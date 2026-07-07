/**
 * FastAPI client.
 * All backend communication goes through here.
 */

import type {
  EvalRunRow,
  EvalJob,
  Gauges,
  HealthResponse,
  ProjectCreate,
  ProjectSummary,
  SelfRecordCorporaResponse,
  CorpusBreakdownResponse,
  SetupState,
  SessionInfo,
  SessionStart,
  SessionListItem,
  SessionHistoryResponse,
  MessageSend,
  MessageResponse,
  ShellRequest,
  ShellResponse,
  FileReadRequest,
  FileReadResponse,
  FileWriteRequest,
  FileWriteResponse,
  MemoryEntry,
  MemoryUserList,
  MemoryUserEntries,
} from "@/types/api";

// Detect backend URL:
// - Web dev: same-origin via Vite proxy (vite.config.ts) → `window.location.origin`
//   resolves `${path}` against the page origin (5173), and Vite forwards
//   `/api`, `/health`, `/ws`, `/voice` to the backend on :8765. This
//   avoids the previous 8766 port drift that caused `TypeError: Load
//   failed` on every fetch.
// - Tauri: read from `window.__HALO_API__` (injected by the Tauri shell
//   at startup; defaults to same-origin in dev mode).
// - Tailscale / prod: override via `VITE_API_BASE` (e.g.
//   "http://box.tail123.ts.net:8765").
//
// Sprint 49 B2: the previous default of `""` produced `fetch(""+path)`
// which throws `TypeError: Load failed` on every call when the SPA
// wasn't on a port that had a working same-origin proxy. The
// `window.location.origin` fallback means the SPA works out-of-the-box
// on the vite dev port (5173) without env-var setup.
const API_BASE =
  (import.meta.env.VITE_API_BASE as string) ||
  (typeof window !== "undefined" && (window as any).__HALO_API__) ||
  (typeof window !== "undefined" ? window.location.origin : "");

class ApiError extends Error {
  status: number;
  body: unknown;
  constructor(status: number, body: unknown, message: string) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

/**
 * Sprint 48 — wrap `requestJson` with bearer-token injection.
 *
 * Reads `window.__haloApiToken` (set by Tauri at startup) and adds
 * `Authorization: Bearer <token>` to every outgoing fetch. If the
 * token is missing (no Tauri shell, dev mode without bootstrap),
 * falls through silently — the read-side endpoints don't require
 * auth, and the write-side endpoints will 401 which the caller
 * will surface as an error.
 *
 * The wrapper preserves `init.headers` so callers can still set
 * their own headers (e.g. `Content-Type` overrides); the bearer
 * is added last so it doesn't get clobbered.
 */
async function authedRequest<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const token = (window as unknown as { __haloApiToken?: string })
    .__haloApiToken;
  const baseHeaders: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init.headers as Record<string, string> | undefined),
  };
  if (token && token.length > 0) {
    baseHeaders["Authorization"] = `Bearer ${token}`;
  }
  return requestJson<T>(path, { ...init, headers: baseHeaders });
}

/**
 * Sprint 49 B4 — split the old monolithic `request()` into
 * `requestJson` + `requestText` so callers pick the right
 * one explicitly.
 *
 * Old code was:
 *
 *   if (!res.ok) {
 *     let body: unknown;
 *     try { body = await res.json(); }
 *     catch { body = await res.text(); }
 *     ...
 *   }
 *
 * This pattern is the source of the
 * `TypeError: Failed to execute 'text' on 'Response': body stream
 * already read` errors that crashed `/settings` and `/audit` on
 * certain fast-Render-cycles. The `await res.json()` in the
 * `try` block consumes the body stream; if the JSON parse
 * throws (because the server returned text/plain), the `catch`
 * branch then tries to `await res.text()` on the SAME consumed
 * stream, which is the lock.
 *
 * The standard fix is `res.clone()` BEFORE the first read. We
 * clone the response in the error branch and consume the
 * clone; if the JSON parse fails, we still have the original
 * for `.text()`. Same shape as the Fetch spec guidance.
 */
async function requestJson<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(init.headers || {}),
    },
    ...init,
  });
  if (!res.ok) {
    // Clone BEFORE reading so we can attempt both .json() and
    // .text() without locking the body stream.
    const cloned = res.clone();
    let body: unknown;
    try {
      body = await cloned.json();
    } catch {
      // Fallback: read the original (not the clone) so the
      // clone is left untouched. If both fail, surface the
      // text "Unknown error body" so callers don't get stuck.
      try {
        body = await res.text();
      } catch {
        body = "Unknown error body (both json+text failed)";
      }
    }
    throw new ApiError(
      res.status,
      body,
      `API ${res.status} on ${path}: ${typeof body === "string" ? body : JSON.stringify(body)}`,
    );
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

/**
 * Sprint 49 — raw-text variant of `requestJson`. Use only for
 * endpoints that return `text/plain` (currently none in the
 * codebase, but kept available for the watchdog curl shim and
 * any future raw-text needs).
 *
 * The error path mirrors `requestJson` — clone + dual-read —
 * so a 500 response with text/plain body still surfaces the
 * server's error message in the `ApiError`.
 */
async function requestText(
  path: string,
  init: RequestInit = {},
): Promise<string> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
  });
  if (!res.ok) {
    const cloned = res.clone();
    let body: string;
    try {
      body = await cloned.text();
    } catch {
      try {
        body = await res.text();
      } catch {
        body = "Unknown error body (both text+json failed)";
      }
    }
    throw new ApiError(res.status, body, `API ${res.status} on ${path}: ${body}`);
  }
  return await res.text();
}

// Health & system
export const api = {
  health: () => requestJson<HealthResponse>("/health"),
  getGauges: () => requestJson<Gauges>("/api/system/gauges"),
  getSystemInfo: () =>
    requestJson<{
      platform: string;
      python_version: string;
      app_version: string;
      git_sha: string;
      build_id: number;
      features: string[];
    }>("/api/system/info"),

  // Sprint 39: held-out eval trend for the HeldOutEvalCard.
  //   - `latest` (EvalRunRow | null) — newest run, or null if no runs yet
  //   - `history` (EvalRunRow[]) — most recent first, max 7
  //   - `threshold_pct` (number) — WER pass/fail bar from
  //     `~/.gundam-halo/test-config.toml` (default 15.0).
  // The backend reads `backend/tests/voice/held_out_results/*.json`
  // (Sprint 38 trend files). Missing dir → `{latest: null,
  // history: [], threshold_pct: 15.0}`. Corrupt JSONs are skipped
  // silently — see `app/voice/held_out_eval.py::load_eval_history`.
  getVoiceEvalResults: () =>
    requestJson<{
      latest: EvalRunRow | null;
      history: EvalRunRow[];
      threshold_pct: number;
    }>("/voice/eval-results"),

  // Sprint 40: held-out eval + fine-tune background runner (M9-E criterion 6).
  //   - `startHeldOutEval` → POST /voice/run-held-out-eval (returns {job_id})
  //   - `getHeldOutEvalJob` → GET /voice/run-held-out-eval/{id}
  //   - `startFinetune` → POST /voice/run-finetune
  //   - `listEvalJobs` → GET /voice/list-jobs
  // The HeldOutEvalCard polls getHeldOutEvalJob every 3s while a job is
  // running, then refetches /voice/eval-results when the job succeeds.
  startHeldOutEval: (params?: {
    threshold?: number;
    model_size?: "tiny" | "base" | "small" | "medium";
    halo_home?: string;
  }) =>
    authedRequest<{ job_id: string; status: string }>(
      "/voice/run-held-out-eval",
      {
        method: "POST",
        body: JSON.stringify({
          threshold: params?.threshold ?? 0.15,
          model_size: params?.model_size ?? "base",
          halo_home: params?.halo_home,
        }),
      },
    ),

  getHeldOutEvalJob: (jobId: string) =>
    requestJson<EvalJob>(
      `/voice/run-held-out-eval/${encodeURIComponent(jobId)}`,
    ),

  startFinetune: (params?: {
    train_corpus_dir?: string;
    base_model_path?: string;
    output_model_dir?: string;
    halo_home?: string;
  }) =>
    authedRequest<{
      job_id: string;
      status: string;
      // Sprint 45: server-side auto-detection echoes back the
      // resolved paths so the UI can confirm what got queued.
      train_corpus_dir?: string;
      base_model_path?: string | null;
    }>("/voice/run-finetune", {
      method: "POST",
      body: JSON.stringify({
        train_corpus_dir: params?.train_corpus_dir,
        base_model_path: params?.base_model_path,
        output_model_dir: params?.output_model_dir,
        halo_home: params?.halo_home,
      }),
    }),

  listEvalJobs: (limit = 10) =>
    requestJson<{ jobs: EvalJob[] }>(
      `/voice/list-jobs?limit=${limit}`,
    ),

  // Sprint 45: scan $HALO_HOME/recordings/yue-self-*/. Used by
  // HeldOutEvalCard to render the "Will fine-tune on: <path>
  // (N chunks · Ms)" hint above the fine-tune button.
  listSelfRecordCorpora: () =>
    requestJson<SelfRecordCorporaResponse>("/voice/self-record-corpora"),

  // Sprint 46: per-corpus WER breakdown. Drives the stacked bar
  // chart in HeldOutEvalCard. `limit` caps how many of the most
  // recent runs are bucketed (default 20).
  getEvalCorpusBreakdown: (limit = 20) =>
    requestJson<CorpusBreakdownResponse>(
      `/voice/eval-corpus-breakdown?limit=${limit}`,
    ),

  // Sprint 39: setup wizard state for the SetupWizard card.
  //   - `status` (string) — "in_progress" | "complete" | "skipped" | ...
  //   - `current_step` (int) — 1..8 (matches the 8 wizard steps)
  //   - `completed_steps` (int[]) — list of step numbers the user finished
  //   - `started_at` / `finished_at` (string | null) — ISO timestamps
  //   - `skipped` (bool) — true if the user opted to skip (out of M13 scope)
  //   - `reason` (string | null) — populated when `skipped` is true
  // Missing endpoint → ApiError 404. Caller handles via try/catch.
  getSetupState: () =>
    requestJson<SetupState>("/api/setup/state"),

  // Sprint 16 + 17a + 17b: voice config GET / PUT.
  //   - `wake_phrases` (Sprint 16) — list of strings, multi-line
  //     textarea in Settings → Voice.
  //   - `strict_wake_phrase` (Sprint 17a) — boolean. When true,
  //     voice turns whose ASR transcript does not start with a
  //     configured wake phrase are discarded.
  // The PUT persists to ~/.gundam-halo/config.toml so the next
  // server start also picks it up. The in-process config is
  // updated immediately so the very next voice turn benefits.
  //
  // Sprint 17b also adds read-only fields on the GET response
  // (asr_backend, asr_corrector, restart_required) — those are
  // surfaced by the Settings → Voice tab so the user can see
  // which engine is loaded.
  //
  // Sprint 18 Track B: the ASR engine and corrector are now
  // **editable** via the Settings → Voice tab. Both are optional
  // in the PUT payload; the backend validates the value, persists
  // it to config.toml, and flips `restart_required: true` in the
  // response when either field actually changed. Changing either
  // requires a backend restart (the 2GB SenseVoice + fsmn-vad
  // pipeline is loaded once at voice WS connect time).
  //
  // Sprint 19c: `always_on_mic` is a runtime-tunable flag
  // (no restart). When true, the cockpit auto-fires the
  // agent on the backend's VAD speech_start event
  // (Sprint 19c Phase 1 wires the vad.state WS
  // forwarding; the frontend auto-fire hook ships in
  // Phase 2).
  getVoiceConfig: () =>
    requestJson<{
      wake_phrases: string[];
      strict_wake_phrase: boolean;
      asr_backend?: string;
      asr_corrector?: string;
      always_on_mic?: boolean;
      restart_required?: boolean;
      // Sprint 41 — live countdown for the RestartNudgeBanner.
      restart_scheduled?: boolean;
      restart_in_seconds?: number | null;
    }>("/voice/config"),
  setVoiceConfig: (payload: {
    wake_phrases: string[];
    strict_wake_phrase: boolean;
    asr_backend?: string;
    asr_corrector?: string;
    always_on_mic?: boolean;
  }) =>
    requestJson<{
      wake_phrases: string[];
      strict_wake_phrase: boolean;
      asr_backend?: string;
      asr_corrector?: string;
      always_on_mic?: boolean;
      restart_required?: boolean;
      // Sprint 19b: when the backend schedules a self-restart
      // in response to an asr change, this is true. The
      // dashboard surfaces a "Backend restarting in 5s" toast
      // so the user knows to expect a brief disconnect.
      restart_scheduled?: boolean;
      persisted: boolean;
      error?: string;
    }>("/voice/config", {
      method: "PUT",
      body: JSON.stringify(payload),
    }),

  // Projects
  listProjects: () => requestJson<ProjectSummary[]>("/api/projects"),
  createProject: (data: ProjectCreate) =>
    requestJson<ProjectSummary>("/api/projects", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  getProject: (name: string) => requestJson<ProjectSummary>(`/api/projects/${name}`),
  deleteProject: (name: string) =>
    requestJson<void>(`/api/projects/${name}`, { method: "DELETE" }),
  archiveProject: (name: string) =>
    requestJson<ProjectSummary>(`/api/projects/${name}/archive`, { method: "POST" }),

  // Memory (persisted sessions)
  listProjectMemory: (name: string) =>
    requestJson<SessionListItem[]>(`/api/projects/${name}/memory`),
  getSessionMessages: (name: string, sessionId: string) =>
    requestJson<{ session_id: string; project_name: string; message_count: number; messages: any[] }>(
      `/api/projects/${name}/memory/${sessionId}`,
    ),

  // Sessions
  listSessions: () => requestJson<SessionInfo[]>("/api/sessions"),
  startSession: (data: SessionStart) =>
    requestJson<SessionInfo>("/api/sessions", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  getSession: (id: string) => requestJson<SessionInfo>(`/api/sessions/${id}`),
  sendMessage: (sessionId: string, data: MessageSend) =>
    requestJson<MessageResponse>(
      `/api/sessions/${sessionId}/message`,
      { method: "POST", body: JSON.stringify(data) },
    ),
  stopSession: (id: string) =>
    requestJson<{ session_id: string; status: string }>(`/api/sessions/${id}/stop`, {
      method: "POST",
    }),
  /** A5 — fetch persisted message history for a session.
   *
   *  Used by ProjectDetailPage to:
   *    1. Hydrate the local message list on mount (so a page
   *       refresh doesn't wipe the conversation).
   *    2. Resume a known session from a deep-link.
   *
   *  Returns the same wire format as `/api/projects/:name/memory/:sessionId`
   *  so callers can share a single mapper.
   */
  getSessionHistory: (id: string) =>
    requestJson<SessionHistoryResponse>(`/api/sessions/${id}/messages`),

  // Mac control
  readFile: (data: FileReadRequest) =>
    requestJson<FileReadResponse>("/api/mac/file/read", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  writeFile: (data: FileWriteRequest) =>
    requestJson<FileWriteResponse>("/api/mac/file/write", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  runShell: (data: ShellRequest) =>
    requestJson<ShellResponse>("/api/mac/shell", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  // Settings
  getSettings: () => requestJson<import("@/types/api").Settings>("/api/settings"),
  getAuditLog: (limit = 100) =>
    requestJson<import("@/types/api").AuditEntry[]>(
      `/api/settings/audit?limit=${limit}`,
    ),

  // Secrets (runtime secret management, M6+). Values are NEVER
  // returned by the server — only a `{configured: bool, source: ...}`
  // status. The POST `value` is sent over HTTPS (or Tailscale) and
  // never logged on either side.
  getSecrets: () =>
    requestJson<
      Record<
        string,
        { label: string; configured: boolean; source: "override" | "env" | "none" }
      >
    >("/api/secrets"),
  setSecrets: (
    items: Array<{ name: string; value: string }>,
  ) =>
    requestJson<
      Record<
        string,
        { label: string; configured: boolean; source: "override" | "env" | "none" }
      >
    >("/api/secrets", {
      method: "POST",
      body: JSON.stringify({ secrets: items }),
    }),
  deleteSecret: (name: string) =>
    requestJson<
      Record<
        string,
        { label: string; configured: boolean; source: "override" | "env" | "none" }
      >
    >(`/api/secrets/${name}`, { method: "DELETE" }),
  clearSecrets: (names: string[]) =>
    requestJson<
      Record<
        string,
        { label: string; configured: boolean; source: "override" | "env" | "none" }
      >
    >("/api/secrets/clear", {
      method: "POST",
      body: JSON.stringify({ names }),
    }),
  // User Memory (M7-Phase-2.5). Read-only viewer for the agent's
  // per-user key/value memory. The dashboard cannot write directly;
  // the agent uses the memory_write tool. The dashboard can delete
  // entries the agent got wrong.
  listMemoryUsers: () =>
    requestJson<{ users: string[] }>("/api/memory"),
  listMemoryEntries: (user: string) =>
    requestJson<{ user: string; entries: Array<{ key: string; value: string; updated_at: number; created_at: number }> }>(
      `/api/memory/${encodeURIComponent(user)}`,
    ),
  readMemoryEntry: (user: string, key: string) =>
    requestJson<{ key: string; value: string; updated_at: number; created_at: number }>(
      `/api/memory/${encodeURIComponent(user)}/${encodeURIComponent(key)}`,
    ),
  deleteMemoryEntry: (user: string, key: string) =>
    requestJson<{ deleted: boolean; user: string; key: string }>(
      `/api/memory/${encodeURIComponent(user)}/${encodeURIComponent(key)}`,
      { method: "DELETE" },
    ),
};

export { ApiError, API_BASE };

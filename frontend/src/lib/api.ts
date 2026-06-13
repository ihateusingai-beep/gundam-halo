/**
 * FastAPI client.
 * All backend communication goes through here.
 */

import type {
  Gauges,
  HealthResponse,
  ProjectCreate,
  ProjectSummary,
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
// - Web dev: same-origin via Vite proxy (vite.config.ts) → empty string
//   means `${path}` is resolved relative to the page origin (5173),
//   and Vite forwards `/api`, `/health`, `/ws`, `/voice` to the
//   backend on :8000. This avoids the previous 8766 port drift that
//   caused `TypeError: Load failed` on every fetch.
// - Tauri: read from window.__TAURI__ (TBD).
// - Tailscale / prod: override via VITE_API_BASE (e.g. "http://box:8000").
const API_BASE =
  (import.meta.env.VITE_API_BASE as string) ||
  (typeof window !== "undefined" && (window as any).__HALO_API__) ||
  "";

class ApiError extends Error {
  status: number;
  body: unknown;
  constructor(status: number, body: unknown, message: string) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

async function request<T>(
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
    let body: unknown;
    try {
      body = await res.json();
    } catch {
      body = await res.text();
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

// Health & system
export const api = {
  health: () => request<HealthResponse>("/health"),
  getGauges: () => request<Gauges>("/api/system/gauges"),
  getSystemInfo: () => request<{ platform: string; python_version: string; app_version: string }>("/api/system/info"),

  // Projects
  listProjects: () => request<ProjectSummary[]>("/api/projects"),
  createProject: (data: ProjectCreate) =>
    request<ProjectSummary>("/api/projects", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  getProject: (name: string) => request<ProjectSummary>(`/api/projects/${name}`),
  deleteProject: (name: string) =>
    request<void>(`/api/projects/${name}`, { method: "DELETE" }),
  archiveProject: (name: string) =>
    request<ProjectSummary>(`/api/projects/${name}/archive`, { method: "POST" }),

  // Memory (persisted sessions)
  listProjectMemory: (name: string) =>
    request<SessionListItem[]>(`/api/projects/${name}/memory`),
  getSessionMessages: (name: string, sessionId: string) =>
    request<{ session_id: string; project_name: string; message_count: number; messages: any[] }>(
      `/api/projects/${name}/memory/${sessionId}`,
    ),

  // Sessions
  listSessions: () => request<SessionInfo[]>("/api/sessions"),
  startSession: (data: SessionStart) =>
    request<SessionInfo>("/api/sessions", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  getSession: (id: string) => request<SessionInfo>(`/api/sessions/${id}`),
  sendMessage: (sessionId: string, data: MessageSend) =>
    request<MessageResponse>(
      `/api/sessions/${sessionId}/message`,
      { method: "POST", body: JSON.stringify(data) },
    ),
  stopSession: (id: string) =>
    request<{ session_id: string; status: string }>(`/api/sessions/${id}/stop`, {
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
    request<SessionHistoryResponse>(`/api/sessions/${id}/messages`),

  // Mac control
  readFile: (data: FileReadRequest) =>
    request<FileReadResponse>("/api/mac/file/read", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  writeFile: (data: FileWriteRequest) =>
    request<FileWriteResponse>("/api/mac/file/write", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  runShell: (data: ShellRequest) =>
    request<ShellResponse>("/api/mac/shell", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  // Settings
  getSettings: () => request<import("@/types/api").Settings>("/api/settings"),
  getAuditLog: (limit = 100) =>
    request<import("@/types/api").AuditEntry[]>(
      `/api/settings/audit?limit=${limit}`,
    ),

  // Secrets (runtime secret management, M6+). Values are NEVER
  // returned by the server — only a `{configured: bool, source: ...}`
  // status. The POST `value` is sent over HTTPS (or Tailscale) and
  // never logged on either side.
  getSecrets: () =>
    request<
      Record<
        string,
        { label: string; configured: boolean; source: "override" | "env" | "none" }
      >
    >("/api/secrets"),
  setSecrets: (
    items: Array<{ name: string; value: string }>,
  ) =>
    request<
      Record<
        string,
        { label: string; configured: boolean; source: "override" | "env" | "none" }
      >
    >("/api/secrets", {
      method: "POST",
      body: JSON.stringify({ secrets: items }),
    }),
  deleteSecret: (name: string) =>
    request<
      Record<
        string,
        { label: string; configured: boolean; source: "override" | "env" | "none" }
      >
    >(`/api/secrets/${name}`, { method: "DELETE" }),
  clearSecrets: (names: string[]) =>
    request<
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
    request<{ users: string[] }>("/api/memory"),
  listMemoryEntries: (user: string) =>
    request<{ user: string; entries: Array<{ key: string; value: string; updated_at: number; created_at: number }> }>(
      `/api/memory/${encodeURIComponent(user)}`,
    ),
  readMemoryEntry: (user: string, key: string) =>
    request<{ key: string; value: string; updated_at: number; created_at: number }>(
      `/api/memory/${encodeURIComponent(user)}/${encodeURIComponent(key)}`,
    ),
  deleteMemoryEntry: (user: string, key: string) =>
    request<{ deleted: boolean; user: string; key: string }>(
      `/api/memory/${encodeURIComponent(user)}/${encodeURIComponent(key)}`,
      { method: "DELETE" },
    ),
};

export { ApiError, API_BASE };

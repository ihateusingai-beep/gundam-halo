/**
 * Voice tab shared types — owned by `tabs/VoiceTab.tsx`,
 * imported by the 7 `sections/*.tsx` leaves.
 *
 * Extracted from the original 828-LoC VoiceTab.tsx (Sprint
 * 56.7 / Senior-engineer audit #1-ROI refactor). The split
 * keeps each section to ~30-180 LoC and gives React.memo
 * boundaries a meaningful surface to memo on (the per-section
 * `store` interface below is the memoization key).
 */
import type { VoiceStatus } from "@/services/halo-voice-ws";

/** Voice config shape returned by GET /voice/config.
 *
 * NOTE: this is a *subset* of `Settings.voice`. The settings
 * payload has more fields (VAD thresholds, TTS voice id,
 * etc.) that the wizard doesn't expose yet. The wizard reads
 * what it needs + falls back to defaults for the rest. */
export interface VoiceConfig {
  wake_phrases: string[];
  strict_wake_phrase: boolean;
  asr_backend?: string;
  asr_corrector?: string;
  always_on_mic?: boolean;
  restart_required?: boolean;
}

/** ASR backend picker — Sprint 18, expanded Sprint 23 to
 *  include `whisper_hf`. The draft state is constrained to
 *  the values the renderer offers. Server may report an
 *  unknown value (hand-edited config.toml) — see
 *  `isAsrBackend()` for the type guard. */
export type AsrBackendDraft = "whisper_local" | "yuesub" | "whisper_hf";

/** Post-ASR correction picker — Sprint 18. */
export type AsrCorrectorDraft = "bert" | "opencc" | "none";

/** Type guards used by the orchestrator (VoiceTab.tsx) when
 *  hydrating drafts from the server response. The server may
 *  report values outside the picker set (e.g. a hand-edited
 *  config.toml with `asr_backend = "mlx_whisper"`); we
 *  silently fall back to the default so the radio still
 *  shows a selected state.
 *
 *  Why a type guard and not a Zod schema: the radio state
 *  and the draft state are independent — even if the
 *  server-rejected value is preserved in `config.asr_backend`,
 *  the radio falls back to the local default. The draft
 *  diverges from the server truth by design. */
export function isAsrBackend(value: unknown): value is AsrBackendDraft {
  return value === "whisper_local" || value === "yuesub" || value === "whisper_hf";
}

export function isAsrCorrector(value: unknown): value is AsrCorrectorDraft {
  return value === "bert" || value === "opencc" || value === "none";
}

/** The shared store every section reads. Defining it here
 *  (not in VoiceTab.tsx) means each section file can be
 *  edited in isolation; the contract is enforced by the type
 *  checker.
 *
 *  Two invariant groups:
 *
 *  1. Read-only server state — `config`, `voiceStatus`.
 *     Mutation happens via `setConfig` (after a successful
 *     PUT) so the UI immediately reflects the new persisted
 *     state.
 *
 *  2. Editable drafts — `asrBackend`, `asrCorrector`,
 *     `alwaysOnMic`, `draft`, `strictDraft`. These are
 *     controlled-component state held by VoiceTab.tsx so
 *     Save / Reset can read ALL drafts uniformly.
 *
 *  The SaveBar also reads `saving` (disabled while in
 *  flight) and `handleSave` + `handleReset` are passed down
 *  to keep ownership of the action in VoiceTab.tsx (which
 *  sees all drafts). */
export interface VoiceSectionsStore {
  config: VoiceConfig | null;
  setConfig: (c: VoiceConfig) => void;
  voiceStatus: VoiceStatus;

  // ASR engine drafts
  asrBackend: AsrBackendDraft;
  setAsrBackend: (v: AsrBackendDraft) => void;
  asrCorrector: AsrCorrectorDraft;
  setAsrCorrector: (v: AsrCorrectorDraft) => void;

  // Voice interaction mode (Sprint 19c)
  alwaysOnMic: boolean;
  setAlwaysOnMic: (v: boolean) => void;

  // Wake phrases (Sprint 16) + strict gate (Sprint 17a)
  draft: string;
  setDraft: (v: string) => void;
  strictDraft: boolean;
  setStrictDraft: (v: boolean) => void;

  // Save action owner
  saving: boolean;
  handleSave: () => Promise<void> | void;
  handleReset: () => void;
}

/** Sprint 33b Personalised Fine-tune — Tauri IPC response shape.
 *  Mirrors the Rust `RecordingCommandResponse`'s JSON payload. */
export interface FinetuneResponse {
  phase: "running" | "complete" | "error";
  message: string;
  progress?: number;
  logTail?: string[];
}

/** UI-side mirror of `FinetuneResponse.phase` + the
 *  pre-click `idle` state. */
export type CardPhase = "idle" | "running" | "complete" | "error";

/** Per-card setters passed to `runFinetuneCommand()` so the
 *  dispatcher can write back to whichever slot invoked it. */
export interface CardSetters {
  setPhase: (p: CardPhase) => void;
  setMessage: (m: string) => void;
  label: string;
}

/** The 3 Tauri IPC commands the dispatcher knows how to
 *  invoke. Typing the union means TS catches typos like
 *  `runFinetuneCommand("start_recoording", …)` at compile
 *  time (the old code used string literals inline). */
export type FinetuneCommand = "start_record" | "start_train" | "activate_model";

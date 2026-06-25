/**
 * Setup Wizard API — Sprint 44.
 *
 * Typed wrapper around the 11 /api/setup/* endpoints plus the 2
 * Sprint 44 preview endpoints (/llm/validate, /tts/preview).
 *
 * Mirrors the pattern in `lib/api.ts` (FastAPI client with shared
 * ApiError + ApiClient.request() helper). Kept in a separate
 * module so the wizard-specific types + flows don't pollute the
 * generic API surface.
 */

import type {
  LLMConfig,
  LLMValidateResponse,
  SetupState,
  SetupStepPayload,
  TailscaleConfig,
  ThemeConfig,
  TTSPreviewResponse,
  VoiceASRConfig,
  VoiceTTSConfig,
} from "@/types/api";

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

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(init.headers || {}) },
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

/** Strip the optional `fallback_model` so the backend doesn't reject
 *  an empty string when the user didn't fill it in. */
function llmPayload(cfg: LLMConfig) {
  return {
    provider: cfg.provider,
    api_key: cfg.api_key,
    base_url: cfg.base_url,
    default_model: cfg.default_model,
    fallback_model: cfg.fallback_model ?? "",
    api_key_env: "MINIMAX_API_KEY",
  };
}

export const setupApi = {
  getState: () => request<SetupState>("/api/setup/state"),

  start: () =>
    request<SetupStepPayload>("/api/setup/start", { method: "POST" }),

  submitLLM: (cfg: LLMConfig) =>
    request<SetupStepPayload>("/api/setup/llm", {
      method: "POST",
      body: JSON.stringify(llmPayload(cfg)),
    }),

  /** Sprint 44 — inline API-key validation. Never persists. */
  validateLLM: (cfg: LLMConfig) =>
    request<LLMValidateResponse>("/api/setup/llm/validate", {
      method: "POST",
      body: JSON.stringify(llmPayload(cfg)),
    }),

  submitASR: (cfg: VoiceASRConfig) =>
    request<SetupStepPayload>("/api/setup/voice-asr", {
      method: "POST",
      body: JSON.stringify({
        backend: cfg.backend,
        model_size: cfg.model_size ?? "base",
        model_path: cfg.model_path ?? "",
        device: cfg.device ?? "cpu",
      }),
    }),

  submitTTS: (cfg: VoiceTTSConfig) =>
    request<SetupStepPayload>("/api/setup/voice-tts", {
      method: "POST",
      body: JSON.stringify(cfg),
    }),

  /** Sprint 44 — render a 1-sentence TTS preview. Returns base64 WAV. */
  previewTTS: (cfg: { backend: string; voice: string; text?: string }) =>
    request<TTSPreviewResponse>("/api/setup/tts/preview", {
      method: "POST",
      body: JSON.stringify({
        backend: cfg.backend,
        voice: cfg.voice,
        text: cfg.text ?? "你好，Unicorn。",
      }),
    }),

  submitTheme: (cfg: ThemeConfig) =>
    request<SetupStepPayload>("/api/setup/theme", {
      method: "POST",
      body: JSON.stringify({ theme: cfg.themeId }),
    }),

  submitTailscale: (cfg: TailscaleConfig) =>
    request<SetupStepPayload>("/api/setup/tailscale", {
      method: "POST",
      body: JSON.stringify({
        enabled: cfg.enabled,
        hostname: cfg.hostname,
      }),
    }),

  runSmoke: () =>
    request<SetupStepPayload>("/api/setup/smoke", { method: "POST" }),

  finish: () =>
    request<SetupStepPayload>("/api/setup/finish", { method: "POST" }),

  skip: () =>
    request<SetupStepPayload>("/api/setup/skip", { method: "POST" }),

  reset: () =>
    request<SetupStepPayload>("/api/setup/reset", { method: "POST" }),
};

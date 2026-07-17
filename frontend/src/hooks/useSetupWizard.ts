/**
 * useSetupWizard — Sprint 44 wizard state machine.
 *
 * Single source of truth for the wizard's UI state. Mirrors the
 * backend's `compute_setup_state()` but holds the local form state
 * for fields the user is currently editing.
 *
 * Step lifecycle:
 *   1. Mount → call setupApi.getState() → seed initial step
 *   2. User clicks "Next" → POST /api/setup/<step-endpoint>
 *   3. On success → advance current_step
 *   4. On error → display field-level errors, stay on step
 *
 * Crash recovery: the backend's `setup_state.json` is the source of
 * truth for "what step are we on". If the wizard crashes mid-flow,
 * the next mount picks up where we left off. We DO NOT cache the
 * wizard's form state in localStorage — that's extra complexity for
 * a flow that takes 90s.
 */

import { useCallback, useEffect, useState } from "react";

import { setupApi } from "@/lib/setup-api";
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

export type WizardStep = 1 | 2 | 3 | 4 | 5 | 6 | 7;
export type WizardStatus =
  | "loading"
  | "active"
  | "submitting"
  | "error"
  | "finished";

// Sprint 74 X-A — wizard mode. "essential" is the 3-step fast path
// (Welcome → LLM → Smoke); "advanced" is the full 7-step path
// (+ ASR, TTS, Theme, Tailscale). The choice is persisted to
// setup_state.json via POST /api/setup/mode.
export type WizardMode = "essential" | "advanced";

export const ESSENTIAL_TOTAL_STEPS = 3;
export const ADVANCED_TOTAL_STEPS = 7;

export interface WizardError {
  field: string;
  code: string;
  message: string;
}

export interface UseSetupWizardResult {
  status: WizardStatus;
  currentStep: WizardStep;
  completedSteps: WizardStep[];
  errors: WizardError[];
  redirect: string | null;

  // Sprint 74 X-A — wizard mode (essential | advanced) + total step
  // count for the active mode. Persisted via setupApi.setMode().
  mode: WizardMode;
  totalSteps: 3 | 7;
  setMode: (mode: WizardMode) => Promise<void>;

  // Step submit handlers.
  submitLLM: (cfg: LLMConfig) => Promise<void>;
  submitASR: (cfg: VoiceASRConfig) => Promise<void>;
  submitTTS: (cfg: VoiceTTSConfig) => Promise<void>;
  submitTheme: (cfg: ThemeConfig) => Promise<void>;
  submitTailscale: (cfg: TailscaleConfig) => Promise<void>;
  runSmoke: () => Promise<void>;

  finish: () => Promise<void>;
  skip: () => Promise<void>;
  reset: () => Promise<void>;

  // Inline preview helpers (Sprint 44).
  validateLLM: (cfg: LLMConfig) => Promise<LLMValidateResponse>;
  previewTTS: (cfg: {
    backend: string;
    voice: string;
    text?: string;
  }) => Promise<TTSPreviewResponse>;

  // Form state defaults (used to pre-fill StepLLM, StepVoiceASR, etc.).
  llmForm: LLMConfig;
  asrForm: VoiceASRConfig;
  ttsForm: VoiceTTSConfig;
  themeForm: ThemeConfig;
  tailscaleForm: TailscaleConfig;
}

const DEFAULT_LLM: LLMConfig = {
  provider: "minimax",
  api_key: "",
  base_url: "https://api.minimax.io/v1",
  default_model: "MiniMax-M2",
  fallback_model: "",
};

const DEFAULT_ASR: VoiceASRConfig = {
  backend: "whisper_local",
  model_size: "base",
  model_path: "",
  device: "cpu",
};

const DEFAULT_TTS: VoiceTTSConfig = {
  backend: "edge",
  voice: "zh-HK-HiuMaanNeural",
  rate: "+0%",
  pitch: "+0Hz",
  volume: "+0%",
};

const DEFAULT_THEME: ThemeConfig = { themeId: "gundam-ntd" };

const DEFAULT_TAILSCALE: TailscaleConfig = {
  enabled: false,
  hostname: "gundam-halo",
};

export function useSetupWizard(): UseSetupWizardResult {
  const [state, setState] = useState<SetupState | null>(null);
  const [status, setStatus] = useState<WizardStatus>("loading");
  const [errors, setErrors] = useState<WizardError[]>([]);
  const [redirect, setRedirect] = useState<string | null>(null);
  // Sprint 74 X-A — wizard mode. Default "essential" matches the
  // backend's default for fresh state files. Persisted via
  // setupApi.setMode() (POST /api/setup/mode) when toggled.
  const [mode, setModeState] = useState<WizardMode>("essential");

  const [llmForm, setLlmForm] = useState<LLMConfig>(DEFAULT_LLM);
  const [asrForm, setAsrForm] = useState<VoiceASRConfig>(DEFAULT_ASR);
  const [ttsForm, setTtsForm] = useState<VoiceTTSConfig>(DEFAULT_TTS);
  const [themeForm, setThemeForm] = useState<ThemeConfig>(DEFAULT_THEME);
  const [tailscaleForm, setTailscaleForm] =
    useState<TailscaleConfig>(DEFAULT_TAILSCALE);

  // Initial fetch — picks up where the user left off (crash recovery).
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const s = await setupApi.getState();
        if (cancelled) return;
        setState(s);
        // Sprint 74 X-A — hydrate mode from server. Defensive: an
        // old (pre-0.3.15) backend that doesn't return `mode` defaults
        // to "essential" rather than crashing the wizard.
        setModeState(s.mode ?? "essential");
        if (s.status === "complete") {
          setStatus("finished");
        } else {
          setStatus("active");
        }
      } catch {
        if (cancelled) return;
        // 404 or network error → treat as fresh start at step 1.
        setState({
          status: "pending",
          current_step: 1,
          completed_steps: [],
          started_at: null,
          finished_at: null,
          skipped: false,
          reason: null,
          mode: "essential",
          total_steps: 3,
        });
        setStatus("active");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // Apply the response from any submit to the wizard state.
  const applyResponse = useCallback((res: SetupStepPayload) => {
    setState({
      status: res.status,
      current_step: res.current_step,
      completed_steps: res.completed_steps,
      started_at: res.started_at,
      finished_at: res.finished_at,
      skipped: res.skipped,
      reason: res.reason,
      // Sprint 74 X-A — backend always includes mode + total_steps
      // (post-0.3.15). If a pre-0.3.15 backend reply is somehow
      // threaded through, fall back to the current mode rather
      // than crash.
      mode: (res.mode as WizardMode | undefined) ?? mode,
      total_steps:
        (res.total_steps as 3 | 7 | undefined) ??
        (mode === "advanced" ? ADVANCED_TOTAL_STEPS : ESSENTIAL_TOTAL_STEPS),
    });
    if (res.errors && res.errors.length > 0) {
      setErrors(res.errors);
      setStatus("error");
    } else {
      setErrors([]);
      setRedirect(res.redirect ?? null);
      if (res.status === "complete" || res.redirect) {
        setStatus("finished");
      } else {
        setStatus("active");
      }
    }
  }, []);

  const runSubmit = useCallback(
    async (
      fn: () => Promise<SetupStepPayload>,
    ): Promise<SetupStepPayload | null> => {
      setStatus("submitting");
      setErrors([]);
      try {
        const res = await fn();
        applyResponse(res);
        return res;
      } catch (e) {
        setStatus("error");
        setErrors([
          {
            field: "wizard",
            code: "network_error",
            message: e instanceof Error ? e.message : String(e),
          },
        ]);
        return null;
      }
    },
    [applyResponse],
  );

  const submitLLM = useCallback(
    (cfg: LLMConfig) => {
      setLlmForm(cfg);
      return runSubmit(() => setupApi.submitLLM(cfg)).then(() => {});
    },
    [runSubmit],
  );

  const submitASR = useCallback(
    (cfg: VoiceASRConfig) => {
      setAsrForm(cfg);
      return runSubmit(() => setupApi.submitASR(cfg)).then(() => {});
    },
    [runSubmit],
  );

  const submitTTS = useCallback(
    (cfg: VoiceTTSConfig) => {
      setTtsForm(cfg);
      return runSubmit(() => setupApi.submitTTS(cfg)).then(() => {});
    },
    [runSubmit],
  );

  const submitTheme = useCallback(
    (cfg: ThemeConfig) => {
      setThemeForm(cfg);
      return runSubmit(() => setupApi.submitTheme(cfg)).then(() => {});
    },
    [runSubmit],
  );

  const submitTailscale = useCallback(
    (cfg: TailscaleConfig) => {
      setTailscaleForm(cfg);
      return runSubmit(() => setupApi.submitTailscale(cfg)).then(() => {});
    },
    [runSubmit],
  );

  const runSmoke = useCallback(
    () => runSubmit(() => setupApi.runSmoke()).then(() => {}),
    [runSubmit],
  );

  const finish = useCallback(
    () => runSubmit(() => setupApi.finish()).then(() => {}),
    [runSubmit],
  );

  const skip = useCallback(
    () => runSubmit(() => setupApi.skip()).then(() => {}),
    [runSubmit],
  );

  const reset = useCallback(
    () => runSubmit(() => setupApi.reset()).then(() => {}),
    [runSubmit],
  );

  // Sprint 74 X-A — flip the wizard's mode (essential | advanced).
  // Persists to the backend via POST /api/setup/mode, then mirrors
  // the response into local state. Returns a promise so the caller
  // can show a toast or animate the transition.
  const setMode = useCallback(async (next: WizardMode) => {
    if (next === mode) return;
    try {
      const res = await setupApi.setMode(next);
      setModeState(next);
      // Update the cached state object too so a subsequent
      // applyResponse() doesn't overwrite the mode we just set.
      if (res) {
        setState((prev) =>
          prev
            ? {
                ...prev,
                mode: res.mode ?? next,
                current_step: res.current_step ?? prev.current_step,
                completed_steps: res.completed_steps ?? prev.completed_steps,
                status: res.status ?? prev.status,
              }
            : prev,
        );
      }
    } catch (e) {
      // Surface as a wizard-level error so the caller can show a toast.
      setErrors([
        {
          field: "wizard",
          code: "mode_change_failed",
          message: e instanceof Error ? e.message : String(e),
        },
      ]);
      setStatus("error");
    }
  }, [mode]);

  const validateLLM = useCallback(
    (cfg: LLMConfig) => setupApi.validateLLM(cfg),
    [],
  );

  const previewTTS = useCallback(
    (cfg: { backend: string; voice: string; text?: string }) =>
      setupApi.previewTTS(cfg),
    [],
  );

  return {
    status,
    currentStep: (state?.current_step ?? 1) as WizardStep,
    completedSteps: (state?.completed_steps ?? []) as WizardStep[],
    errors,
    redirect,
    // Sprint 74 X-A — expose mode + totalSteps so the cockpit card
    // and WizardShell can render mode-aware UI without recomputing.
    mode,
    totalSteps: mode === "advanced" ? ADVANCED_TOTAL_STEPS : ESSENTIAL_TOTAL_STEPS,
    setMode,
    submitLLM,
    submitASR,
    submitTTS,
    submitTheme,
    submitTailscale,
    runSmoke,
    finish,
    skip,
    reset,
    validateLLM,
    previewTTS,
    llmForm,
    asrForm,
    ttsForm,
    themeForm,
    tailscaleForm,
  };
}

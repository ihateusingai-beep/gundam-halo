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

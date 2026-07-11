/**
 * StepVoiceTTS — Wizard step 4. Pick TTS backend + voice.
 *
 * Three backends: edge (free, default), azure (premium), piper
 * (offline). Each has its own voice catalogue. The user can click
 * "Preview" next to a voice to hear a 1-sentence sample via the
 * /api/setup/tts/preview endpoint (Sprint 44).
 *
 * If the voice layer isn't loaded yet (i.e. user jumped to step 4
 * without finishing the wizard), preview shows "Preview unavailable
 * until step 7" — graceful fallback per the spec.
 */

import { useState } from "react";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { useStepValidation } from "@/hooks/useStepValidation";
import { cn } from "@/lib/utils";
import type { VoiceTTSConfig } from "@/types/api";
import type { WizardError } from "@/hooks/useSetupWizard";

/** Sprint 65 W-A4 (migrate 2): Zod schema for StepVoiceTTS.
 *  Mirrors the existing VoiceTTSConfig type in @/types/api. */
const ttsSchema = z.object({
  backend: z.enum(["edge", "azure", "piper"]),
  voice: z.string().min(1, "Voice is required"),
  rate: z.string().min(1, "Rate is required"),
  pitch: z.string().min(1, "Pitch is required"),
  volume: z.string().min(1, "Volume is required"),
});

export interface StepVoiceTTSProps {
  form: VoiceTTSConfig;
  onSubmit: (cfg: VoiceTTSConfig) => Promise<void>;
  onPreview: (cfg: {
    backend: string;
    voice: string;
    text?: string;
  }) => Promise<{
    ok: boolean;
    audio_base64: string | null;
    error: string | null;
    error_code?: string | null;
  }>;
  errors: WizardError[];
  busy: boolean;
}

const VOICES: Record<string, string[]> = {
  edge: [
    "zh-HK-HiuMaanNeural",
    "zh-HK-WanLungNeural",
    "zh-CN-XiaoxiaoNeural",
    "en-US-JennyNeural",
    "ja-JP-NanamiNeural",
  ],
  azure: ["zh-HK-HiuMaanNeural", "en-US-AriaNeural"],
  piper: ["zh_CN-huayan-medium", "en_US-lessac-medium"],
};

export function StepVoiceTTS({ form, onSubmit, onPreview, errors, busy }: StepVoiceTTSProps) {
  const [draft, setDraft] = useState<VoiceTTSConfig>(form);
  const [previewing, setPreviewing] = useState<string | null>(null);
  const [previewAudio, setPreviewAudio] = useState<string | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  // Sprint 65 W-A4: Zod validation. Zod errors take precedence
  // over backend errors (same pattern as StepLLM / StepVoiceASR).
  const zodValidation = useStepValidation(ttsSchema, draft);
  const allErrors: WizardError[] = [
    ...zodValidation.errors.map((e) => ({
      field: e.field,
      code: "zod",
      message: e.message,
    })),
    ...errors,
  ];

  const voices = VOICES[draft.backend] ?? [];

  async function handlePreview(voice: string) {
    setPreviewing(voice);
    setPreviewError(null);
    try {
      const res = await onPreview({
        backend: draft.backend,
        voice,
        text: "你好，Unicorn。",
      });
      if (res.ok && res.audio_base64) {
        setPreviewAudio(`data:audio/wav;base64,${res.audio_base64}`);
      } else {
        setPreviewAudio(null);
        setPreviewError(
          res.error_code === "voice_layer_not_loaded"
            ? "Preview unavailable until step 7."
            : (res.error ?? "Preview failed"),
        );
      }
    } catch (e) {
      setPreviewError(String(e));
    } finally {
      setPreviewing(null);
    }
  }

  return (
    <div className="space-y-3 py-2" data-testid="step-voice-tts">
      <h2 className="text-lg font-[Rajdhani] text-[var(--text-primary)]">
        Voice Text-to-Speech
      </h2>

      <div className="grid grid-cols-3 gap-2">
        {(["edge", "azure", "piper"] as const).map((b) => (
          <button
            key={b}
            data-testid={`tts-backend-${b}`}
            onClick={() => {
              setDraft({ ...draft, backend: b });
              setPreviewAudio(null);
              setPreviewError(null);
            }}
            className={cn(
              "border px-3 py-2 text-left",
              draft.backend === b
                ? "border-[var(--accent)] bg-[var(--accent)]/10"
                : "border-[var(--border-color)]",
            )}
          >
            <div className="text-xs font-mono font-bold">{b}</div>
            <div className="text-[10px] text-[var(--text-muted)] mt-0.5">
              {b === "edge" && "free, online"}
              {b === "azure" && "premium quality"}
              {b === "piper" && "offline, local"}
            </div>
          </button>
        ))}
      </div>

      <div>
        <label className="text-[10px] uppercase tracking-widest font-[Orbitron] text-[var(--text-muted)]">
          Voice
        </label>
        <div className="space-y-1 mt-1">
          {voices.map((v) => (
            <div
              key={v}
              className={cn(
                "flex items-center gap-2 px-2 py-1 border",
                draft.voice === v
                  ? "border-[var(--accent)]"
                  : "border-[var(--border-color)]",
              )}
            >
              <button
                data-testid={`tts-voice-${v}`}
                onClick={() => setDraft({ ...draft, voice: v })}
                className="flex-1 text-left text-xs font-mono"
              >
                {v}
              </button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => handlePreview(v)}
                disabled={previewing === v}
                data-testid={`tts-preview-${v}`}
              >
                {previewing === v ? "…" : "Preview"}
              </Button>
            </div>
          ))}
        </div>
        {previewAudio && (
          <audio
            data-testid="tts-preview-audio"
            controls
            autoPlay
            src={previewAudio}
            className="mt-2 w-full h-8"
          />
        )}
        {previewError && (
          <p
            data-testid="tts-preview-error"
            className="text-[10px] text-[var(--warning)] font-mono mt-1"
          >
            {previewError}
          </p>
        )}
      </div>

      <div className="grid grid-cols-3 gap-3">
        <div>
          <label className="text-[10px] uppercase tracking-widest font-[Orbitron] text-[var(--text-muted)]">
            Rate
          </label>
          <input
            value={draft.rate}
            onChange={(e) => setDraft({ ...draft, rate: e.target.value })}
            className="w-full mt-1 bg-transparent border border-[var(--border-color)] px-2 py-1 text-xs font-mono"
          />
        </div>
        <div>
          <label className="text-[10px] uppercase tracking-widest font-[Orbitron] text-[var(--text-muted)]">
            Pitch
          </label>
          <input
            value={draft.pitch}
            onChange={(e) => setDraft({ ...draft, pitch: e.target.value })}
            className="w-full mt-1 bg-transparent border border-[var(--border-color)] px-2 py-1 text-xs font-mono"
          />
        </div>
        <div>
          <label className="text-[10px] uppercase tracking-widest font-[Orbitron] text-[var(--text-muted)]">
            Volume
          </label>
          <input
            value={draft.volume}
            onChange={(e) => setDraft({ ...draft, volume: e.target.value })}
            className="w-full mt-1 bg-transparent border border-[var(--border-color)] px-2 py-1 text-xs font-mono"
          />
        </div>
      </div>

      {allErrors.length > 0 && (
        <p
          data-testid="tts-validation-error"
          className="text-[10px] text-[var(--danger)] font-mono"
        >
          {allErrors[0].message}
        </p>
      )}

      <Button
        onClick={() => onSubmit(draft)}
        disabled={busy}
        data-testid="tts-next"
      >
        {busy ? "Saving…" : "Next →"}
      </Button>
    </div>
  );
}

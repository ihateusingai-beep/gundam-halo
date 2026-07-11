/**
 * StepVoiceASR — Wizard step 3. Pick voice ASR backend.
 *
 * Three backends:
 *   - whisper_local (default) — openai-whisper, base/small/medium/large
 *   - sherpa                  — sherpa-onnx for offline ASR
 *   - yuesub                  — Cantonese-specific (SenseVoice + fsmn-vad)
 *
 * For whisper_local the user picks model_size; for sherpa/yuesub
 * they supply a model_path. device is cpu/cuda/mps (mps recommended
 * on Apple Silicon).
 */

import { useState } from "react";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { useStepValidation } from "@/hooks/useStepValidation";
import { cn } from "@/lib/utils";
import type { VoiceASRConfig } from "@/types/api";
import type { WizardError } from "@/hooks/useSetupWizard";

/** Sprint 64 W-A4 (migrate 2): Zod schema for StepVoiceASR.
 *  Mirrors the StepLLM pilot. The other 4 wizard steps
 *  still use hand-rolled validation (deferred to Sprint 65+). */
const asrSchema = z.object({
  backend: z.enum(["whisper_local", "sherpa", "yuesub"]),
  model_size: z.string().min(1, "Model size is required"),
  model_path: z.string().optional(),
  device: z.enum(["cpu", "cuda", "mps"]),
});

export interface StepVoiceASRProps {
  form: VoiceASRConfig;
  onSubmit: (cfg: VoiceASRConfig) => Promise<void>;
  errors: WizardError[];
  busy: boolean;
}

const MODEL_SIZES = ["tiny", "base", "small", "medium", "large-v3"];

export function StepVoiceASR({ form, onSubmit, errors, busy }: StepVoiceASRProps) {
  const [draft, setDraft] = useState<VoiceASRConfig>(form);
  // Sprint 64 W-A4: Zod validation. Zod errors take precedence
  // over backend errors for the same field (same pattern as
  // StepLLM).
  const zodValidation = useStepValidation(asrSchema, draft);
  const allErrors: WizardError[] = [
    ...zodValidation.errors.map((e) => ({
      field: e.field,
      code: "zod",
      message: e.message,
    })),
    ...errors,
  ];

  const needsModelSize = draft.backend === "whisper_local";
  const needsModelPath =
    draft.backend === "sherpa" || draft.backend === "yuesub";

  return (
    <div className="space-y-3 py-2" data-testid="step-voice-asr">
      <h2 className="text-lg font-[Rajdhani] text-[var(--text-primary)]">
        Voice Speech-to-Text
      </h2>

      <div className="grid grid-cols-3 gap-2">
        {(["whisper_local", "sherpa", "yuesub"] as const).map((b) => (
          <button
            key={b}
            data-testid={`asr-backend-${b}`}
            onClick={() => setDraft({ ...draft, backend: b })}
            className={cn(
              "border px-3 py-2 text-left transition-colors",
              draft.backend === b
                ? "border-[var(--accent)] bg-[var(--accent)]/10"
                : "border-[var(--border-color)] hover:border-[var(--text-secondary)]",
            )}
          >
            <div className="text-xs font-mono font-bold">{b}</div>
            <div className="text-[10px] text-[var(--text-muted)] mt-0.5">
              {b === "whisper_local" && "openai-whisper"}
              {b === "sherpa" && "sherpa-onnx (offline)"}
              {b === "yuesub" && "Cantonese-specific"}
            </div>
          </button>
        ))}
      </div>

      {needsModelSize && (
        <div>
          <label className="text-[10px] uppercase tracking-widest font-[Orbitron] text-[var(--text-muted)]">
            Model Size
          </label>
          <select
            data-testid="asr-model-size"
            value={draft.model_size ?? "base"}
            onChange={(e) => setDraft({ ...draft, model_size: e.target.value })}
            className="w-full mt-1 bg-transparent border border-[var(--border-color)] px-2 py-1 text-sm font-mono focus:border-[var(--accent)] outline-none"
          >
            {MODEL_SIZES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
          <p className="text-[10px] text-[var(--text-muted)] font-mono mt-0.5">
            Larger models are more accurate but slower. Default "base" runs
            in &lt;1s on Apple Silicon.
          </p>
        </div>
      )}

      {needsModelPath && (
        <div>
          <label className="text-[10px] uppercase tracking-widest font-[Orbitron] text-[var(--text-muted)]">
            Model Path
          </label>
          <input
            value={draft.model_path ?? ""}
            onChange={(e) => setDraft({ ...draft, model_path: e.target.value })}
            placeholder="~/.cache/huggingface/…/model.onnx"
            className="w-full mt-1 bg-transparent border border-[var(--border-color)] px-2 py-1 text-xs font-mono focus:border-[var(--accent)] outline-none"
          />
        </div>
      )}

      <div>
        <label className="text-[10px] uppercase tracking-widest font-[Orbitron] text-[var(--text-muted)]">
          Device
        </label>
        <div className="flex gap-2 mt-1">
          {(["cpu", "mps", "cuda"] as const).map((d) => (
            <button
              key={d}
              data-testid={`asr-device-${d}`}
              onClick={() => setDraft({ ...draft, device: d })}
              className={cn(
                "px-3 py-1 text-xs font-mono border",
                draft.device === d
                  ? "border-[var(--accent)] text-[var(--accent)]"
                  : "border-[var(--border-color)] text-[var(--text-muted)]",
              )}
            >
              {d}
            </button>
          ))}
        </div>
        <p className="text-[10px] text-[var(--text-muted)] font-mono mt-1">
          mps (Apple GPU) is recommended on M1/M2/M3 Macs.
        </p>
      </div>

      <Button
        onClick={() => onSubmit(draft)}
        disabled={busy}
        data-testid="asr-next"
      >
        {busy ? "Saving…" : "Next →"}
      </Button>
    </div>
  );
}

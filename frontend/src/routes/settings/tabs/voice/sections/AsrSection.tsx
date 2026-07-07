/**
 * AsrSection — ASR engine + corrector pickers + restart hint.
 *
 * Extracted from VoiceTab.tsx (Sprint 56.7). Three logical
 * sub-blocks:
 *
 *   1. ASR engine radio (3 options: whisper_local / yuesub /
 *      whisper_hf). Changing this requires a backend restart
 *      because the ASR engine is loaded at startup.
 *
 *   2. Corrector radio (3 options: bert / opencc / none).
 *      Only applies to the yuesub backend. Switching between
 *      corrector values also flips `restart_required`.
 *
 *   3. Restart-required banner: shown when the persisted
 *      config has `restart_required=true` (the PUT call
 *      flipped it because a change happened). Tells the user
 *      the manual restart command.
 *
 * Sprint 18 added the editable radios; Sprint 23 added the
 * `whisper_hf` option for fine-tuned HF checkpoints. The radio
 * chrome is the shared `RadioOption` component (also used by
 * AlwaysOnSection).
 */
import { Section } from "../../../shared";

import { RadioOption } from "../RadioOption";
import type { VoiceSectionsStore } from "../types";

export function AsrSection({ store }: { store: VoiceSectionsStore }) {
  const { config, asrBackend, setAsrBackend, asrCorrector, setAsrCorrector } =
    store;

  return (
    <>
      <Section title="ASR engine (Sprint 18)">
        {/* Sprint 17b: read-only display of the current ASR engine
            and corrector.
            Sprint 18: the section is now EDITABLE. Two radio
            groups — one for the engine, one for the corrector —
            bound to asrBackend / asrCorrector drafts. Save
            (at the bottom of the form) dispatches all four
            fields in one PUT; the backend persists, validates,
            and flips the `restart_required` flag if either asr
            field actually changed. */}
        <p className="text-xs text-[var(--text-secondary)] font-mono mb-2">
          Choose the speech-recognition backend. <strong>whisper_local</strong>{" "}
          is the default (openai-whisper base, English / Mandarin).
          <strong> yuesub</strong> uses SenseVoiceSmall + fsmn-vad for
          Cantonese.
          <strong> whisper_hf</strong> uses a fine-tuned HuggingFace
          checkpoint (M9-E Layer 2 — see Personalised Fine-tune
          below). Changing this requires a backend restart.
        </p>
        <div className="flex flex-col gap-1.5" data-testid="asr-backend-radios">
          <RadioOption
            name="asr-backend"
            value="whisper_local"
            checked={asrBackend === "whisper_local"}
            onChange={() => setAsrBackend("whisper_local")}
            label="whisper_local"
            hint="— openai-whisper (English / Mandarin)"
          />
          <RadioOption
            name="asr-backend"
            value="yuesub"
            checked={asrBackend === "yuesub"}
            onChange={() => setAsrBackend("yuesub")}
            label="yuesub"
            hint="— SenseVoiceSmall + fsmn-vad (Cantonese)"
          />
          <RadioOption
            name="asr-backend"
            value="whisper_hf"
            checked={asrBackend === "whisper_hf"}
            onChange={() => setAsrBackend("whisper_hf")}
            label="whisper_hf"
            hint="— fine-tuned HF checkpoint (M9-E Layer 2)"
          />
        </div>
      </Section>

      <Section title="Corrector (Sprint 18)">
        <p className="text-xs text-[var(--text-secondary)] font-mono mb-2">
          Post-process the ASR output. <strong>bert</strong> uses
          OpenCC + BERT masked-LM (slow, 300-500ms per segment but
          high quality). <strong>opencc</strong> uses OpenCC + regex
          rules (fast, &lt;5ms). <strong>none</strong> skips the
          corrector entirely. Only applies to the yuesub backend.
        </p>
        <div className="flex flex-col gap-1.5" data-testid="asr-corrector-radios">
          <RadioOption
            name="asr-corrector"
            value="bert"
            checked={asrCorrector === "bert"}
            onChange={() => setAsrCorrector("bert")}
            label="bert"
            hint="— OpenCC + BERT masked-LM (slow but high quality)"
          />
          <RadioOption
            name="asr-corrector"
            value="opencc"
            checked={asrCorrector === "opencc"}
            onChange={() => setAsrCorrector("opencc")}
            label="opencc"
            hint="— OpenCC + regex rules (fast)"
          />
          <RadioOption
            name="asr-corrector"
            value="none"
            checked={asrCorrector === "none"}
            onChange={() => setAsrCorrector("none")}
            label="none"
            hint="— Raw ASR output"
          />
        </div>
      </Section>

      {config?.restart_required && (
        <div
          className="mt-2 mb-3 border border-[var(--warning)] bg-[var(--bg-elevated)] px-3 py-2 text-xs font-mono"
          data-testid="restart-required-banner"
        >
          <span className="text-[var(--warning)]">⚠ Restart required:</span>{" "}
          <span className="text-[var(--text-primary)]">
            config.toml changed but the running backend still
            uses the pre-restart instance. Restart with{" "}
            <code>pkill -f &apos;uvicorn app.main:app&apos; &amp;&amp; uv run --project . uvicorn app.main:app</code>{" "}
            for the new ASR engine / corrector to take effect.
          </span>
        </div>
      )}
    </>
  );
}

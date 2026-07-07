/**
 * AlwaysOnSection — Voice interaction mode picker.
 *
 * Extracted from VoiceTab.tsx (Sprint 56.7). Two-state radio:
 * push-to-talk (default) vs always-on mic.
 *
 * Sprint 19c added this section. The toggle is runtime-tunable
 * (no restart required) — the change persists via the same
 * PUT round-trip as the wake phrases + ASR engine +
 * corrector. The cockpit shows a ⏸ toggle to pause when
 * always-on is enabled.
 *
 * The `value="always-on"` / `value="push-to-talk"` strings are
 * the legacy form field names from Sprint 19c — kept verbatim
 * for git-blame continuity. Internally we bind a single
 * `alwaysOnMic: boolean` draft state.
 */
import { Section } from "../../../shared";

import { RadioOption } from "../RadioOption";
import type { VoiceSectionsStore } from "../types";

export function AlwaysOnSection({ store }: { store: VoiceSectionsStore }) {
  const { alwaysOnMic, setAlwaysOnMic } = store;
  return (
    <Section title="Voice interaction mode (Sprint 19c)">
      {/* Sprint 19c: choose between push-to-talk (the
          default) and always-on mic. Always-on auto-
          fires the agent on the backend's VAD
          speech_start event; the cockpit shows a ⏸
          toggle to pause. Runtime-tunable — no
          restart required. */}
      <p className="text-xs text-[var(--text-secondary)] font-mono mb-2">
        Choose how the cockpit captures your voice.
        <strong> Push-to-talk</strong> keeps the mic
        closed until you press and hold the 🎤 button
        (lowest power, most private).
        <strong> Always-on</strong> keeps the mic open
        and uses the backend's VAD to detect when you
        start talking; the agent fires automatically.
        A small ⏸ toggle appears in the cockpit when
        always-on is enabled.
      </p>
      <div className="flex flex-col gap-1.5" data-testid="voice-interaction-mode-radios">
        <RadioOption
          name="voice-interaction-mode"
          value="push-to-talk"
          checked={!alwaysOnMic}
          onChange={() => setAlwaysOnMic(false)}
          label="Push-to-talk"
          hint="— hold the mic button to talk (default)"
        />
        <RadioOption
          name="voice-interaction-mode"
          value="always-on"
          checked={alwaysOnMic}
          onChange={() => setAlwaysOnMic(true)}
          label="Always-on"
          hint="— mic always live; VAD auto-fires the agent"
        />
      </div>
    </Section>
  );
}

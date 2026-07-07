/**
 * WakeSection — wake-phrase textarea + strict-mode checkbox.
 *
 * Extracted from VoiceTab.tsx (Sprint 56.7). Two sub-blocks:
 *
 *   1. The textarea — one phrase per line. Empty lines are
 *      ignored server-side. Default hints
 *      (`Unicorn / NTD / gundam / 獨角獸 / 高達`) are shown
 *      as the placeholder.
 *
 *   2. The strict-mode checkbox (Sprint 17a). When ON
 *      (default), voice turns whose ASR transcript doesn't
 *      start with a configured wake phrase are discarded
 *      server-side. When OFF, the wake phrase is just a
 *      confidence marker in MissionLog.
 *
 * Default phrase list (placeholder) matches the user's
 * Halo profile memory default (`["Unicorn", "NTD", "gundam",
 * "獨角獸", "高達"]`).
 */
import { Section } from "../../../shared";

import type { VoiceSectionsStore } from "../types";

export function WakeSection({ store }: { store: VoiceSectionsStore }) {
  const { config, draft, setDraft, strictDraft, setStrictDraft } = store;

  return (
    <>
      <Section title="Wake phrases (Sprint 16)">
        <p className="text-xs text-[var(--text-secondary)] font-mono mb-2">
          When you hold the mic button, the ASR transcript is checked
          against these phrases at the start. If one matches, the
          prefix is stripped and the turn is tagged as
          wake-triggered in the MissionLog.
        </p>
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          spellCheck={false}
          rows={Math.max(4, (config?.wake_phrases.length ?? 0) + 2)}
          className="w-full bg-[var(--bg-input)] border border-[var(--border-color)] rounded px-2 py-1.5 text-xs font-mono text-[var(--text-primary)] focus:outline-none focus:border-[var(--accent)] placeholder:text-[var(--text-muted)]/50"
          placeholder="Unicorn&#10;NTD&#10;gundam&#10;獨角獸&#10;高達"
        />
      </Section>

      <Section title="Wake-phrase gate (Sprint 17a)">
        <p className="text-xs text-[var(--text-secondary)] font-mono mb-3">
          When strict mode is <strong>on</strong> (the default), voice
          turns are discarded unless the ASR transcript starts with
          one of the configured wake phrases above. When{" "}
          <strong>off</strong>, the agent runs on every transcript;
          the wake phrase is just a confidence marker. Both settings
          apply to push-to-talk and the voice text-input field.
        </p>
        <label className="flex items-center gap-2 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={strictDraft}
            onChange={(e) => setStrictDraft(e.target.checked)}
            className="w-4 h-4 accent-[var(--accent)] cursor-pointer"
            data-testid="strict-wake-checkbox"
          />
          <span className="text-xs font-mono text-[var(--text-primary)]">
            Strict mode (only fire on a wake phrase)
          </span>
        </label>
      </Section>
    </>
  );
}

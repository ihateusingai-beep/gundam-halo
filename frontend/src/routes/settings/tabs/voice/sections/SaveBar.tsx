/**
 * SaveBar — Save + Reset buttons + the current-config status span.
 *
 * Extracted from VoiceTab.tsx (Sprint 56.7). Owning the
 * Save/Reset handlers in VoiceTab.tsx (not here) is
 * intentional: those handlers read ALL drafts (`draft`,
 * `strictDraft`, `asrBackend`, `asrCorrector`, `alwaysOnMic`)
 * and dispatch a single PUT to the backend. The SaveBar only
 * needs the `saving` flag + the two action refs.
 */
import type { VoiceSectionsStore } from "../types";

export function SaveBar({ store }: { store: VoiceSectionsStore }) {
  const { config, saving, handleSave, handleReset } = store;

  return (
    <div className="flex items-center gap-2 mt-3 flex-wrap">
      <button
        type="button"
        onClick={handleSave}
        disabled={saving}
        data-testid="voice-save-button"
        className="px-3 py-1 text-[10px] uppercase tracking-wider font-[Rajdhani] border border-[var(--accent)] text-[var(--accent)] bg-[var(--bg-elevated)] hover:bg-[var(--accent)] hover:text-[var(--bg-primary)] transition-colors disabled:opacity-40"
      >
        {saving ? "Saving…" : "Save"}
      </button>
      <button
        type="button"
        onClick={handleReset}
        disabled={saving}
        data-testid="voice-reset-button"
        className="px-3 py-1 text-[10px] uppercase tracking-wider font-[Rajdhani] border border-[var(--border-color)] text-[var(--text-muted)] hover:border-[var(--accent)] hover:text-[var(--accent)] transition-colors disabled:opacity-40"
      >
        Reset
      </button>
      {config && (
        <span
          className="text-[10px] text-[var(--text-muted)] font-mono"
          data-testid="voice-config-summary"
        >
          {config.wake_phrases.length} phrase(s) · gate:{" "}
          {config.strict_wake_phrase ? "strict" : "permissive"}
        </span>
      )}
    </div>
  );
}

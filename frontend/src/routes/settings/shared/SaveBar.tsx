/**
 * SaveBar — shared Save/Reset button group for settings tabs.
 *
 * Sprint 60 S-A4. Extracted from `routes/settings/tabs/voice/sections/
 * SaveBar.tsx` (which used a `VoiceSectionsStore`-specific shape)
 * into a generic component that any settings tab can adopt.
 *
 * ## Behaviour
 *
 *  Renders three controls (Save, Reset, optional summary span):
 *
 *    [ Save ] [ Reset ]   (when resetLabel provided)
 *    [ Save ]              (when onReset not provided)
 *
 *  - `dirty=true`   → Save enabled, Reset enabled
 *  - `dirty=false`  → Save DISABLED (via `aria-disabled`, not `disabled`,
 *                      so screen readers keep tab order), Reset enabled
 *                      (resets to last-saved state — still useful when
 *                      the user has been editing)
 *  - `saving=true`  → both buttons show "Saving…" + disabled + spinner
 *
 *  The optional `summary` slot is a freeform span rendered after
 *  the buttons — used by VoiceTab to show "5 phrase(s) · gate: strict"
 *  as a "current config at a glance" affordance.
 *
 * ## a11y contract
 *
 *  - Save button uses `aria-disabled={!dirty || saving}` instead
 *    of native `disabled`. This keeps the button in the tab order
 *    so keyboard users can still focus it (to read the
 *    `aria-label`), but click handlers are short-circuited.
 *  - Reset button uses native `disabled` when `saving` (no
 *    data-testid attribute change is required — saves are atomic).
 *  - Both buttons carry a `data-testid` so per-tab tests can target
 *    them without coupling to label text (which i18n may change).
 *
 * ## Why a separate component
 *
 *  Per the Sprint 50 standing rule, every per-tab affordance that
 *  appears in 2+ tabs should be a shared component. SaveBar was
 *  originally only in VoiceTab (Sprint 56.7). Sprint 60 promotes
 *  it to shared + adopts in 7 more tabs (General / Mac / Channels /
 *  Memory / Secrets / Security / Themes).
 *
 *  Pre-Sprint 60 cost: each tab had its own ~30 LoC inline
 *  Save/Reset block (inconsistent copy, inconsistent button states,
 *  inconsistent disabled semantics). Post-Sprint 60: 8 tabs share
 *  ~60 LoC of well-tested code.
 */

import type { ReactNode } from "react";

export interface SaveBarProps {
  /** True when the form has unsaved changes. Save is enabled
   *  iff dirty && !saving. */
  dirty: boolean;
  /** True while a save request is in flight. Disables both buttons
   *  + shows a "Saving…" label. */
  saving: boolean;
  /** Click handler for the Save button. */
  onSave: () => void;
  /** Click handler for the Reset button (optional — when omitted,
   *  the Reset button is not rendered at all). */
  onReset?: () => void;
  /** Override the Save button label. Default: "Save". */
  saveLabel?: string;
  /** Override the Reset button label. Default: "Reset". */
  resetLabel?: string;
  /** Freeform summary rendered after the buttons (e.g. config echo).
   *  Use sparingly — it's a status hint, not a status report. */
  summary?: ReactNode;
  /** Test id override for the Save button (default: "save-bar-save"). */
  saveTestId?: string;
  /** Test id override for the Reset button (default: "save-bar-reset"). */
  resetTestId?: string;
}

export function SaveBar({
  dirty,
  saving,
  onSave,
  onReset,
  saveLabel = "Save",
  resetLabel = "Reset",
  summary,
  saveTestId = "save-bar-save",
  resetTestId = "save-bar-reset",
}: SaveBarProps) {
  const saveDisabled = !dirty || saving;

  return (
    <div className="flex items-center gap-2 mt-3 flex-wrap">
      <button
        type="button"
        onClick={() => {
          if (saveDisabled) return;
          void onSave();
        }}
        aria-disabled={saveDisabled}
        data-testid={saveTestId}
        className="px-3 py-1 text-[10px] uppercase tracking-wider font-[Rajdhani] border border-[var(--accent)] text-[var(--accent)] bg-[var(--bg-elevated)] hover:bg-[var(--accent)] hover:text-[var(--bg-primary)] transition-colors disabled:opacity-40 aria-disabled:opacity-40 aria-disabled:pointer-events-none"
      >
        {saving ? "Saving…" : saveLabel}
      </button>
      {onReset && (
        <button
          type="button"
          onClick={onReset}
          disabled={saving}
          data-testid={resetTestId}
          className="px-3 py-1 text-[10px] uppercase tracking-wider font-[Rajdhani] border border-[var(--border-color)] text-[var(--text-muted)] hover:border-[var(--accent)] hover:text-[var(--accent)] transition-colors disabled:opacity-40"
        >
          {resetLabel}
        </button>
      )}
      {summary && (
        <span
          className="text-[10px] text-[var(--text-muted)] font-mono"
          data-testid="save-bar-summary"
        >
          {summary}
        </span>
      )}
    </div>
  );
}
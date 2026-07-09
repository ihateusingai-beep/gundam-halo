/**
 * RailToggle — small standalone component used by
 * CockpitLayout for Sprint 49 #5 (right-rail collapse).
 *
 * Extracted as a leaf component so it can be unit-tested
 * without dragging in the full CockpitLayout provider tree
 * (which has 20+ Tauri-only hooks and Zustand stores). The
 * state is hoisted to the parent (CockpitLayout) in
 * production; the component here owns its own state in
 * isolation (test-only path) so the test doesn't need to
 * wire the full context.
 *
 * `RAIL_KEY` is exported so the parent CockpitLayout can
 * read the same key when it needs to react to the toggle
 * (e.g. for the `grid-cols-[200px_1fr_48px]` vs
 * `grid-cols-[200px_1fr_240px]` layout swap).
 */
import { useEffect, useState } from "react";

export const RAIL_KEY = "halo.cockpit.railExpanded.v1";

/** Toggle button for the cockpit's right-rail (Sprint 49 #5).
 *
 *  Renders a thin (h-8) horizontal button at the top of the
 *  right rail. Click flips `expanded` state and the arrow
 *  icon (`→` collapsed / `←` expanded).
 *
 *  Owns its own state — does NOT accept `expanded` /
 *  `onChange` props. State persists to localStorage at
 *  `RAIL_KEY` (schema-versioned for future migrations).
 *
 *  Production mounting: `CockpitLayout` mounts this inside
 *  the right rail and reads the SAME key to derive its
 *  3-column grid template (`200px_1fr_48px` collapsed vs.
 *  `200px_1fr_240px` expanded). The two components don't
 *  share a parent state — they coordinate via localStorage.
 *  See `CockpitLayout.tsx::railExpanded` for the parent.
 *
 *  Test mounting: `CockpitLayout.test.tsx` mounts this
 *  component in isolation (without the full layout) and
 *  asserts the localStorage round-trip and aria-label flip.
 *  No provider tree required.
 *
 *  Accessibility:
 *    - `aria-label` toggles between "Collapse right rail"
 *      and "Expand right rail" so screen-reader users hear
 *      the current action.
 *    - `data-expanded="0|1"` is a test hook (NOT for styling
 *      — the styling is done via the aria-label-derived
 *      `expanded` state).
 *    - `data-testid="rail-toggle"` for unit tests.
 *
 *  Edge cases:
 *    - SSR / no window: state initialised to `false`. Effect
 *      short-circuits when `window` is undefined.
 *    - localStorage disabled (private mode): reads return
 *      `false` (catch-all), writes silently fail.
 */
export function RailToggle() {
  const [expanded, setExpanded] = useState<boolean>(() => {
    if (typeof window === "undefined") return false;
    try {
      return window.localStorage.getItem(RAIL_KEY) === "1";
    } catch {
      return false;
    }
  });

  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      window.localStorage.setItem(RAIL_KEY, expanded ? "1" : "0");
    } catch {
      /* localStorage disabled — silently ignore */
    }
  }, [expanded]);

  return (
    <button
      type="button"
      onClick={() => setExpanded((v) => !v)}
      aria-label={expanded ? "Collapse right rail" : "Expand right rail"}
      data-testid="rail-toggle"
      data-expanded={expanded ? "1" : "0"}
      className="w-full h-8 flex items-center justify-center text-[var(--text-muted)] hover:text-[var(--accent)] border border-dashed border-[var(--border-color)] hover:border-[var(--accent)] transition-colors text-xs"
    >
      {expanded ? "→" : "←"}
    </button>
  );
}

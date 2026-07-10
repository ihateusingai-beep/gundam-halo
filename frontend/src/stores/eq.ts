/**
 * useEqStore — per-USER EQ preset override.
 *
 * Sprint 62 A-A2. Pre-existing: `applyEqPreset` was keyed
 * strictly on the active theme — users who like SEED's
 * theme but want NT-D's tighter highs couldn't have it.
 *
 * This store separates the *theme* (visual identity) from
 * the *EQ preset* (audio character). The user can:
 *   1. Pick a theme (visual) — `useThemeStore.setTheme`
 *   2. Override the EQ preset (audio) — `useEqStore.setPreset`
 *   3. Revert the override — `useEqStore.resetToThemePreset`
 *
 * The visualizer (CockpitEqCard) reads `getActivePreset(theme)`
 * to get the effective preset — the override if set, else
 * the theme's default.
 *
 * ## Persistence
 *
 * The override is **session-only** (NOT persisted to
 * localStorage in Sprint 62). Page reload resets the
 * override; the user must re-set it. This is intentional —
 * the override is a "today's vibe" affordance, not a
 * permanent config. Adding localStorage persistence is
 * deferred to Sprint 63+ (UX review needed first).
 *
 * ## API
 *
 *   ```ts
 *   const preset = useEqStore((s) => s.currentPreset);
 *   const setPreset = useEqStore((s) => s.setPreset);
 *   const reset = useEqStore((s) => s.resetToThemePreset);
 *   const active = useEqStore.getState().getActivePreset(theme);
 *   ```
 */
import { create } from "zustand";

import { getEqPreset, type EqPreset } from "@/lib/audio-eq";

interface EqState {
  /** The active override. `null` = "no override, use the
   *  theme's preset". Non-null = "use this preset regardless
   *  of theme". */
  override: EqPreset | null;

  /** Set a custom EQ preset. Pass any EqPreset (the 8 hard-
   *  coded theme presets, or a future user-defined one).
   *  Setting to `null` clears the override (equivalent to
   *  `resetToThemePreset`). */
  setPreset: (p: EqPreset | null) => void;

  /** Revert to the theme-derived preset. */
  resetToThemePreset: () => void;

  /** Compute the effective preset for a given theme id.
   *  Returns the override if set, else the theme's preset.
   *  If `themeId` is null, returns the "Flat" fallback. */
  getActivePreset: (themeId: string | null) => EqPreset;
}

export const useEqStore = create<EqState>((set, get) => ({
  override: null,

  setPreset: (p) => set({ override: p }),

  resetToThemePreset: () => set({ override: null }),

  getActivePreset: (themeId) => {
    const override = get().override;
    return override ?? getEqPreset(themeId);
  },
}));

/** Helper for non-React callers (e.g. VoicePanel's
 *  TtsAudioGraph integration, which is outside React).
 *  Equivalent to `useEqStore.getState().getActivePreset(theme)`. */
export function getActiveEqPreset(themeId: string | null): EqPreset {
  return useEqStore.getState().getActivePreset(themeId);
}
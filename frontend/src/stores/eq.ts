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
 * ## Persistence (Sprint 67 C-A1)
 *
 * The override is now **persisted to localStorage** with a
 * schema-versioned key (`halo.eq.override.v1` — see
 * `@/stores/eq.schema`). On mount, the store reads the
 * key; if present + valid, the override is restored.
 *
 * Sprint 62's standing rule was "session-only by default";
 * Sprint 67 reverses that for EQ (the user has been
 * requesting persistence since Sprint 62). The default
 * is now "persisted, opt-out via Reset".
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

import { EQ_OVERRIDE_LS_KEY, persistedEqOverrideSchema } from "./eq.schema";

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

// ---------------------------------------------------------------------------
// localStorage I/O (Sprint 67 C-A1)
// ---------------------------------------------------------------------------

/** Read the persisted override from localStorage. Returns
 *  `null` if the key is missing OR the stored value fails
 *  Zod validation. Logs a warning on parse failure. */
function readPersistedOverride(): EqPreset | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(EQ_OVERRIDE_LS_KEY);
    if (raw == null) return null;
    const parsed: unknown = JSON.parse(raw);
    const result = persistedEqOverrideSchema.safeParse(parsed);
    if (!result.success) {
      console.warn(
        `[useEqStore] persisted override failed schema validation, ignoring. errors=${result.error.message}`,
      );
      return null;
    }
    return result.data;
  } catch (e) {
    console.warn("[useEqStore] failed to read persisted override:", e);
    return null;
  }
}

/** Write the override to localStorage. Pass `null` to
 *  remove the key (the "no override" state). */
function writePersistedOverride(preset: EqPreset | null): void {
  if (typeof window === "undefined") return;
  try {
    if (preset == null) {
      window.localStorage.removeItem(EQ_OVERRIDE_LS_KEY);
    } else {
      window.localStorage.setItem(
        EQ_OVERRIDE_LS_KEY,
        JSON.stringify(preset),
      );
    }
  } catch (e) {
    console.warn("[useEqStore] failed to write persisted override:", e);
  }
}

export const useEqStore = create<EqState>((set, get) => ({
  // Sprint 67 C-A1: hydrate from localStorage on store init.
  // Zustand's create() runs the initializer eagerly, so the
  // first React render sees the persisted value (or null).
  override: readPersistedOverride(),

  setPreset: (p) => {
    writePersistedOverride(p);
    set({ override: p });
  },

  resetToThemePreset: () => {
    writePersistedOverride(null);
    set({ override: null });
  },

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

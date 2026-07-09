/**
 * theme-bg-constants.ts — Single source of truth for per-theme
 * cockpit-background mapping.
 *
 * Lives in its own file so BOTH `stores/theme.ts` (the store
 * action that cascades bg on `setTheme`) AND
 * `routes/settings/constants.ts` (the wizard selector that
 * reads the same map) can import without forming a cycle.
 *
 * ## Why this exists
 *
 * Prior to Sprint 58 Phase 4, the cockpit background slug and
 * the cockpit asset path were decoupled — `data-bg="core-01"`
 * always meant `/gundam-assets/backgrounds/bg-unicorn-core-01.jpg`
 * regardless of the active theme. After Phase 4, every theme
 * has its own hero artwork, so we need to know:
 *
 *   "if theme = gundam-seed and bg = core-01, what's the file?"
 *
 *   →  /gundam-assets/backgrounds/bg-seed-core-01.jpg
 *
 * The mapping rule is:
 *
 *   bg-<themeSlug>-<bgSlug>.jpg
 *
 * where themeSlug = themeId.replace(/^gundam-/, "") (e.g.
 * "gundam-seed" → "seed"). Unknown themes fall back to the
 * NT-D Unicorn baseline (`bg-unicorn-<bgSlug>.jpg`).
 */
import type { GundamTheme } from "@/types/api";

/** All theme ids that ship with a per-theme cockpit background.
 *  Adding a new theme here + dropping a `<theme>-core-01..04.jpg`
 *  asset into `/public/gundam-assets/backgrounds/` is the
 *  full wire-up needed; no other code change required.
 *
 *  Typed as `readonly GundamTheme[]` so the Set constructor
 *  inherits the right element type without a separate generic
 *  (the `Set<GundamTheme>` constructor was complaining because
 *  `GundamTheme` includes `null`, which doesn't match the
 *  literal string union).
 *
 *  NT-D is INTENTIONALLY OMITTED — its assets live at the
 *  bare `/gundam-assets/backgrounds/bg-unicorn-core-XX.jpg`
 *  (the 4 legacy Unicorn variants from before Sprint 58). The
 *  "unicorn" slug is the historical NT-D identifier — keeping
 *  that name preserves continuity with the Sprint 16-57 era
 *  where the cockpit was always Unicorn NT-D.
 */
export const THEMES_WITH_BG_SET: ReadonlySet<GundamTheme> = new Set([
  // gundam-ntd excluded — uses bg-unicorn-core-XX.jpg legacy
  "gundam-seed",
  "gundam-crossbone",
  "gundam-ntd-green",
  "gundam-00",
  "gundam-destiny",
  "gundam-god",
  "gundam-cartoon",
  "gundam-halo",
]);

/** Default bg slug per theme id. Every theme currently maps
 *  to `core-01` (we ship one hero per theme in Sprint 58 Phase
 *  2; the 4-variant `core-02..04` per-theme set is Phase 2.5
 *  — out of scope here). NT-D intentionally absent — its
 *  default is the historical `core-01` Unicorn baseline (the
 *  fallback `defaultBgForTheme` returns). */
export type CockpitBgSlug = "none" | "core-01" | "core-02" | "core-03" | "core-04";
export const THEME_DEFAULT_BG: Record<string, CockpitBgSlug> = {
  "gundam-seed": "core-01",
  "gundam-crossbone": "core-01",
  "gundam-ntd-green": "core-01",
  "gundam-00": "core-01",
  "gundam-destiny": "core-01",
  "gundam-god": "core-01",
  "gundam-cartoon": "core-01",
  "gundam-halo": "core-01",
};

/** Resolve the default cockpit background slug for a given
 *  theme id. Returns `"core-01"` (the historical NT-D Unicorn
 *  default) for unknown / unset themes. */
export function defaultBgForTheme(themeId: string | null | undefined): CockpitBgSlug {
  if (themeId && themeId in THEME_DEFAULT_BG) {
    return THEME_DEFAULT_BG[themeId];
  }
  return "core-01";
}

/** Resolve the `<theme>` directory slug used in the asset path.
 *  NT-D and unknown themes both return `"unicorn"` (the legacy
 *  NT-D Unicorn baseline). Every other known theme returns
 *  its bare slug (e.g. "gundam-seed" → "seed"). */
export function themeAssetSlug(themeId: string | null | undefined): string {
  if (themeId && THEMES_WITH_BG_SET.has(themeId as GundamTheme)) {
    return themeId.replace(/^gundam-/, "");
  }
  return "unicorn";
}

/** Build the per-theme asset path: `/gundam-assets/backgrounds/bg-<themeSlug>-<bgSlug>.jpg`. */
export function resolveBgAsset(
  bgSlug: CockpitBgSlug,
  themeId: string | null | undefined,
): string | null {
  if (bgSlug === "none") return null;
  return `/gundam-assets/backgrounds/bg-${themeAssetSlug(themeId)}-${bgSlug}.jpg`;
}
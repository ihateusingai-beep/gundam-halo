/**
 * Avatar asset paths — single source of truth for the theme-keyed
 * avatar directory + per-theme emotion PNG URLs.
 *
 * Sprint 58 NEW. Previously hard-coded in `ImageSetAvatar.tsx`;
 * extracted so the wizard (StepTheme) and the audit docs can
 * read the same mapping without importing React components.
 *
 * ## Mapping
 *
 *   themeId          →  directory         →  path for emotion
 *   ----------------------------------------------------------------
 *   null             →  emotions/         →  /avatars/emotions/<emotion>.png
 *   "gundam-ntd"     →  emotions/         →  /avatars/emotions/<emotion>.png
 *   "gundam-seed"    →  emotions-seed/    →  /avatars/emotions-seed/<emotion>.png
 *   "gundam-ntd-green"→ emotions-ntd-green/→  /avatars/emotions-ntd-green/<emotion>.png
 *   "gundam-00"      →  emotions-00/      →  /avatars/emotions-00/<emotion>.png
 *   "gundam-destiny"  →  emotions-destiny/ →  /avatars/emotions-destiny/<emotion>.png
 *   "gundam-god"      →  emotions-god/     →  /avatars/emotions-god/<emotion>.png
 *   "gundam-crossbone"→ emotions-crossbone/ (3 PNGs only; not a full set)
 *
 * Each set has 9 emotion PNGs (idle / listening / thinking /
 * speaking / warning / damage / joy / sad / confused). Themes
 * NOT in the set fall back to the NT-D Unicorn baseline.
 */

const THEMES_WITH_AVATAR_SET: ReadonlySet<string> = new Set([
  // gundam-ntd is INTENTIONALLY omitted — its assets live at the
  // bare /avatars/emotions/ directory (the legacy NT-D Unicorn
  // baseline set, which we kept when introducing the per-theme
  // directories in Sprint 57). Adding it here would route NT-D
  // to a non-existent /avatars/emotions-ntd/ and break the
  // cockpit with broken-image icons.
  "gundam-seed", // Sprint 57
  "gundam-ntd-green", // Sprint 58 A1
  "gundam-00", // Sprint 58 A1
  "gundam-destiny", // Sprint 58 A1
  "gundam-god", // Sprint 58 A1
  "gundam-crossbone", // 3 PNGs from earlier probe; not a full set
]);

export type AvatarEmotion =
  | "idle"
  | "listening"
  | "thinking"
  | "speaking"
  | "warning"
  | "damage"
  | "joy"
  | "sad"
  | "confused";

/** Resolve the directory name for a given theme id. NT-D uses
 *  the bare `emotions/` directory (legacy baseline). Every
 *  other known theme uses `emotions-<slug>/`. Unknown themes
 *  fall back to `emotions/` (NT-D baseline). */
export function avatarDirForTheme(
  themeId: string | null | undefined,
): string {
  if (themeId && THEMES_WITH_AVATAR_SET.has(themeId)) {
    return `emotions-${themeId.replace(/^gundam-/, "")}`;
  }
  // NT-D explicitly, and unknown themes → legacy bare `emotions/`.
  return "emotions";
}

/** Build the URL map for the active theme. Cheap (9 string
 *  concats); call inside `useMemo` keyed on themeId. */
export function buildAvatarImageMap(
  themeId: string | null | undefined,
): Record<AvatarEmotion, string> {
  const dir = avatarDirForTheme(themeId);
  return {
    idle:      `/avatars/${dir}/idle.png`,
    listening: `/avatars/${dir}/listening.png`,
    thinking:  `/avatars/${dir}/thinking.png`,
    speaking:  `/avatars/${dir}/speaking.png`,
    warning:   `/avatars/${dir}/warning.png`,
    damage:    `/avatars/${dir}/damage.png`,
    joy:       `/avatars/${dir}/joy.png`,
    sad:       `/avatars/${dir}/sad.png`,
    confused:  `/avatars/${dir}/confused.png`,
  };
}
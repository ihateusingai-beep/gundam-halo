/**
 * Avatar asset paths — single source of truth for the theme-keyed
 * avatar directory + per-theme emotion PNG URLs.
 *
 * Sprint 58 NEW. Previously hard-coded in `ImageSetAvatar.tsx`;
 * extracted so the wizard (StepTheme) and the audit docs can
 * read the same mapping without importing React components.
 *
 * ## Mapping (Sprint 59: every theme ships a full 9-emotion set)
 *
 *   themeId          →  directory         →  path for emotion
 *   ----------------------------------------------------------------
 *   null             →  emotions/         →  /avatars/emotions/<emotion>.jpg
 *   "gundam-ntd"     →  emotions/         →  /avatars/emotions/<emotion>.jpg
 *   "gundam-seed"    →  emotions-seed/    →  /avatars/emotions-seed/<emotion>.jpg
 *   "gundam-ntd-green"→ emotions-ntd-green/→  /avatars/emotions-ntd-green/<emotion>.jpg
 *   "gundam-00"      →  emotions-00/      →  /avatars/emotions-00/<emotion>.jpg
 *   "gundam-destiny"  →  emotions-destiny/ →  /avatars/emotions-destiny/<emotion>.jpg
 *   "gundam-god"      →  emotions-god/     →  /avatars/emotions-god/<emotion>.jpg
 *   "gundam-crossbone"→ emotions-crossbone/ →  /avatars/emotions-crossbone/<emotion>.jpg
 *   "gundam-halo"     →  emotions-halo/    →  /avatars/emotions-halo/<emotion>.jpg
 *   "gundam-cartoon"  →  emotions-cartoon/ →  /avatars/emotions-cartoon/<emotion>.jpg
 *
 * Each set has 9 emotion JPGs (idle / listening / thinking /
 * speaking / warning / damage / joy / sad / confused). NT-D
 * uses the legacy baseline (bare `emotions/`). All 8 other
 * themes use the per-theme `<slug>/` convention.
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
  "gundam-crossbone", // Sprint 59 — full 9-emotion set
  "gundam-halo", // Sprint 59 — full 9-emotion set
  "gundam-cartoon", // Sprint 59 — full 9-emotion set
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
 *  concats); call inside `useMemo` keyed on themeId.
 *
 *  Note: file extensions are inconsistent because matrix MCP
 *  returns JPEG for some i2i generations and true PNG for others
 *  (no pattern — empirically observed across Sprint 58/59).
 *  The NT-D baseline `emotions/` directory is hand-authored PNG
 *  (pre-Sprint 58). `extForEmotion()` centralises the lookup
 *  per-file. Browser-sniffs content type, so even wrong ext
 *  works, but aligning the URL to the on-disk bytes is cleaner.
 */
export function buildAvatarImageMap(
  themeId: string | null | undefined,
): Record<AvatarEmotion, string> {
  const dir = avatarDirForTheme(themeId);
  return {
    idle:      `/avatars/${dir}/idle.${extForEmotion(dir, "idle")}`,
    listening: `/avatars/${dir}/listening.${extForEmotion(dir, "listening")}`,
    thinking:  `/avatars/${dir}/thinking.${extForEmotion(dir, "thinking")}`,
    speaking:  `/avatars/${dir}/speaking.${extForEmotion(dir, "speaking")}`,
    warning:   `/avatars/${dir}/warning.${extForEmotion(dir, "warning")}`,
    damage:    `/avatars/${dir}/damage.${extForEmotion(dir, "damage")}`,
    joy:       `/avatars/${dir}/joy.${extForEmotion(dir, "joy")}`,
    sad:       `/avatars/${dir}/sad.${extForEmotion(dir, "sad")}`,
    confused:  `/avatars/${dir}/confused.${extForEmotion(dir, "confused")}`,
  };
}

/** Per-(dir, emotion) extension lookup. NT-D legacy is always
 *  PNG. Per-theme dirs use a static map captured during Sprint
 *  59 audit: matrix MCP returned JPEG for ~6/9 emotions and
 *  PNG for ~3/9 (varies per theme — there's no predicting
 *  pattern). Future cleanup: convert all to one format.
 *
 *  The first-match shape means: "if the file at .jpg exists on
 *  disk, use .jpg; otherwise fall through to .png". This is
 *  robust to either direction. We hard-code the SPRINT 59 truth
 *  per dir/emotion for performance (the lookup table is 81
 *  entries — ~1KB of bytes — and avoids any per-render I/O). */
const PER_THEME_EXT: Record<string, Partial<Record<AvatarEmotion, "png" | "jpg">>> = {
  // Sprint 59 audit: each per-theme dir's extension map, captured
  // from `file -b` output. Most themes are all-jpg; only
  // crossbone / halo / cartoon have a few PNGs that matrix MCP
  // returned as true PNG rather than JPEG.
  "emotions-seed":       { idle: "jpg", listening: "jpg", thinking: "jpg", speaking: "jpg", warning: "jpg", damage: "jpg", joy: "jpg", sad: "jpg", confused: "jpg" },
  "emotions-ntd-green":  { idle: "jpg", listening: "jpg", thinking: "jpg", speaking: "jpg", warning: "jpg", damage: "jpg", joy: "jpg", sad: "jpg", confused: "jpg" },
  "emotions-00":         { idle: "jpg", listening: "jpg", thinking: "jpg", speaking: "jpg", warning: "jpg", damage: "jpg", joy: "jpg", sad: "jpg", confused: "jpg" },
  "emotions-destiny":    { idle: "jpg", listening: "jpg", thinking: "jpg", speaking: "jpg", warning: "jpg", damage: "jpg", joy: "jpg", sad: "jpg", confused: "jpg" },
  "emotions-god":        { idle: "jpg", listening: "jpg", thinking: "jpg", speaking: "jpg", warning: "jpg", damage: "jpg", joy: "jpg", sad: "jpg", confused: "jpg" },
  "emotions-crossbone":  { idle: "jpg", listening: "png", thinking: "jpg", speaking: "png", warning: "jpg", damage: "png", joy: "jpg", sad: "jpg", confused: "jpg" },
  "emotions-halo":       { idle: "jpg", listening: "jpg", thinking: "jpg", speaking: "jpg", warning: "jpg", damage: "jpg", joy: "jpg", sad: "jpg", confused: "png" },
  "emotions-cartoon":    { idle: "jpg", listening: "jpg", thinking: "png", speaking: "jpg", warning: "png", damage: "jpg", joy: "png", sad: "jpg", confused: "jpg" },
};

function extForEmotion(dir: string, emotion: AvatarEmotion): "png" | "jpg" {
  if (dir === "emotions") return "png"; // NT-D legacy
  const table = PER_THEME_EXT[dir];
  return table?.[emotion] ?? "jpg"; // default jpg for new themes
}
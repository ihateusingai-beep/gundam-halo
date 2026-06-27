/**
 * Activity tier — Sprint 41 (Feature F).
 *
 * Maps a project's `last_activity_at` timestamp to one of 5
 * visual tiers (fresh / recent / stale / dormant / archived).
 * Each tier has a CSS variable colour + a label for the
 * MissionCard status row.
 *
 * Tiers (hardcoded thresholds; future work: per-user `[ui]`
 * config block to override):
 *   - fresh    — < 1 hour      (green --success)
 *   - recent   — < 24 hours    (cyan --accent)
 *   - stale    — < 7 days      (amber --warning)
 *   - dormant  — >= 7 days     (rose-red --danger)
 *   - archived — manual override (grey --text-muted)
 *
 * Defensive: malformed timestamp → "stale" (no crash). Null
 * timestamp → "dormant" (no activity yet).
 *
 * Pure function — no side effects. Tested with deterministic
 * `now` arg so vitest can pin the boundaries.
 */

export type ActivityTier =
  | "fresh"
  | "recent"
  | "stale"
  | "dormant"
  | "archived";

const ONE_HOUR_MS = 60 * 60 * 1000;
const ONE_DAY_MS = 24 * ONE_HOUR_MS;
const SEVEN_DAYS_MS = 7 * ONE_DAY_MS;

export function activityTier(
  lastActivityAt: string | null,
  now: Date = new Date(),
  archived: boolean = false,
): ActivityTier {
  if (archived) return "archived";
  if (!lastActivityAt) return "dormant";
  const lastMs = Date.parse(lastActivityAt);
  if (Number.isNaN(lastMs)) return "stale";
  const ageMs = now.getTime() - lastMs;
  // Negative age (clock skew, future timestamp) → treat as fresh.
  if (ageMs < 0) return "fresh";
  if (ageMs < ONE_HOUR_MS) return "fresh";
  if (ageMs < ONE_DAY_MS) return "recent";
  if (ageMs < SEVEN_DAYS_MS) return "stale";
  return "dormant";
}

/** Theme variable for the tier's border / dot colour. */
export const TIER_COLORS: Record<ActivityTier, string> = {
  fresh: "var(--success)",
  recent: "var(--accent)",
  stale: "var(--warning)",
  dormant: "var(--danger)",
  archived: "var(--text-muted)",
};

/** Short uppercase label rendered next to the status dot. */
export const TIER_LABELS: Record<ActivityTier, string> = {
  fresh: "ACTIVE",
  recent: "RECENT",
  stale: "STALE",
  dormant: "DORMANT",
  archived: "ARCHIVED",
};
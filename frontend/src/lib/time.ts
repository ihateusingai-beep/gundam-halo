/**
 * Format an ISO timestamp as a short relative string ("5m ago", "3h ago", "2d ago").
 * Falls back to a truncated ISO or raw input when parsing fails.
 *
 * Extracted from ProjectCard / MissionCard / MissionSelect (Plan A / M10-A).
 * Keep this pure — no React, no globals, no Date.now() mocking.
 */
export function formatRelative(iso: string): string {
  if (!iso) return "—";
  try {
    const then = new Date(iso).getTime();
    if (isNaN(then)) return iso.slice(0, 16);
    const now = Date.now();
    const diffMs = now - then;
    const sec = Math.floor(diffMs / 1000);
    if (sec < 60) return `${sec}s ago`;
    const min = Math.floor(sec / 60);
    if (min < 60) return `${min}m ago`;
    const hr = Math.floor(min / 60);
    if (hr < 24) return `${hr}h ago`;
    const day = Math.floor(hr / 24);
    if (day < 30) return `${day}d ago`;
    return new Date(iso).toLocaleDateString("en", { day: "numeric", month: "short" });
  } catch {
    return iso;
  }
}

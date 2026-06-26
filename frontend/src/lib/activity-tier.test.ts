/**
 * activity-tier.test.ts — Sprint 41 Feature F.
 *
 * 5 tests covering each tier boundary + defensive fallbacks.
 */

import { describe, expect, it } from "vitest";

import { activityTier, TIER_COLORS, TIER_LABELS } from "@/lib/activity-tier";

const NOW = new Date("2026-06-27T12:00:00Z");

function isoMinutesAgo(min: number): string {
  return new Date(NOW.getTime() - min * 60_000).toISOString();
}
function isoDaysAgo(days: number): string {
  return new Date(NOW.getTime() - days * 86_400_000).toISOString();
}

describe("activityTier", () => {
  it("fresh for < 1 hour", () => {
    expect(activityTier(isoMinutesAgo(30), NOW)).toBe("fresh");
  });

  it("recent for 1-24 hours", () => {
    expect(activityTier(isoMinutesAgo(60), NOW)).toBe("recent");
    expect(activityTier(isoMinutesAgo(60 * 23), NOW)).toBe("recent");
  });

  it("stale for 1-7 days", () => {
    expect(activityTier(isoDaysAgo(1), NOW)).toBe("stale");
    expect(activityTier(isoDaysAgo(6), NOW)).toBe("stale");
  });

  it("dormant for >= 7 days", () => {
    expect(activityTier(isoDaysAgo(7), NOW)).toBe("dormant");
    expect(activityTier(isoDaysAgo(30), NOW)).toBe("dormant");
  });

  it("null last_activity falls back to dormant", () => {
    expect(activityTier(null, NOW)).toBe("dormant");
  });

  it("malformed timestamp falls back to stale", () => {
    expect(activityTier("not-a-date", NOW)).toBe("stale");
  });

  it("future timestamp (clock skew) treated as fresh", () => {
    const future = new Date(NOW.getTime() + 60_000).toISOString();
    expect(activityTier(future, NOW)).toBe("fresh");
  });

  it("archived overrides last_activity", () => {
    // Even if recently active, archived projects show "archived".
    expect(activityTier(isoMinutesAgo(5), NOW, true)).toBe("archived");
    // And even old projects with archived flag stay archived.
    expect(activityTier(isoDaysAgo(30), NOW, true)).toBe("archived");
  });

  it("every tier has a colour + label", () => {
    for (const tier of [
      "fresh",
      "recent",
      "stale",
      "dormant",
      "archived",
    ] as const) {
      expect(TIER_COLORS[tier]).toMatch(/^var\(--/);
      expect(TIER_LABELS[tier]).toBeTruthy();
    }
  });
});
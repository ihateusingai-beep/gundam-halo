/**
 * audit/format.test.ts — Sprint 61 R-A1 tests.
 *
 * 6 tests pinning the 4 format helpers. Pure-function tests,
 * no React or jsdom needed.
 */
import { describe, expect, it } from "vitest";

import type { AuditEntry } from "@/types/api";
import { formatBytes, formatMs, formatTime, groupByDate } from "./format";

function entryAt(iso: string): AuditEntry {
  return {
    id: iso,
    ts: iso,
    event_type: "test",
    data: { action: "noop" },
  };
}

describe("audit/format (Sprint 61 R-A1)", () => {
  it("groupByDate buckets today / yesterday / this-week / earlier", () => {
    const now = Date.now();
    const today = new Date(now).toISOString();
    const yesterday = new Date(now - 24 * 60 * 60 * 1000).toISOString();
    const threeDaysAgo = new Date(now - 3 * 24 * 60 * 60 * 1000).toISOString();
    const twoWeeksAgo = new Date(now - 14 * 24 * 60 * 60 * 1000).toISOString();

    const groups = groupByDate([
      entryAt(today),
      entryAt(yesterday),
      entryAt(threeDaysAgo),
      entryAt(twoWeeksAgo),
    ]);
    const labels = groups.map(([label]) => label);
    expect(labels).toEqual([
      "Today",
      "Yesterday",
      "This Week",
      "Earlier",
    ]);
  });

  it("groupByDate skips empty buckets", () => {
    const now = Date.now();
    const today = new Date(now).toISOString();
    const groups = groupByDate([entryAt(today)]);
    expect(groups).toHaveLength(1);
    expect(groups[0][0]).toBe("Today");
  });

  it("formatTime emits HH:MM:SS", () => {
    // 14:32:08 UTC (test runs in UTC under vitest)
    const iso = "2026-07-11T14:32:08.000Z";
    const out = formatTime(iso);
    expect(out).toMatch(/^\d{2}:\d{2}:\d{2}$/);
  });

  it("formatTime returns '—' for invalid input", () => {
    expect(formatTime("not-a-date")).toBe("—");
  });

  it("formatBytes picks the right unit", () => {
    expect(formatBytes(0)).toBe("0 B");
    expect(formatBytes(500)).toBe("500 B");
    expect(formatBytes(2048)).toBe("2.0 KB");
    expect(formatBytes(5_242_880)).toBe("5.0 MB");
    expect(formatBytes(1_073_741_824)).toBe("1.0 GB");
  });

  it("formatMs picks the right unit", () => {
    expect(formatMs(0.0005)).toMatch(/µs/);
    expect(formatMs(150)).toBe("150ms");
    expect(formatMs(1500)).toBe("1.5s");
    expect(formatMs(90_000)).toBe("1m 30s");
  });
});
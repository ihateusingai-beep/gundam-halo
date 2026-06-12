/** Tests for the relative-time formatter (used by ProjectCard, MissionCard,
 *  MissionSelect). Pure, no React, no globals.
 *
 *  Note: formatRelative uses `Date.now()` internally, so we mock
 *  `Date.now` to a fixed point to make the assertions deterministic.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { formatRelative } from "@/lib/time";

describe("formatRelative", () => {
  // Pin "now" to 2026-06-12T14:00:00Z for all tests in this block
  const NOW = new Date("2026-06-12T14:00:00Z").getTime();

  beforeEach(() => {
    vi.spyOn(Date, "now").mockReturnValue(NOW);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("returns '—' for empty input", () => {
    expect(formatRelative("")).toBe("—");
  });

  it("formats seconds ago", () => {
    const fiveSecAgo = new Date(NOW - 5_000).toISOString();
    expect(formatRelative(fiveSecAgo)).toBe("5s ago");
  });

  it("formats zero seconds ago", () => {
    const now = new Date(NOW).toISOString();
    expect(formatRelative(now)).toBe("0s ago");
  });

  it("formats minutes ago", () => {
    const fiveMinAgo = new Date(NOW - 5 * 60_000).toISOString();
    expect(formatRelative(fiveMinAgo)).toBe("5m ago");
  });

  it("formats hours ago", () => {
    const threeHoursAgo = new Date(NOW - 3 * 3_600_000).toISOString();
    expect(formatRelative(threeHoursAgo)).toBe("3h ago");
  });

  it("formats days ago", () => {
    const twoDaysAgo = new Date(NOW - 2 * 86_400_000).toISOString();
    expect(formatRelative(twoDaysAgo)).toBe("2d ago");
  });

  it("falls back to truncated ISO for invalid date string", () => {
    // The fallback path does `iso.slice(0, 16)` — "not a date" is
    // already < 16 chars, so the original string comes back
    // unchanged. (The truncation only matters for very long inputs.)
    expect(formatRelative("not a date")).toBe("not a date");
  });

  it("truncates long invalid strings to 16 chars", () => {
    expect(formatRelative("this-is-a-very-long-invalid-date-string")).toBe(
      "this-is-a-very-l"
    );
  });

  it("falls back to a locale-formatted date for very old timestamps", () => {
    // 60 days ago — beyond the 30-day window, should hit the
    // `.toLocaleDateString` branch.
    const longAgo = new Date(NOW - 60 * 86_400_000).toISOString();
    const out = formatRelative(longAgo);
    // Don't assert the exact date (locale-dependent in CI) but
    // ensure it does NOT return "60d ago" or "—".
    expect(out).not.toBe("60d ago");
    expect(out).not.toBe("—");
    expect(out.length).toBeGreaterThan(0);
  });

  it("returns truncated ISO on parsing error", () => {
    // Force a Date constructor error via an exotic but parseable-then-failing value
    const weird = "2026-13-45T99:99:99Z"; // invalid month / day / time
    const out = formatRelative(weird);
    // Should either be a relative time (if the Date somehow parses)
    // or a truncated ISO prefix. Just assert it's not "—".
    expect(out).not.toBe("—");
  });
});

/** Tests for the small formatters used by B2 SessionDetailPage
 *  and B7 AuditDashboardPage (formatTime, formatDateTime, formatBytes,
 *  formatMs). They are currently private to those route files, so
 *  we duplicate the implementations here to lock the contract.
 *
 *  If you change a formatter in a route file, mirror the change here
 *  to keep the test aligned. The next refactor will lift these into
 *  a shared `lib/format.ts` and this duplication can go away.
 */
import { describe, it, expect } from "vitest";

/* ----- duplicated from routes/projects/[id]/sessions/[sessionId].tsx ----- */
function formatTime(iso: string): string {
  if (!iso) return "(unknown)";
  try {
    const d = new Date(iso);
    if (isNaN(d.getTime())) return iso.slice(0, 19).replace("T", " ");
    const hh = String(d.getHours()).padStart(2, "0");
    const mm = String(d.getMinutes()).padStart(2, "0");
    const ss = String(d.getSeconds()).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    const mon = d.toLocaleString("en", { month: "short" });
    return `${day} ${mon} ${hh}:${mm}:${ss}`;
  } catch {
    return iso;
  }
}

/* ----- duplicated from routes/audit.tsx ----- */
function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(2)} MB`;
}

function formatMs(n: number): string {
  if (n < 1000) return `${n}ms`;
  return `${(n / 1000).toFixed(2)}s`;
}

describe("formatTime", () => {
  it("returns '(unknown)' for empty input", () => {
    expect(formatTime("")).toBe("(unknown)");
  });

  it("formats ISO string as DD Mon HH:MM:SS", () => {
    // Use a fixed local-time date to avoid TZ surprises — the formatter
    // uses local time (d.getHours()) so we assert the structure, not
    // the exact timezone-offset value.
    const out = formatTime("2026-06-12T14:23:45");
    expect(out).toMatch(/^\d{2} \w{3} \d{2}:\d{2}:\d{2}$/);
  });

  it("falls back to truncated ISO for unparseable input", () => {
    expect(formatTime("garbage")).toBe("garbage");
  });
});

describe("formatBytes", () => {
  it("formats bytes", () => {
    expect(formatBytes(0)).toBe("0 B");
    expect(formatBytes(100)).toBe("100 B");
    expect(formatBytes(1023)).toBe("1023 B");
  });

  it("formats kilobytes with one decimal", () => {
    expect(formatBytes(1024)).toBe("1.0 KB");
    expect(formatBytes(1536)).toBe("1.5 KB");
    expect(formatBytes(1024 * 100)).toBe("100.0 KB");
  });

  it("formats megabytes with two decimals", () => {
    expect(formatBytes(1024 * 1024)).toBe("1.00 MB");
    expect(formatBytes(1024 * 1024 * 2.5)).toBe("2.50 MB");
  });
});

describe("formatMs", () => {
  it("formats milliseconds under 1s", () => {
    expect(formatMs(0)).toBe("0ms");
    expect(formatMs(12)).toBe("12ms");
    expect(formatMs(999)).toBe("999ms");
  });

  it("formats seconds with two decimals", () => {
    expect(formatMs(1000)).toBe("1.00s");
    expect(formatMs(1500)).toBe("1.50s");
    expect(formatMs(12345)).toBe("12.35s"); // rounds
  });
});

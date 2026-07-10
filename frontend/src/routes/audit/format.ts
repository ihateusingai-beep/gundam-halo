/**
 * audit/format.ts — pure formatting helpers for the audit dashboard.
 *
 * Sprint 61 R-A1: extracted from `routes/audit.tsx` (which had
 * 482 LoC with 4 inline format helpers + 4 inline components).
 * These are pure functions, no React deps, easy to test.
 *
 * ## What lives here
 *
 *   - `groupByDate(entries)` — buckets entries by date label
 *     (Today / Yesterday / This Week / Earlier).
 *   - `formatTime(iso)` — HH:MM:SS for an ISO timestamp.
 *   - `formatBytes(n)` — KB/MB/GB humanised.
 *   - `formatMs(n)` — duration in ms → µs / ms / s humanised.
 *
 * ## What doesn't live here
 *
 *   - Date-bucket UI rendering (lives in the orchestrator).
 *   - Filter logic (lives in the orchestrator; helpers here
 *     only format, not filter).
 *   - Network / API calls (lives in `lib/api.ts`).
 */
import type { AuditEntry } from "@/types/api";

const MS_IN_SECOND = 1000;
const MS_IN_MINUTE = 60 * MS_IN_SECOND;
const MS_IN_HOUR = 60 * MS_IN_MINUTE;
const MS_IN_DAY = 24 * MS_IN_HOUR;

const BYTE = 1024;
const KB = BYTE;
const MB = BYTE * BYTE;
const GB = BYTE * BYTE * BYTE;

/** Bucket labels for the date groupBy function. Order matters:
 *  it determines the order the orchestrator renders the
 *  groups in. */
const DATE_BUCKETS = [
  "Today",
  "Yesterday",
  "This Week",
  "Earlier",
] as const;

export type DateBucket = (typeof DATE_BUCKETS)[number];

/** Group entries by date bucket. Returns an array of
 *  `[label, items]` pairs in the canonical order
 *  (Today first, Earlier last). Items within each bucket
 *  preserve the input order. */
export function groupByDate(
  entries: AuditEntry[],
): Array<[DateBucket, AuditEntry[]]> {
  const now = new Date();
  const todayStart = new Date(
    now.getFullYear(),
    now.getMonth(),
    now.getDate(),
  );
  const yesterdayStart = new Date(todayStart.getTime() - MS_IN_DAY);
  const weekStart = new Date(todayStart.getTime() - 7 * MS_IN_DAY);

  const buckets: Record<DateBucket, AuditEntry[]> = {
    Today: [],
    Yesterday: [],
    "This Week": [],
    Earlier: [],
  };
  for (const entry of entries) {
    const ts = new Date(entry.ts);
    if (ts >= todayStart) buckets.Today.push(entry);
    else if (ts >= yesterdayStart) buckets.Yesterday.push(entry);
    else if (ts >= weekStart) buckets["This Week"].push(entry);
    else buckets.Earlier.push(entry);
  }
  // Return only non-empty buckets in canonical order.
  return DATE_BUCKETS.map(
    (label) => [label, buckets[label]] as [DateBucket, AuditEntry[]],
  ).filter(([, items]) => items.length > 0);
}

/** Format an ISO timestamp as HH:MM:SS (24h). */
export function formatTime(iso: string): string {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "—";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

/** Format a byte count as a humanised string (KB / MB / GB).
 *  Returns "0 B" for non-positive values (caller's job to
 *  distinguish "absent" from "0"; this function only formats
 *  the magnitude). */
export function formatBytes(n: number): string {
  if (n < KB) return `${n} B`;
  if (n < MB) return `${(n / KB).toFixed(1)} KB`;
  if (n < GB) return `${(n / MB).toFixed(1)} MB`;
  return `${(n / GB).toFixed(1)} GB`;
}

/** Format a millisecond duration as a humanised string.
 *  Returns "—µs" / "Xms" / "X.Ys" / "Xm Ys". */
export function formatMs(n: number): string {
  if (n < 1) return `${(n * 1000).toFixed(0)}µs`;
  if (n < MS_IN_SECOND) return `${n.toFixed(0)}ms`;
  if (n < MS_IN_MINUTE) return `${(n / MS_IN_SECOND).toFixed(1)}s`;
  const minutes = Math.floor(n / MS_IN_MINUTE);
  const seconds = Math.floor((n % MS_IN_MINUTE) / MS_IN_SECOND);
  return `${minutes}m ${seconds}s`;
}
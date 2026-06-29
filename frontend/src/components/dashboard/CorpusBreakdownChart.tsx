/**
 * CorpusBreakdownChart — Sprint 46 stacked bar chart for HeldOutEvalCard.
 *
 * Renders one bar per eval run (x-axis: timestamp, y-axis: WER %),
 * coloured by corpus_id. Below the chart, a legend row shows one
 * chip per corpus with run count + average WER for that corpus.
 *
 * Why custom (instead of using Recharts BarChart directly)?
 * - We need per-bar cell colouring (deterministic hash → CSS var),
 *   not a per-series stacked bar. Each row is its own series of 1.
 * - The chart is small (typically 4-10 bars) and the cockpit theme
 *   wants tight spacing — easier to hand-roll an SVG than to fight
 *   Recharts' defaults.
 *
 * The component is purely presentational; the parent (HeldOutEvalCard)
 * owns the data + fetch. The component is testable by passing mock
 * timeline + by_corpus props.
 */
import { useMemo } from "react";

import { cn } from "@/lib/utils";
import type {
  CorpusBreakdownResponse,
  CorpusBreakdownEntry,
  CorpusBreakdownTimelineEntry,
} from "@/types/api";

// Theme-aligned colour palette. First 4 are CSS vars (--accent /
// --success / --warning / --danger); the rest are hard-coded
// fallback hues for corpora > 4. "unattributed" is always grey.
const CORPUS_COLORS: readonly string[] = [
  "var(--accent)",  // cyan
  "var(--success)", // green
  "var(--warning)", // amber
  "var(--danger)",  // rose
  "#a78bfa",        // purple
  "#fb923c",        // orange
  "#22d3ee",        // sky
] as const;

const UNATTRIBUTED_COLOR = "var(--text-muted)";

/** Stable hash → palette index. Same corpus_id always gets the same
 *  colour across refreshes. Index covers the first 4 theme colours
 *  cyclically beyond the palette size. */
function corpusColor(corpusId: string): string {
  if (!corpusId || corpusId === "unattributed") {
    return UNATTRIBUTED_COLOR;
  }
  let hash = 0;
  for (let i = 0; i < corpusId.length; i++) {
    hash = (hash * 31 + corpusId.charCodeAt(i)) >>> 0;
  }
  return CORPUS_COLORS[hash % CORPUS_COLORS.length];
}

interface CorpusBreakdownChartProps {
  /** Sorted oldest-first; the backend already sorts, but we re-sort
   *  defensively in case the parent forwards raw data. */
  timeline: CorpusBreakdownTimelineEntry[];
  byCorpus: Record<string, CorpusBreakdownEntry>;
  threshold: number;
  className?: string;
}

const VIEW_W = 120;
const VIEW_H = 32;

function sparklinePoints(
  rows: CorpusBreakdownTimelineEntry[],
  viewW: number,
  viewH: number,
  maxWer: number,
): { x: number; y: number; color: string; entry: CorpusBreakdownTimelineEntry }[] {
  if (rows.length === 0) return [];
  const ordered = [...rows].sort((a, b) => a.timestamp_ms - b.timestamp_ms);
  const step = ordered.length === 1 ? 0 : viewW / (ordered.length - 1);
  return ordered.map((row, i) => {
    const clamped = Math.min(row.wer_pct, maxWer);
    const y = viewH - (clamped / maxWer) * viewH;
    return {
      x: i * step,
      y,
      color: corpusColor(row.corpus_id),
      entry: row,
    };
  });
}

export function CorpusBreakdownChart({
  timeline,
  byCorpus,
  threshold,
  className,
}: CorpusBreakdownChartProps) {
  const allWers = timeline.map((r) => r.wer_pct);
  const chartMax = Math.max(10, threshold * 2, ...allWers);
  const points = useMemo(
    () => sparklinePoints(timeline, VIEW_W, VIEW_H, chartMax),
    [timeline, chartMax],
  );
  const thresholdY = (VIEW_H - (threshold / chartMax) * VIEW_H).toFixed(2);

  // Sort corpora by latest_seen_ms desc (same order as backend).
  const corpusOrder = useMemo(() => {
    return Object.entries(byCorpus).sort(
      (a, b) => b[1].latest_seen_ms - a[1].latest_seen_ms,
    );
  }, [byCorpus]);

  if (timeline.length === 0) {
    return null;
  }

  return (
    <div
      data-testid="corpus-breakdown-chart"
      className={cn("mt-2", className)}
    >
      <svg
        data-testid="corpus-breakdown-svg"
        viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
        preserveAspectRatio="none"
        className="w-full h-8"
        aria-label={`Per-corpus WER trend over ${timeline.length} runs`}
      >
        {/* Threshold dashed line (same convention as the existing sparkline). */}
        <line
          x1="0"
          y1={thresholdY}
          x2={VIEW_W}
          y2={thresholdY}
          stroke="var(--warning)"
          strokeWidth="0.5"
          strokeDasharray="2 2"
        />
        {/* Per-run bars (3px wide). Coloured by corpus. */}
        {points.map((p, i) => (
          <rect
            key={`${p.entry.timestamp_ms}-${i}`}
            data-testid="corpus-bar"
            data-corpus-id={p.entry.corpus_id}
            x={p.x - 1.5}
            y={p.y}
            width="3"
            height={VIEW_H - p.y}
            fill={p.color}
            opacity="0.9"
          >
            <title>
              {`${p.entry.corpus_id}: ${p.entry.wer_pct.toFixed(1)}% WER (${p.entry.asr_backend || "?"})`}
            </title>
          </rect>
        ))}
      </svg>
      {/* Legend chips — one per corpus, in by_corpus order. */}
      <div
        data-testid="corpus-legend"
        className="mt-1 flex items-center gap-2 flex-wrap"
      >
        {corpusOrder.map(([corpusId, entry]) => (
          <div
            key={corpusId}
            data-testid="corpus-legend-chip"
            data-corpus-id={corpusId}
            className="flex items-center gap-1 text-[10px] font-mono text-[var(--text-muted)]"
            title={`${entry.run_count} run(s); avg ${entry.avg_wer_pct.toFixed(1)}% WER; best ${entry.best_wer_pct.toFixed(1)}%`}
          >
            <span
              data-testid="corpus-legend-dot"
              className="inline-block w-2 h-2 rounded-sm"
              style={{ backgroundColor: corpusColor(corpusId) }}
            />
            <span>{corpusId}</span>
            <span>
              {entry.run_count} run{entry.run_count === 1 ? "" : "s"}
            </span>
            <span>·</span>
            <span data-testid="corpus-legend-avg">avg {entry.avg_wer_pct.toFixed(1)}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export { corpusColor, CORPUS_COLORS };

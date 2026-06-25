/**
 * HeldOutEvalCard — Sprint 39 cockpit card.
 *
 * Surfaces the held-out Cantonese eval trend on the home
 * page so the pilot sees the latest WER + a 7-run sparkline
 * without opening a terminal. Data source:
 * `GET /voice/eval-results` (Sprint 39 backend).
 *
 * Three render states:
 *   1. **No data yet** — empty results dir. Renders a
 *      "No evals yet — run `scripts/record-held-out.sh`"
 *      grey card.
 *   2. **Latest run present** — big WER number, pass/fail
 *      badge (cyan PASS / pink FAIL vs threshold), and a
 *      60×24 px SVG sparkline of the last 7 runs.
 *   3. **Error** — fetch failed. Renders "Eval unavailable"
 *      with the error reason in mono.
 *
 * The sparkline is a zero-dep inline SVG (no chart library).
 * Y-axis: 0% → max(threshold×2, max WER) so the threshold
 * stays visible as a dashed line. X-axis: newest at right.
 * Each WER is one polyline vertex; the points are scaled
 * to the viewBox 0..60 wide × 0..24 tall.
 *
 * Polling: 10 s. The trend only changes when the user runs
 * the CLI, so 10 s is plenty. The card never auto-runs
 * anything — it's read-only.
 */

import { useEffect, useState } from "react";

import { HudCard } from "@/components/gundam/HudCard";
import { api } from "@/lib/api";
import type { EvalRunRow } from "@/types/api";

const POLL_INTERVAL_MS = 10_000;

interface DisplayState {
  kind: "loading" | "empty" | "ready" | "error";
  latest?: EvalRunRow;
  history?: EvalRunRow[];
  thresholdPct?: number;
  error?: string;
}

/**
 * Compute the polyline points for the sparkline.
 *
 * `rows` is newest-first (the backend contract). We render
 * the sparkline left-to-right oldest-to-newest (so the
 * pilot sees time flow naturally). Empty input → empty
 * string (caller renders an "empty" SVG).
 */
function sparklinePoints(
  rows: EvalRunRow[],
  viewW: number,
  viewH: number,
  maxWer: number,
): string {
  if (rows.length === 0) return "";
  // Reverse so the leftmost point is the OLDEST run.
  const ordered = [...rows].reverse();
  const step = ordered.length === 1 ? 0 : viewW / (ordered.length - 1);
  // Clamp the Y so values above the chart cap still draw
  // at the top edge instead of disappearing off-canvas.
  const y = (wer: number) => {
    const clamped = Math.min(wer, maxWer);
    // 0% maps to viewH (bottom); maxWer maps to 0 (top).
    return viewH - (clamped / maxWer) * viewH;
  };
  return ordered
    .map((row, i) => `${(i * step).toFixed(2)},${y(row.wer_pct).toFixed(2)}`)
    .join(" ");
}

export function HeldOutEvalCard() {
  const [display, setDisplay] = useState<DisplayState>({ kind: "loading" });

  useEffect(() => {
    let cancelled = false;

    async function poll() {
      try {
        const res = await api.getVoiceEvalResults();
        if (cancelled) return;
        if (!res.latest) {
          setDisplay({
            kind: "empty",
            thresholdPct: res.threshold_pct,
          });
          return;
        }
        setDisplay({
          kind: "ready",
          latest: res.latest,
          history: res.history,
          thresholdPct: res.threshold_pct,
        });
      } catch (e) {
        if (cancelled) return;
        setDisplay({
          kind: "error",
          error: e instanceof Error ? e.message : String(e),
        });
      }
    }

    void poll();
    const id = setInterval(poll, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  // ---- Loading ----
  if (display.kind === "loading") {
    return (
      <HudCard>
        <div data-testid="held-out-eval-card" data-state="loading">
          <span className="text-[10px] font-[Orbitron] text-[var(--text-muted)] uppercase tracking-widest">
            Voice Eval
          </span>
          <p className="text-xs text-[var(--text-muted)] mt-1">Loading…</p>
        </div>
      </HudCard>
    );
  }

  // ---- Error ----
  if (display.kind === "error") {
    return (
      <HudCard>
        <div data-testid="held-out-eval-card" data-state="error">
          <span className="text-[10px] font-[Orbitron] text-[var(--danger)] uppercase tracking-widest">
            Voice Eval
          </span>
          <h3 className="text-lg font-[Rajdhani] text-[var(--danger)] mt-1">
            Unavailable
          </h3>
          <p
            className="text-[10px] text-[var(--text-muted)] font-mono mt-1 truncate"
            title={display.error}
          >
            {display.error}
          </p>
        </div>
      </HudCard>
    );
  }

  // ---- Empty ----
  if (display.kind === "empty") {
    const threshold = display.thresholdPct ?? 15.0;
    return (
      <HudCard>
        <div data-testid="held-out-eval-card" data-state="empty">
          <span className="text-[10px] font-[Orbitron] text-[var(--text-muted)] uppercase tracking-widest">
            Voice Eval
          </span>
          <h3 className="text-lg font-[Rajdhani] text-[var(--text-muted)] mt-1">
            No evals yet
          </h3>
          <p className="text-[10px] text-[var(--text-muted)] font-mono mt-1">
            Run <code className="text-[var(--accent)]">scripts/record-held-out.sh</code>{" "}
            then <code className="text-[var(--accent)]">scripts/run_held_out_eval.py</code>.
          </p>
          <p className="text-[10px] text-[var(--text-muted)] font-mono mt-1">
            Threshold: {threshold.toFixed(1)}% WER.
          </p>
        </div>
      </HudCard>
    );
  }

  // ---- Ready ----
  const { latest, history, thresholdPct } = display;
  // The "ready" branch is only taken when `latest` is defined;
  // the DisplayState type still allows undefined because the
  // kind discriminant doesn't narrow optional fields. We
  // bail explicitly so TS is happy without an `!` assertion.
  if (!latest) {
    return (
      <HudCard>
        <div data-testid="held-out-eval-card" data-state="empty">
          <span className="text-[10px] font-[Orbitron] text-[var(--text-muted)] uppercase tracking-widest">
            Voice Eval
          </span>
          <p className="text-xs text-[var(--text-muted)] mt-1">
            No evals yet.
          </p>
        </div>
      </HudCard>
    );
  }
  const historyRows = history ?? [];
  // Cap the chart at threshold×2 so a single bad run doesn't
  // flatten the rest of the curve. Floor of 10% so very good
  // runs (0% WER) still have some headroom on the chart.
  const allWers = historyRows.map((r) => r.wer_pct);
  const threshold = thresholdPct ?? 15.0;
  const chartMax = Math.max(10, threshold * 2, ...allWers);
  const viewW = 60;
  const viewH = 24;
  const points = sparklinePoints(historyRows, viewW, viewH, chartMax);
  // Threshold dashed line Y coordinate.
  const thresholdY = (viewH - (threshold / chartMax) * viewH).toFixed(2);

  return (
    <HudCard>
      <div
        data-testid="held-out-eval-card"
        data-state="ready"
        data-passed={latest.passed ? "true" : "false"}
      >
        <div className="flex items-center justify-between">
          <span className="text-[10px] font-[Orbitron] text-[var(--text-muted)] uppercase tracking-widest">
            Voice Eval
          </span>
          <span
            className={
              "text-[10px] font-[Rajdhani] uppercase tracking-widest px-1.5 py-0.5 border " +
              (latest.passed
                ? "text-[var(--accent)] border-[var(--accent)]"
                : "text-[var(--danger)] border-[var(--danger)]")
            }
          >
            {latest.passed ? "PASS" : "FAIL"}
          </span>
        </div>
        <h3
          className={
            "text-2xl font-[Rajdhani] mt-1 " +
            (latest.passed ? "text-[var(--accent)]" : "text-[var(--danger)]")
          }
        >
          {latest.wer_pct.toFixed(1)}%
          <span className="text-xs text-[var(--text-muted)] ml-1">WER</span>
        </h3>
        <p className="text-[10px] text-[var(--text-muted)] font-mono mt-0.5">
          Threshold {threshold.toFixed(1)}% · {latest.asr_backend || "unknown backend"}
        </p>
        {historyRows.length > 0 && (
          <svg
            data-testid="wer-sparkline"
            viewBox={`0 0 ${viewW} ${viewH}`}
            preserveAspectRatio="none"
            className="w-full h-6 mt-2"
            aria-label={`WER trend over last ${historyRows.length} runs`}
          >
            {/* Threshold dashed line — visual reference bar. */}
            <line
              x1="0"
              y1={thresholdY}
              x2={viewW}
              y2={thresholdY}
              stroke="var(--warning)"
              strokeWidth="0.5"
              strokeDasharray="2 2"
            />
            <polyline
              points={points}
              fill="none"
              stroke={latest.passed ? "var(--accent)" : "var(--danger)"}
              strokeWidth="1"
              strokeLinejoin="round"
              strokeLinecap="round"
            />
          </svg>
        )}
      </div>
    </HudCard>
  );
}

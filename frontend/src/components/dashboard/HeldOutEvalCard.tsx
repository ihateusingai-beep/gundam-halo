/**
 * HeldOutEvalCard — Sprint 39 + Sprint 40 cockpit card.
 *
 * Sprint 39: surfaces the held-out Cantonese eval trend on the
 * home page so the pilot sees the latest WER + a 7-run
 * sparkline without opening a terminal. Data source:
 * `GET /voice/eval-results`.
 *
 * Sprint 40 adds:
 *   1. **"Run held-out eval" button** — calls
 *      POST /voice/run-held-out-eval (background thread on the
 *      backend). The card shows a "Eval in progress… (Xs
 *      elapsed)" pill while the job runs, then auto-refreshes
 *      the sparkline when the job succeeds (via the
 *      `halo-eval-jobs` service).
 *   2. **"Run fine-tune + re-eval" button** — calls POST
 *      /voice/run-finetune. Disabled when no baseline run
 *      exists yet.
 *   3. **Improvement indicator** — when the 2 most recent
 *      trend rows use different `asr_backend` values
 *      (`whisper_local` → `whisper_hf`), render "−Z% WER
 *      improvement" with a green ↗. This is what visually
 *      closes M9-E Layer 2 acceptance criterion 6 — the
 *      pilot sees the green ↗ and knows criterion 6 is met.
 *   4. **Job state polling** — when an active job is running,
 *      poll GET /voice/run-held-out-eval/{job_id} every 3 s
 *      via the singleton subscriber in `services/halo-eval-jobs.ts`.
 *
 * Sprint 45 adds:
 *   5. **Latest-corpus hint** — fetches GET /voice/self-record-corpora
 *      on mount + every `POLL_INTERVAL_MS`. Renders a small
 *      "Will fine-tune on: <dir> (N chunks · Ms)" line above the
 *      run buttons so the pilot sees which `yue-self-<date>/`
 *      the backend will pick up. When the manifest has rejected
 *      rows, a warning span surfaces the count + tooltip
 *      pointing at the validation skip.
 *
 * Sprint 46 adds:
 *   6. **Per-corpus breakdown chart** — fetches
 *      GET /voice/eval-corpus-breakdown?limit=20 alongside the
 *      existing eval-results. Renders a stacked bar chart
 *      (one bar per run, coloured by corpus_id) below the
 *      sparkline, plus a legend row showing one chip per
 *      corpus with run count + average WER. Empty corpora /
 *      legacy runs without a `corpus_id` bucket as
 *      "unattributed" (grey).
 *
 * Render states (Sprint 39, unchanged):
 *   - **loading**: initial fetch in flight.
 *   - **empty**: no trend JSONs yet.
 *   - **ready**: at least one trend row.
 *   - **error**: fetch failed (network, 404, malformed JSON).
 *
 * Y-axis sparkline: 0% → max(threshold×2, max WER) so the
 * threshold dashed line stays visible. X-axis: oldest → newest.
 */

import { useCallback, useEffect, useState } from "react";

import { HudCard } from "@/components/gundam/HudCard";
import { CorpusBreakdownChart } from "@/components/dashboard/CorpusBreakdownChart";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import type {
  CorpusBreakdownResponse,
  EvalRunRow,
  SelfRecordCorpusSummary,
} from "@/types/api";
import {
  getActiveEvalJob,
  startTracking,
  stopTracking,
  subscribeActiveEvalJob,
} from "@/services/halo-eval-jobs";

const POLL_INTERVAL_MS = 10_000;

interface DisplayState {
  kind: "loading" | "empty" | "ready" | "error";
  latest?: EvalRunRow;
  history?: EvalRunRow[];
  thresholdPct?: number;
  error?: string;
}

function sparklinePoints(
  rows: EvalRunRow[],
  viewW: number,
  viewH: number,
  maxWer: number,
): string {
  if (rows.length === 0) return "";
  const ordered = [...rows].reverse();
  const step = ordered.length === 1 ? 0 : viewW / (ordered.length - 1);
  const y = (wer: number) => {
    const clamped = Math.min(wer, maxWer);
    return viewH - (clamped / maxWer) * viewH;
  };
  return ordered
    .map((row, i) => `${(i * step).toFixed(2)},${y(row.wer_pct).toFixed(2)}`)
    .join(" ");
}

/**
 * Compute the improvement delta between the latest 2 trend rows,
 * but ONLY if the backend changed (e.g. `whisper_local` →
 * `whisper_hf`). Same-backend re-runs never claim "improvement"
 * (would be noise).
 *
 * Returns `{ improvement_pp, improvement_pct, met_criterion_6 }`
 * or `null` if there isn't enough history.
 */
function computeImprovement(
  latest: EvalRunRow | undefined,
  previous: EvalRunRow | undefined,
  thresholdPct: number | undefined,
): {
  improvement_pp: number;
  improvement_pct: number;
  metCriterion6: boolean;
} | null {
  if (!latest || !previous) return null;
  if (previous.asr_backend === latest.asr_backend) return null;
  const pp = previous.wer_pct - latest.wer_pct;
  const pct =
    previous.wer_pct > 0 ? (pp / previous.wer_pct) * 100 : 0;
  return {
    improvement_pp: pp,
    improvement_pct: pct,
    metCriterion6: latest.wer_pct < (thresholdPct ?? 10.0),
  };
}

export function HeldOutEvalCard() {
  const [display, setDisplay] = useState<DisplayState>({ kind: "loading" });
  const [startingEval, setStartingEval] = useState(false);
  const [startingFinetune, setStartingFinetune] = useState(false);
  const [activeJob, setActiveJob] = useState(() => getActiveEvalJob());
  // Sprint 45: latest self-record corpus summary (drives the
  // "Will fine-tune on: ..." hint above the buttons).
  const [latestCorpus, setLatestCorpus] = useState<SelfRecordCorpusSummary | null>(null);
  // Sprint 46: per-corpus WER breakdown for the stacked chart.
  const [corpusBreakdown, setCorpusBreakdown] = useState<CorpusBreakdownResponse | null>(null);

  // Subscribe to active-job transitions (driven by halo-eval-jobs).
  useEffect(() => {
    const unsub = subscribeActiveEvalJob((j) => setActiveJob(j));
    return unsub;
  }, []);

  const fetchLatestCorpus = useCallback(async () => {
    try {
      const res = await api.listSelfRecordCorpora();
      // Backend already sorts newest-first; pick the first item
      // (or `latest_path` field if exposed). Falls back to null
      // when the user hasn't recorded anything yet.
      setLatestCorpus(res.corpora[0] ?? null);
    } catch (e) {
      console.warn("[HeldOutEvalCard] failed to list corpora:", e);
      setLatestCorpus(null);
    }
  }, []);

  // Sprint 46: per-corpus breakdown for the stacked chart.
  // Cheap call (just reads existing trend JSONs), polled at the
  // same cadence as eval-results.
  const fetchCorpusBreakdown = useCallback(async () => {
    try {
      const res = await api.getEvalCorpusBreakdown(20);
      setCorpusBreakdown(res);
    } catch (e) {
      console.warn("[HeldOutEvalCard] failed to fetch corpus breakdown:", e);
      setCorpusBreakdown(null);
    }
  }, []);

  const fetchResults = useCallback(async () => {
    try {
      const res = await api.getVoiceEvalResults();
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
      setDisplay({
        kind: "error",
        error: e instanceof Error ? e.message : String(e),
      });
    }
  }, []);

  // Initial + periodic poll.
  useEffect(() => {
    void fetchResults();
    void fetchLatestCorpus();
    void fetchCorpusBreakdown();
    const id = setInterval(() => {
      void fetchResults();
      void fetchCorpusBreakdown();
    }, POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [fetchResults, fetchLatestCorpus, fetchCorpusBreakdown]);

  // When an active fine-tune finishes, refresh corpora list
  // (the user may record more between runs).
  useEffect(() => {
    if (activeJob?.job.status === "succeeded" && activeJob.job.kind === "finetune") {
      void fetchLatestCorpus();
    }
  }, [activeJob, fetchLatestCorpus]);

  // When an active job completes (succeeded), refresh the eval-results.
  useEffect(() => {
    if (activeJob?.job.status === "succeeded" && activeJob.job.kind === "held-out-eval") {
      void fetchResults();
      void fetchCorpusBreakdown();
    }
  }, [activeJob, fetchResults, fetchCorpusBreakdown]);

  // ---- Async handlers ----

  async function handleRunEval() {
    setStartingEval(true);
    try {
      const res = await api.startHeldOutEval({ threshold: display.thresholdPct ?? 15.0 });
      // The endpoint returns {job_id, status}. The full EvalJob
      // object is fetched by the polling ticker in the service.
      // Seed it now so the UI shows "running…" immediately.
      startTracking({
        job_id: res.job_id,
        kind: "held-out-eval",
        status: "pending",
        started_at: new Date().toISOString(),
        finished_at: null,
        exit_code: null,
        log_path: null,
        trend_json_path: null,
        report_path: null,
        error: null,
      });
    } catch (e) {
      setDisplay({
        kind: "error",
        error: e instanceof Error ? e.message : String(e),
      });
    } finally {
      setStartingEval(false);
    }
  }

  async function handleRunFinetune() {
    setStartingFinetune(true);
    try {
      const res = await api.startFinetune();
      startTracking({
        job_id: res.job_id,
        kind: "finetune",
        status: "pending",
        started_at: new Date().toISOString(),
        finished_at: null,
        exit_code: null,
        log_path: null,
        trend_json_path: null,
        report_path: null,
        error: null,
      });
    } catch (e) {
      setDisplay({
        kind: "error",
        error: e instanceof Error ? e.message : String(e),
      });
    } finally {
      setStartingFinetune(false);
    }
  }

  // ---- Render branches ----
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
          <RunEvalButton
            onClick={handleRunEval}
            busy={startingEval}
            disabled={!!activeJob && activeJob.job.status === "running"}
          />
        </div>
      </HudCard>
    );
  }

  // ---- Ready ----
  const { latest, history, thresholdPct } = display;
  // The "ready" branch is only taken when `latest` is defined;
  // the DisplayState type still allows undefined because the
  // kind discriminant doesn't narrow optional fields. We bail
  // explicitly so TS is happy without an `!` assertion.
  if (!latest) {
    return (
      <HudCard>
        <div data-testid="held-out-eval-card" data-state="empty">
          <span className="text-[10px] font-[Orbitron] text-[var(--text-muted)] uppercase tracking-widest">
            Voice Eval
          </span>
          <p className="text-xs text-[var(--text-muted)] mt-1">No data.</p>
        </div>
      </HudCard>
    );
  }
  const historyRows = history ?? [];
  const previous = historyRows[1];
  const improvement = computeImprovement(latest, previous, thresholdPct);
  const allWers = historyRows.map((r) => r.wer_pct);
  const threshold = thresholdPct ?? 15.0;
  const chartMax = Math.max(10, threshold * 2, ...allWers);
  const viewW = 60;
  const viewH = 24;
  const points = sparklinePoints(historyRows, viewW, viewH, chartMax);
  const thresholdY = (viewH - (threshold / chartMax) * viewH).toFixed(2);
  const hasBaseline = !!previous; // enables the fine-tune button

  // Active job state — render the in-progress pill.
  const active = activeJob;
  const activeIsRunning = active && active.job.status === "running";
  const elapsedSec = active
    ? Math.floor((Date.now() - active.startedAtMs) / 1000)
    : 0;

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
            className={cn(
              "text-[10px] font-[Rajdhani] uppercase tracking-widest px-1.5 py-0.5 border",
              latest.passed
                ? "text-[var(--accent)] border-[var(--accent)]"
                : "text-[var(--danger)] border-[var(--danger)]",
            )}
          >
            {latest.passed ? "PASS" : "FAIL"}
          </span>
        </div>
        <h3
          className={cn(
            "text-2xl font-[Rajdhani] mt-1",
            latest.passed ? "text-[var(--accent)]" : "text-[var(--danger)]",
          )}
        >
          {latest.wer_pct.toFixed(1)}%
          <span className="text-xs text-[var(--text-muted)] ml-1">WER</span>
        </h3>

        {/* Sprint 40 — improvement badge (only when backend changed). */}
        {improvement && improvement.improvement_pp > 0 && (
          <p
            data-testid="improvement-badge"
            data-met-criterion-6={improvement.metCriterion6 ? "true" : "false"}
            className={cn(
              "text-[11px] font-[Rajdhani] mt-1",
              improvement.metCriterion6
                ? "text-[var(--accent)]"
                : "text-[var(--warning)]",
            )}
          >
            ↗ −{improvement.improvement_pp.toFixed(1)}pp WER
            <span className="text-[10px] text-[var(--text-muted)] ml-1">
              (−{improvement.improvement_pct.toFixed(1)}%)
            </span>
            {improvement.metCriterion6 && (
              <span className="text-[10px] ml-1">
                · ✓ M9-E criterion 6
              </span>
            )}
          </p>
        )}

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

        {/* Sprint 46 — per-corpus breakdown (stacked bars + legend). */}
        {corpusBreakdown && corpusBreakdown.timeline.length > 1 && (
          <CorpusBreakdownChart
            timeline={corpusBreakdown.timeline}
            byCorpus={corpusBreakdown.by_corpus}
            threshold={threshold}
          />
        )}

        {/* Active job indicator — Sprint 40. */}
        {active && (
          <div
            data-testid="active-job-pill"
            data-job-kind={active.job.kind}
            data-job-status={active.job.status}
            className="mt-2 flex items-center justify-between gap-2 px-2 py-1 border border-[var(--accent)]/40 bg-[var(--accent)]/5"
          >
            <span className="text-[10px] font-mono text-[var(--accent)]">
              {activeIsRunning ? "● " : ""}
              {active.job.kind === "finetune" ? "Fine-tune" : "Eval"}:{" "}
              {active.job.status}
              {activeIsRunning && ` (${elapsedSec}s)`}
            </span>
            <button
              data-testid="cancel-job"
              onClick={() => stopTracking()}
              className="text-[10px] font-mono text-[var(--text-muted)] hover:text-[var(--danger)]"
              title="Stop tracking. Does NOT kill the backend subprocess."
            >
              dismiss
            </button>
          </div>
        )}

        {/* Sprint 45 — latest-corpus hint above the fine-tune button.
            Renders only when at least one yue-self-* dir exists.
            Shows the resolved path + chunk count + duration, plus
            a warning span if the manifest has rejected lines. */}
        {latestCorpus && (
          <div
            data-testid="latest-corpus-hint"
            className="mt-2 text-[10px] font-mono text-[var(--text-muted)]"
          >
            Will fine-tune on:{" "}
            <span
              className="text-[var(--accent)]"
              data-testid="latest-corpus-path"
              title={latestCorpus.path}
            >
              {latestCorpus.path.split("/").slice(-2).join("/")}
            </span>
            <br />
            <span data-testid="latest-corpus-meta">
              {latestCorpus.manifest_chunks} chunks ·{" "}
              {latestCorpus.total_duration_s.toFixed(1)}s
              {latestCorpus.rejected_lines > 0 && (
                <>
                  {" · "}
                  <span
                    data-testid="latest-corpus-rejected"
                    className="text-[var(--warning)]"
                    title={`${latestCorpus.rejected_lines} manifest row(s) failed schema validation and were skipped`}
                  >
                    {latestCorpus.rejected_lines} rejected
                  </span>
                </>
              )}
            </span>
          </div>
        )}

        {/* Run buttons — Sprint 40. */}
        <div className="mt-2 flex items-center gap-2 flex-wrap">
          <RunEvalButton
            onClick={handleRunEval}
            busy={startingEval}
            disabled={!!activeIsRunning}
          />
          <RunFinetuneButton
            onClick={handleRunFinetune}
            busy={startingFinetune}
            disabled={!hasBaseline || !!activeIsRunning}
            disabledReason={
              !hasBaseline
                ? "Run a baseline eval first"
                : undefined
            }
          />
        </div>
      </div>
    </HudCard>
  );
}

// ---------------------------------------------------------------------------
// Sub-buttons
// ---------------------------------------------------------------------------

interface RunButtonProps {
  onClick: () => void;
  busy: boolean;
  disabled: boolean;
  disabledReason?: string;
}

function RunEvalButton({ onClick, busy, disabled }: RunButtonProps) {
  return (
    <button
      data-testid="run-eval-button"
      onClick={onClick}
      disabled={busy || disabled}
      className={cn(
        "px-3 py-1 text-[10px] uppercase tracking-wider font-[Rajdhani] border",
        "border-[var(--accent)] text-[var(--accent)] hover:bg-[var(--accent)] hover:text-[var(--bg-primary)]",
        "transition-colors disabled:opacity-40 disabled:cursor-not-allowed",
      )}
    >
      {busy ? "Starting…" : "Run eval"}
    </button>
  );
}

function RunFinetuneButton({
  onClick,
  busy,
  disabled,
  disabledReason,
}: RunButtonProps) {
  return (
    <button
      data-testid="run-finetune-button"
      onClick={onClick}
      disabled={busy || disabled}
      title={disabledReason}
      className={cn(
        "px-3 py-1 text-[10px] uppercase tracking-wider font-[Rajdhani] border",
        "border-[var(--warning)] text-[var(--warning)] hover:bg-[var(--warning)] hover:text-[var(--bg-primary)]",
        "transition-colors disabled:opacity-40 disabled:cursor-not-allowed",
      )}
    >
      {busy ? "Starting…" : "Fine-tune + re-eval"}
    </button>
  );
}
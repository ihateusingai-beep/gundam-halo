/**
 * halo-eval-jobs.ts — Sprint 40 background eval job tracker.
 *
 * Mirrors the `services/halo-watchdog-events.ts` pattern from
 * Sprint 43 — module-level singleton + console-debug global
 * (`window.__haloEval`) + subscribe() API. The HeldOutEvalCard
 * uses this to:
 *
 *   1. Poll GET /voice/run-held-out-eval/{job_id} every 3 s
 *      while a job is in flight.
 *   2. Notify subscribers when a job transitions to
 *      succeeded / failed.
 *   3. Auto-refetch /voice/eval-results when a held-out-eval
 *      succeeds (so the HeldOutEvalCard sparkline updates
 *      without a manual page reload).
 *
 * Outside the Tauri shell (web dev mode), the polling still
 * works — the GET endpoint doesn't require Tauri.
 */

import type { EvalJob } from "@/types/api";

import { api } from "@/lib/api";

/** Active job snapshot — null when no job is in flight. */
export interface ActiveEvalJob {
  job: EvalJob;
  /** Monotonic ms when polling started; used for "X seconds elapsed" UI. */
  startedAtMs: number;
}

let activeJob: ActiveEvalJob | null = null;
let pollHandle: ReturnType<typeof setInterval> | null = null;
const subscribers: Set<(j: ActiveEvalJob | null) => void> = new Set();

/** Polling interval while a job is running (3 s — same as the
 * watchdog's /api/health cadence). */
const POLL_INTERVAL_MS = 3_000;

/** Stop polling + clear active job. Idempotent. */
function _stopPolling() {
  if (pollHandle !== null) {
    clearInterval(pollHandle);
    pollHandle = null;
  }
}

/** Notify all subscribers + write console-debug. */
function _broadcast() {
  for (const cb of subscribers) {
    try {
      cb(activeJob);
    } catch (e) {
      console.warn("[halo-eval] subscriber threw:", e);
    }
  }
  if (typeof window !== "undefined") {
    const w = window as any;
    w.__haloEval = { getActiveJob: () => activeJob };
  }
  // eslint-disable-next-line no-console
  console.debug("[halo-eval]", activeJob);
}

/**
 * Start polling a job. Idempotent — calling with the same
 * job_id is a no-op. Stops when the job reaches a terminal
 * state (succeeded / failed) or when stopTracking() is called.
 */
export function startTracking(job: EvalJob): void {
  if (typeof window === "undefined") return;
  if (activeJob?.job.job_id === job.job_id) return;

  activeJob = { job, startedAtMs: Date.now() };
  _stopPolling();

  const tick = async () => {
    if (!activeJob) return;
    try {
      const next = await api.getHeldOutEvalJob(activeJob.job.job_id);
      // 404 = job was reaped (or backend restarted) — mark failed.
      const job: EvalJob =
        next ?? {
          ...activeJob.job,
          status: "failed",
          error: "job_not_found",
          finished_at: new Date().toISOString(),
          exit_code: -1,
        };
      activeJob = { ...activeJob, job };
      _broadcast();

      // Terminal state — stop polling + auto-refresh eval-results.
      if (job.status === "succeeded" || job.status === "failed") {
        _stopPolling();
        if (job.status === "succeeded" && job.kind === "held-out-eval") {
          // Fire-and-forget — the HeldOutEvalCard's own subscriber
          // will refetch when this resolves.
          window.dispatchEvent(new CustomEvent("halo-eval-results-stale"));
        }
      }
    } catch (e) {
      console.warn("[halo-eval] poll failed:", e);
      // Keep polling — transient network blip.
    }
  };

  // Initial tick + recurring.
  void tick();
  pollHandle = setInterval(tick, POLL_INTERVAL_MS);
}

/** Stop tracking the current job (cancel button on the card). */
export function stopTracking(): void {
  activeJob = null;
  _stopPolling();
  _broadcast();
}

/** Read the current active job snapshot. */
export function getActiveEvalJob(): ActiveEvalJob | null {
  return activeJob;
}

/** Subscribe to active-job transitions. Returns an unsubscribe fn. */
export function subscribeActiveEvalJob(
  cb: (j: ActiveEvalJob | null) => void,
): () => void {
  subscribers.add(cb);
  cb(activeJob);
  return () => {
    subscribers.delete(cb);
  };
}

/** Test-only — reset module state. */
export function _resetEvalJobsForTests(): void {
  activeJob = null;
  _stopPolling();
  subscribers.clear();
  if (typeof window !== "undefined") {
    delete (window as any).__haloEval;
  }
}
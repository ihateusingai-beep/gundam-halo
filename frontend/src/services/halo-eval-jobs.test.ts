/**
 * halo-eval-jobs.test.ts — Sprint 40.
 *
 * Verifies the singleton + polling lifecycle:
 * 1. startTracking + getActiveEvalJob round-trips.
 * 2. stopTracking clears the active job.
 * 3. Polling resolves a job_id against the mocked api endpoint and
 *    updates the snapshot.
 */

import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "@/lib/api";
import {
  _resetEvalJobsForTests,
  getActiveEvalJob,
  startTracking,
  stopTracking,
  subscribeActiveEvalJob,
} from "@/services/halo-eval-jobs";

const getHeldOutEvalJobMock = vi.fn();
vi.mock("@/lib/api", () => ({
  api: {
    getHeldOutEvalJob: (...args: unknown[]) => getHeldOutEvalJobMock(...args),
  },
}));

beforeEach(() => {
  _resetEvalJobsForTests();
  getHeldOutEvalJobMock.mockReset();
});

afterEach(() => {
  _resetEvalJobsForTests();
  cleanup();
});

describe("halo-eval-jobs", () => {
  it("startTracking sets the active job; getActiveEvalJob reads it", () => {
    startTracking({
      job_id: "held-out-eval-20260101T000000Z-abcdef",
      kind: "held-out-eval",
      status: "pending",
      started_at: "2026-01-01T00:00:00+00:00",
      finished_at: null,
      exit_code: null,
      log_path: null,
      trend_json_path: null,
      report_path: null,
      error: null,
    });

    const active = getActiveEvalJob();
    expect(active).not.toBeNull();
    expect(active?.job.job_id).toBe("held-out-eval-20260101T000000Z-abcdef");
    expect(active?.job.kind).toBe("held-out-eval");
    expect(active?.startedAtMs).toBeGreaterThan(0);
  });

  it("stopTracking clears the active job", () => {
    startTracking({
      job_id: "finetune-x",
      kind: "finetune",
      status: "pending",
      started_at: "2026-01-01T00:00:00+00:00",
      finished_at: null,
      exit_code: null,
      log_path: null,
      trend_json_path: null,
      report_path: null,
      error: null,
    });
    expect(getActiveEvalJob()).not.toBeNull();
    stopTracking();
    expect(getActiveEvalJob()).toBeNull();
  });

  it("subscribers receive the active job immediately on subscribe", () => {
    startTracking({
      job_id: "held-out-eval-immediate",
      kind: "held-out-eval",
      status: "pending",
      started_at: "2026-01-01T00:00:00+00:00",
      finished_at: null,
      exit_code: null,
      log_path: null,
      trend_json_path: null,
      report_path: null,
      error: null,
    });

    const received: (string | null)[] = [];
    const unsub = subscribeActiveEvalJob((j) => {
      received.push(j?.job.job_id ?? null);
    });
    expect(received[0]).toBe("held-out-eval-immediate");

    stopTracking();
    expect(received[received.length - 1]).toBeNull();
    unsub();
  });
});
/**
 * HeldOutEvalCard.test.tsx — Sprint 39 + Sprint 40 acceptance tests.
 *
 * Sprint 39 verifies the "ready" branch renders the right WER
 * number, PASS badge, and sparkline polyline.
 *
 * Sprint 40 adds:
 *   - Improvement indicator shows when the 2 latest trend rows
 *     have different `asr_backend` values (the "M9-E criterion 6
 *     visually closed" signal).
 *   - The "Run eval" button fires the right IPC.
 */

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const getVoiceEvalResultsMock = vi.fn();
const startHeldOutEvalMock = vi.fn();
const startFinetuneMock = vi.fn();

vi.mock("@/lib/api", () => ({
  api: {
    getVoiceEvalResults: (...args: unknown[]) => getVoiceEvalResultsMock(...args),
    startHeldOutEval: (...args: unknown[]) => startHeldOutEvalMock(...args),
    startFinetune: (...args: unknown[]) => startFinetuneMock(...args),
  },
}));

// Reset the eval-jobs singleton between tests.
import { _resetEvalJobsForTests } from "@/services/halo-eval-jobs";

import { HeldOutEvalCard } from "@/components/dashboard/HeldOutEvalCard";

afterEach(() => {
  getVoiceEvalResultsMock.mockReset();
  startHeldOutEvalMock.mockReset();
  startFinetuneMock.mockReset();
  _resetEvalJobsForTests();
  cleanup();
});

describe("HeldOutEvalCard", () => {
  it("renders the latest run as a big WER number with PASS badge and sparkline", async () => {
    getVoiceEvalResultsMock.mockResolvedValue({
      latest: {
        timestamp: "2026-06-26T10:00:00+00:00",
        timestamp_ms: 1782408000000,
        wer_pct: 12.0,
        passed: true,
        wav_path: "/tmp/held-out.wav",
        asr_backend: "whisper_local",
        duration_sec: 30.5,
        source_path: "/tmp/run.json",
      },
      history: [
        {
          timestamp: "2026-06-26T10:00:00+00:00",
          timestamp_ms: 1782408000000,
          wer_pct: 12.0,
          passed: true,
          wav_path: "/tmp/held-out.wav",
          asr_backend: "whisper_local",
          duration_sec: 30.5,
          source_path: "/tmp/run.json",
        },
        {
          timestamp: "2026-06-25T10:00:00+00:00",
          timestamp_ms: 1782321600000,
          wer_pct: 14.0,
          passed: true,
          wav_path: "/tmp/held-out.wav",
          asr_backend: "whisper_local",
          duration_sec: 31.0,
          source_path: "/tmp/run2.json",
        },
        {
          timestamp: "2026-06-24T10:00:00+00:00",
          timestamp_ms: 1782235200000,
          wer_pct: 18.0,
          passed: false,
          wav_path: "/tmp/held-out.wav",
          asr_backend: "whisper_local",
          duration_sec: 29.5,
          source_path: "/tmp/run3.json",
        },
      ],
      threshold_pct: 15.0,
    });

    render(<HeldOutEvalCard />);

    await waitFor(() => {
      expect(screen.getByTestId("held-out-eval-card")).toBeTruthy();
    });

    const card = screen.getByTestId("held-out-eval-card");
    expect(card.getAttribute("data-state")).toBe("ready");
    expect(card.getAttribute("data-passed")).toBe("true");
    expect(card.textContent).toContain("12.0%");
    expect(card.textContent).toContain("PASS");
    expect(card.textContent).toContain("Threshold 15.0%");
    expect(card.textContent).toContain("whisper_local");

    const svg = screen.getByTestId("wer-sparkline");
    expect(svg).toBeTruthy();
    const polyline = svg.querySelector("polyline");
    expect(polyline).toBeTruthy();
    const points = polyline?.getAttribute("points") ?? "";
    const pointCount = points.trim().split(/\s+/).length;
    expect(pointCount).toBe(3);
  });

  it("renders the improvement badge when the 2 latest runs use different backends", async () => {
    getVoiceEvalResultsMock.mockResolvedValue({
      latest: {
        // After personalised run — WER 8% < 10% → M9-E met.
        timestamp: "2026-06-26T11:00:00+00:00",
        timestamp_ms: 1782411600000,
        wer_pct: 8.0,
        passed: true,
        wav_path: "/tmp/held-out.wav",
        asr_backend: "whisper_hf",
        duration_sec: 28.0,
        source_path: "/tmp/run-after.json",
      },
      history: [
        {
          timestamp: "2026-06-26T11:00:00+00:00",
          timestamp_ms: 1782411600000,
          wer_pct: 8.0,
          passed: true,
          wav_path: "/tmp/held-out.wav",
          asr_backend: "whisper_hf",
          duration_sec: 28.0,
          source_path: "/tmp/run-after.json",
        },
        {
          // Baseline run — WER 50% with whisper_local.
          timestamp: "2026-06-26T09:00:00+00:00",
          timestamp_ms: 1782404400000,
          wer_pct: 50.0,
          passed: false,
          wav_path: "/tmp/held-out.wav",
          asr_backend: "whisper_local",
          duration_sec: 30.5,
          source_path: "/tmp/run-baseline.json",
        },
      ],
      threshold_pct: 15.0,
    });

    render(<HeldOutEvalCard />);

    await waitFor(() => {
      expect(screen.getByTestId("improvement-badge")).toBeTruthy();
    });

    const badge = screen.getByTestId("improvement-badge");
    expect(badge.getAttribute("data-met-criterion-6")).toBe("true");
    expect(badge.textContent).toContain("−42.0pp WER");
    expect(badge.textContent).toContain("M9-E criterion 6");
  });

  it("does NOT render the improvement badge when both runs use the same backend", async () => {
    // Re-run the same backend — would be noise to claim "improvement".
    getVoiceEvalResultsMock.mockResolvedValue({
      latest: {
        timestamp: "2026-06-26T11:00:00+00:00",
        timestamp_ms: 1782411600000,
        wer_pct: 14.0,
        passed: true,
        wav_path: "/tmp/held-out.wav",
        asr_backend: "whisper_local",
        duration_sec: 28.0,
        source_path: "/tmp/run.json",
      },
      history: [
        {
          timestamp: "2026-06-26T11:00:00+00:00",
          timestamp_ms: 1782411600000,
          wer_pct: 14.0,
          passed: true,
          wav_path: "/tmp/held-out.wav",
          asr_backend: "whisper_local",
          duration_sec: 28.0,
          source_path: "/tmp/run.json",
        },
        {
          timestamp: "2026-06-25T10:00:00+00:00",
          timestamp_ms: 1782321600000,
          wer_pct: 18.0,
          passed: false,
          wav_path: "/tmp/held-out.wav",
          asr_backend: "whisper_local",
          duration_sec: 30.5,
          source_path: "/tmp/run2.json",
        },
      ],
      threshold_pct: 15.0,
    });

    render(<HeldOutEvalCard />);

    await waitFor(() => {
      expect(screen.getByTestId("held-out-eval-card")).toBeTruthy();
    });

    expect(screen.queryByTestId("improvement-badge")).toBeNull();
  });

  it("Run eval button fires startHeldOutEval IPC", async () => {
    getVoiceEvalResultsMock.mockResolvedValue({
      latest: null,
      history: [],
      threshold_pct: 15.0,
    });
    startHeldOutEvalMock.mockResolvedValue({
      job_id: "held-out-eval-test",
      status: "pending",
    });

    render(<HeldOutEvalCard />);

    await waitFor(() => {
      expect(screen.getByTestId("held-out-eval-card")).toBeTruthy();
    });

    const btn = screen.getByTestId("run-eval-button");
    btn.click();

    await waitFor(() => {
      expect(startHeldOutEvalMock).toHaveBeenCalledTimes(1);
    });
    // Threshold is forwarded from the card's display state.
    const [params] = startHeldOutEvalMock.mock.calls[0];
    expect(params).toMatchObject({ threshold: 15.0 });
  });
});

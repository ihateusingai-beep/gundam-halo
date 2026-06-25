/**
 * HeldOutEvalCard.test.tsx — Sprint 39 Track B acceptance test.
 *
 * Verifies the "ready" branch renders the right WER number, PASS
 * badge, and sparkline polyline. The empty / error branches are
 * covered by the live smoke (manual); unit-testing them would
 * just duplicate the same DOM assertions for slightly different
 * text content.
 *
 * Mocking strategy:
 *   - `api.getVoiceEvalResults` is mocked to return 3 valid runs
 *     (newest first: 18% → 14% → 12%) below the 15% threshold
 *     so the latest passes.
 *   - The 10s interval is not exercised.
 */

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const getVoiceEvalResultsMock = vi.fn();
vi.mock("@/lib/api", () => ({
  api: {
    getVoiceEvalResults: (...args: unknown[]) => getVoiceEvalResultsMock(...args),
  },
}));

import { HeldOutEvalCard } from "@/components/dashboard/HeldOutEvalCard";

afterEach(() => {
  getVoiceEvalResultsMock.mockReset();
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

    // The WER is shown to 1 dp + a "WER" suffix label.
    expect(card.textContent).toContain("12.0%");
    expect(card.textContent).toContain("WER");

    // The PASS badge is rendered as uppercase text.
    expect(card.textContent).toContain("PASS");

    // The threshold + backend are surfaced.
    expect(card.textContent).toContain("Threshold 15.0%");
    expect(card.textContent).toContain("whisper_local");

    // The sparkline SVG renders with exactly 3 polyline points
    // (one per run, oldest-first after the render-side reverse).
    const svg = screen.getByTestId("wer-sparkline");
    expect(svg).toBeTruthy();
    const polyline = svg.querySelector("polyline");
    expect(polyline).toBeTruthy();
    const points = polyline?.getAttribute("points") ?? "";
    // 3 runs → 3 (x,y) pairs.
    const pointCount = points.trim().split(/\s+/).length;
    expect(pointCount).toBe(3);
  });
});

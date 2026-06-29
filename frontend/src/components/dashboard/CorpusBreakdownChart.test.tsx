/**
 * CorpusBreakdownChart.test.tsx — Sprint 46 acceptance tests.
 *
 * Coverage (3 tests):
 * 1. Renders one bar per timeline entry.
 * 2. Legend chips show run count + avg WER.
 * 3. corpusColor() is stable — same id → same colour.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import {
  CorpusBreakdownChart,
  corpusColor,
} from "@/components/dashboard/CorpusBreakdownChart";
import type {
  CorpusBreakdownResponse,
} from "@/types/api";

afterEach(() => {
  cleanup();
});

describe("CorpusBreakdownChart", () => {
  it("renders one bar per timeline entry", () => {
    const by_corpus: CorpusBreakdownResponse["by_corpus"] = {
      "self:2026-06-27": {
        run_count: 2,
        latest_wer_pct: 8.0,
        best_wer_pct: 6.0,
        avg_wer_pct: 7.0,
        first_seen_ms: 1782408000000,
        latest_seen_ms: 1782411600000,
        passed: true,
      },
    };
    const timeline = [
      {
        timestamp: "2026-06-27T10:00:00+00:00",
        timestamp_ms: 1782408000000,
        wer_pct: 8.0,
        corpus_id: "self:2026-06-27",
        asr_backend: "whisper_hf",
      },
      {
        timestamp: "2026-06-27T11:00:00+00:00",
        timestamp_ms: 1782411600000,
        wer_pct: 6.0,
        corpus_id: "self:2026-06-27",
        asr_backend: "whisper_hf",
      },
    ];

    render(
      <CorpusBreakdownChart
        timeline={timeline}
        byCorpus={by_corpus}
        threshold={15.0}
      />,
    );

    const bars = screen.getAllByTestId("corpus-bar");
    expect(bars).toHaveLength(2);
    // Each bar carries the corpus_id for colour grouping.
    expect(bars[0].getAttribute("data-corpus-id")).toBe("self:2026-06-27");
    expect(bars[1].getAttribute("data-corpus-id")).toBe("self:2026-06-27");
  });

  it("renders legend chips with run count and avg WER", () => {
    const by_corpus: CorpusBreakdownResponse["by_corpus"] = {
      "self:2026-06-27": {
        run_count: 3,
        latest_wer_pct: 6.0,
        best_wer_pct: 6.0,
        avg_wer_pct: 7.0,
        first_seen_ms: 1782408000000,
        latest_seen_ms: 1782415200000,
        passed: true,
      },
      "common-voice-yue": {
        run_count: 1,
        latest_wer_pct: 12.0,
        best_wer_pct: 12.0,
        avg_wer_pct: 12.0,
        first_seen_ms: 1782400000000,
        latest_seen_ms: 1782400000000,
        passed: true,
      },
    };
    const timeline = [
      {
        timestamp: "2026-06-27T10:00:00+00:00",
        timestamp_ms: 1782408000000,
        wer_pct: 6.0,
        corpus_id: "self:2026-06-27",
        asr_backend: "whisper_hf",
      },
    ];

    render(
      <CorpusBreakdownChart
        timeline={timeline}
        byCorpus={by_corpus}
        threshold={15.0}
      />,
    );

    const chips = screen.getAllByTestId("corpus-legend-chip");
    expect(chips).toHaveLength(2);
    // Newest first.
    expect(chips[0].getAttribute("data-corpus-id")).toBe("self:2026-06-27");
    expect(chips[1].getAttribute("data-corpus-id")).toBe("common-voice-yue");
    // First chip shows "3 runs · avg 7.0%".
    expect(chips[0].textContent).toContain("3 runs");
    expect(chips[0].textContent).toContain("avg 7.0%");
  });

  it("corpusColor() is stable — same id → same colour", () => {
    const a = corpusColor("self:2026-06-27");
    const b = corpusColor("self:2026-06-27");
    expect(a).toBe(b);
    // Different corpus → almost certainly different colour.
    const c = corpusColor("common-voice-yue");
    expect(c).not.toBe(a);
    // Unattributed always → grey.
    expect(corpusColor("")).toBe(corpusColor("unattributed"));
    expect(corpusColor("")).toBe("var(--text-muted)");
  });
});

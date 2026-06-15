/**
 * Tests for useSharedAmplitude (Sprint 17b Track E).
 *
 * We verify the dual-source contract:
 *   - default (no arg): idle drift returns ~baseline ± small noise
 *   - source="idle"  : same as default
 *   - source="mic" with no stream: amplitude=0
 *   - source="mic" with a stream: useMicAnalyser is invoked
 *     and its amplitude value flows through
 *
 * We use vitest fake timers to fast-forward the idle drift
 * loop (50ms tick) without wall-clock waiting. We also stub
 * the AnalyserNode in jsdom so the mic path doesn't require
 * a real AudioContext.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook } from "@testing-library/react";

// Mock useMicAnalyser so we don't have to set up a real
// AudioContext in jsdom. The vi.mock factory is hoisted
// to the top of the file BEFORE any other statement runs,
// so we can't reference a module-level variable from
// inside the factory. Instead, we read the amplitude
// value AND record the latest stream arg via globalThis
// properties that the test body mutates between
// assertions. The factory returns a fresh vi.fn whose
// behaviour reads the same globals.
(globalThis as { __MOCK_MIC_AMP__?: number }).__MOCK_MIC_AMP__ = 0;
(
  globalThis as { __MOCK_MIC_LAST_STREAM__?: MediaStream | null | undefined }
).__MOCK_MIC_LAST_STREAM__ = null;
vi.mock("@/hooks/use-mic-analyser", () => ({
  useMicAnalyser: vi.fn(
    (stream: MediaStream | null | undefined) => {
      // Record the stream arg for assertion
      (
        globalThis as {
          __MOCK_MIC_LAST_STREAM__?: MediaStream | null | undefined;
        }
      ).__MOCK_MIC_LAST_STREAM__ = stream;
      const amp =
        (globalThis as { __MOCK_MIC_AMP__?: number }).__MOCK_MIC_AMP__ ?? 0;
      return {
        amplitude: amp,
        active: amp > 0,
        error: null,
      };
    },
  ),
}));

// Import after vi.mock so the mock takes effect.
import { useSharedAmplitude } from "@/hooks/use-shared-amplitude";

function setMockMicAmplitude(v: number) {
  (globalThis as { __MOCK_MIC_AMP__?: number }).__MOCK_MIC_AMP__ = v;
}

function getLastMicStream(): MediaStream | null | undefined {
  return (
    globalThis as { __MOCK_MIC_LAST_STREAM__?: MediaStream | null | undefined }
  ).__MOCK_MIC_LAST_STREAM__;
}

describe("useSharedAmplitude — source='idle' (default)", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    setMockMicAmplitude(0);
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("returns the idle drift baseline when no source is passed", () => {
    const { result } = renderHook(() => useSharedAmplitude());
    expect(result.current).toBeGreaterThan(0.0);
    expect(result.current).toBeLessThanOrEqual(1.0);
  });

  it("returns the idle drift when source='idle' is explicit", () => {
    const { result } = renderHook(() => useSharedAmplitude("idle"));
    expect(result.current).toBeGreaterThan(0.0);
    expect(result.current).toBeLessThanOrEqual(1.0);
  });
});

describe("useSharedAmplitude — source='mic' (Sprint 17b Track E)", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    setMockMicAmplitude(0);
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("returns 0 when source='mic' but no stream is provided", () => {
    const { result } = renderHook(() =>
      useSharedAmplitude("mic", null),
    );
    expect(result.current).toBe(0);
  });

  it("threads the stream through to useMicAnalyser", () => {
    // The mock factory records the latest stream arg on
    // globalThis. We assert the hook's "mic" branch passes
    // our fake stream through to useMicAnalyser unchanged.
    const fakeAmplitude = 0.42;
    setMockMicAmplitude(fakeAmplitude);
    const fakeStream = {} as MediaStream;
    const { result } = renderHook(() =>
      useSharedAmplitude("mic", fakeStream),
    );
    expect(result.current).toBe(fakeAmplitude);
    // The mock factory stored the stream it was called with;
    // assert it matches what we passed in.
    expect(getLastMicStream()).toBe(fakeStream);
  });

  it("flips amplitude reactively when source prop changes from 'idle' to 'mic'", () => {
    // First render with idle — returns baseline drift
    setMockMicAmplitude(0);
    const { result, rerender } = renderHook(
      ({ source }: { source: "idle" | "mic" }) =>
        useSharedAmplitude(source, null),
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      { initialProps: { source: "idle" as any } },
    );
    const idleValue = result.current;
    expect(idleValue).toBeGreaterThan(0.0);

    // Flip to "mic" with no stream — useMicAnalyser returns 0
    setMockMicAmplitude(0);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    rerender({ source: "mic" as any });
    expect(result.current).toBe(0);
  });
});

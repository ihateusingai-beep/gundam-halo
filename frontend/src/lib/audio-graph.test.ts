/**
 * audio-graph.test.ts — Sprint 57 TtsAudioGraph lifecycle.
 *
 * 3 tests pinning: setTheme applies the preset; getPreset
 * returns the current preset; dispose closes the AudioContext.
 * Uses a minimal AudioContext mock since jsdom doesn't ship one.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TtsAudioGraph } from "./audio-graph";

function buildFakeAudioContext() {
  const filters: Array<{
    type: BiquadFilterType;
    frequency: { value: number; setValueAtTime: ReturnType<typeof vi.fn> };
    gain: { value: number; setValueAtTime: ReturnType<typeof vi.fn> };
    Q: { value: number; setValueAtTime: ReturnType<typeof vi.fn> };
    connect: ReturnType<typeof vi.fn>;
    disconnect: ReturnType<typeof vi.fn>;
  }> = [];
  const ctx = {
    state: "running" as AudioContextState,
    currentTime: 0,
    destination: { id: "destination" },
    createBiquadFilter: () => {
      const f = {
        type: "peaking" as BiquadFilterType,
        context: ctx,
        frequency: { value: 1000, setValueAtTime: vi.fn() },
        gain: { value: 0, setValueAtTime: vi.fn() },
        Q: { value: 1, setValueAtTime: vi.fn() },
        connect: vi.fn(),
        disconnect: vi.fn(),
      };
      filters.push(f);
      return f;
    },
    createMediaElementSource: vi.fn(),
    resume: vi.fn().mockResolvedValue(undefined),
    close: vi.fn().mockResolvedValue(undefined),
    _filters: filters,
  };
  return ctx;
}

describe("TtsAudioGraph", () => {
  let originalAudioContext: typeof AudioContext | undefined;

  beforeEach(() => {
    originalAudioContext = (window as unknown as { AudioContext?: typeof AudioContext })
      .AudioContext;
  });

  afterEach(() => {
    (window as unknown as { AudioContext?: typeof AudioContext }).AudioContext =
      originalAudioContext;
  });

  it("returns null when AudioContext is unavailable", () => {
    (window as unknown as { AudioContext?: typeof AudioContext }).AudioContext = undefined;
    const graph = new TtsAudioGraph();
    expect(graph.getContext()).toBeNull();
  });

  it("lazy-creates the AudioContext + 5 filters on first getContext", () => {
    const fake = buildFakeAudioContext();
    (window as unknown as { AudioContext: unknown }).AudioContext = function FakeAudioContext() {
      return fake;
    };
    const graph = new TtsAudioGraph();
    const ctx = graph.getContext();
    expect(ctx).toBe(fake);
    expect(graph.getFilters().length).toBe(5);
  });

  it("setTheme updates the current preset", () => {
    const fake = buildFakeAudioContext();
    (window as unknown as { AudioContext: unknown }).AudioContext = function FakeAudioContext() {
      return fake;
    };
    const graph = new TtsAudioGraph();
    void graph.getContext(); // force init
    graph.setTheme("gundam-ntd");
    expect(graph.getPreset().name).toBe("NT-D Sharp");
    graph.setTheme(null);
    expect(graph.getPreset().name).toBe("Flat");
  });

  it("dispose closes the AudioContext and clears filters", async () => {
    const fake = buildFakeAudioContext();
    (window as unknown as { AudioContext: unknown }).AudioContext = function FakeAudioContext() {
      return fake;
    };
    const graph = new TtsAudioGraph();
    void graph.getContext();
    expect(graph.getFilters().length).toBe(5);
    await graph.dispose();
    expect(graph.getFilters().length).toBe(0);
    expect(fake.close).toHaveBeenCalledOnce();
  });
});

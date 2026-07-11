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

  // Sprint 64 A-A4: per-band gain control
  it("setBandGain(0, 5) calls setValueAtTime(5) on the first filter", () => {
    const fake = buildFakeAudioContext();
    (window as unknown as { AudioContext: unknown }).AudioContext = function FakeAudioContext() {
      return fake;
    };
    const graph = new TtsAudioGraph();
    void graph.getContext();
    graph.setTheme("gundam-ntd"); // initialise the 5 filters
    const filters = graph.getFilters();
    const band0 = filters[0];
    if (!band0) throw new Error("band 0 filter not initialised");
    const band0Mock = band0.gain.setValueAtTime as unknown as {
      mock: { calls: unknown[][] };
    };
    const band1 = filters[1];
    if (!band1) throw new Error("band 1 filter not initialised");
    const band1Mock = band1.gain.setValueAtTime as unknown as {
      mock: { calls: unknown[][] };
    };
    const before = band1Mock.mock.calls.length;
    graph.setBandGain(0, 5);
    // setValueAtTime was called on band 0 (with the new gain)
    expect(band0Mock.mock.calls.length).toBeGreaterThan(0);
    // ...but NOT on band 1 (other bands unchanged)
    expect(band1Mock.mock.calls.length).toBe(before);
  });

  it("setBandGain before graph init is a no-op", () => {
    const fake = buildFakeAudioContext();
    (window as unknown as { AudioContext: unknown }).AudioContext = function FakeAudioContext() {
      return fake;
    };
    const graph = new TtsAudioGraph();
    // No getContext() / setTheme call — filters[] is still empty
    graph.setBandGain(0, 5);
    expect(graph.getFilters().length).toBe(0);
  });

  it("setBandGain(99, 5) is out-of-bounds (no-op + warn)", () => {
    const fake = buildFakeAudioContext();
    (window as unknown as { AudioContext: unknown }).AudioContext = function FakeAudioContext() {
      return fake;
    };
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
    const graph = new TtsAudioGraph();
    void graph.getContext();
    graph.setTheme("gundam-ntd");
    graph.setBandGain(99 as never, 5);
    expect(warnSpy).toHaveBeenCalledWith(
      expect.stringContaining("out of range"),
    );
    warnSpy.mockRestore();
  });

  it("setBandGain updates getPreset() (UI sees the new value)", () => {
    const fake = buildFakeAudioContext();
    (window as unknown as { AudioContext: unknown }).AudioContext = function FakeAudioContext() {
      return fake;
    };
    const graph = new TtsAudioGraph();
    void graph.getContext();
    graph.setTheme("gundam-ntd");
    const before = graph.getPreset().bands[0]?.gain ?? 0;
    graph.setBandGain(0, before + 3);
    expect(graph.getPreset().bands[0]?.gain).toBeCloseTo(before + 3);
  });
});

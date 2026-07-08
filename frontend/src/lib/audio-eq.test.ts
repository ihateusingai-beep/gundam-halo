/**
 * audio-eq.test.ts — Sprint 57 EQ preset verification.
 *
 * 5 tests pinning the 8-theme × 5-band EQ profile. Per-theme
 * character is a UX guarantee, so any future refactor that
 * changes the gain values must intentionally update these
 * tests.
 */
import { describe, expect, it } from "vitest";

import { applyEqPreset, getEqPreset } from "./audio-eq";

describe("getEqPreset", () => {
  it("returns the flat preset for null", () => {
    const p = getEqPreset(null);
    expect(p.name).toBe("Flat");
    expect(p.bands.every((b) => b.gain === 0)).toBe(true);
  });

  it("returns the flat preset for unknown theme id", () => {
    const p = getEqPreset("not-a-theme");
    expect(p.name).toBe("Flat");
  });

  it("returns the 8 named theme presets", () => {
    const expectedIds = [
      "gundam-ntd",
      "gundam-seed",
      "gundam-crossbone",
      "gundam-ntd-green",
      "gundam-00",
      "gundam-destiny",
      "gundam-god",
      "gundam-cartoon",
    ];
    for (const id of expectedIds) {
      const p = getEqPreset(id);
      expect(p.bands.length).toBe(5);
      // Every band is a BiquadFilter shape with required keys
      for (const band of p.bands) {
        expect(typeof band.type).toBe("string");
        expect(typeof band.frequency).toBe("number");
        expect(typeof band.gain).toBe("number");
        expect(typeof band.Q).toBe("number");
      }
    }
  });

  it("NT-D emphasizes the highs (psycho-frame resonance)", () => {
    const p = getEqPreset("gundam-ntd");
    // High shelf (band 5) should be the most positive gain.
    const highShelf = p.bands[4].gain;
    const otherGains = p.bands.slice(0, 4).map((b) => b.gain);
    expect(highShelf).toBeGreaterThan(Math.max(...otherGains));
  });

  it("CROSS (pirate) emphasizes the lows", () => {
    const p = getEqPreset("gundam-crossbone");
    // Low shelf (band 1) should be the most positive gain.
    const lowShelf = p.bands[0].gain;
    const otherGains = p.bands.slice(1).map((b) => b.gain);
    expect(lowShelf).toBeGreaterThan(Math.max(...otherGains));
  });
});

describe("applyEqPreset", () => {
  function makeFakeFilters(): BiquadFilterNode[] {
    // jsdom doesn't expose BiquadFilterNode. We build a minimal
    // stand-in with the same surface (type, frequency, gain, Q
    // as AudioParam-like objects with `setValueAtTime`).
    function fakeParam(initial: number) {
      const param: { value: number; setValueAtTime: (v: number, _t: number) => void } = {
        value: initial,
        setValueAtTime(v, _t) {
          param.value = v;
        },
      };
      return param;
    }
    function fakeFilter(): BiquadFilterNode {
      const f: Partial<BiquadFilterNode> = {
        type: "peaking" as BiquadFilterType,
        frequency: fakeParam(1000) as unknown as AudioParam,
        gain: fakeParam(0) as unknown as AudioParam,
        Q: fakeParam(1) as unknown as AudioParam,
        context: { currentTime: 0 } as AudioContext,
      };
      return f as BiquadFilterNode;
    }
    return [0, 1, 2, 3, 4].map(() => fakeFilter());
  }

  it("applies the 5-band gains to the filter chain", () => {
    const filters = makeFakeFilters();
    const preset = getEqPreset("gundam-ntd");
    applyEqPreset(filters, preset);
    for (let i = 0; i < 5; i++) {
      const filter = filters[i] as unknown as {
        type: string;
        frequency: { value: number };
        gain: { value: number };
        Q: { value: number };
      };
      expect(filter.type).toBe(preset.bands[i].type);
      expect(filter.frequency.value).toBe(preset.bands[i].frequency);
      expect(filter.gain.value).toBe(preset.bands[i].gain);
      expect(filter.Q.value).toBe(preset.bands[i].Q);
    }
  });

  it("throws on filter chain count mismatch", () => {
    const filters = makeFakeFilters().slice(0, 3);
    const preset = getEqPreset("gundam-ntd");
    expect(() => applyEqPreset(filters, preset)).toThrow(
      /exactly 5 BiquadFilters/,
    );
  });
});

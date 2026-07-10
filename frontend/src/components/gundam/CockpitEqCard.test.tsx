/**
 * CockpitEqCard.test.tsx — Sprint 62 A-A3 tests.
 *
 * 4 tests pinning the A/B compare affordance: button renders,
 * chip click starts timer, Pin button promotes to permanent
 * override, ✕ cancels.
 */
import { afterEach, describe, expect, it, vi, beforeEach } from "vitest";
import { cleanup, fireEvent, render, screen, act } from "@testing-library/react";

import { CockpitEqCard } from "./CockpitEqCard";

// Mock the TtsAudioGraph so the visualizer doesn't try to use
// a real AudioContext in jsdom (which would throw).
vi.mock("@/lib/audio-graph", () => ({
  TtsAudioGraph: class {
    currentPreset = FLAT_PRESET;
    setTheme() {}
    setPreset(p: typeof FLAT_PRESET) {
      this.currentPreset = p;
    }
    getPreset() {
      return this.currentPreset;
    }
    attachMediaElement() {}
    resume() {}
    dispose() {}
  },
}));

// Stub the useThemeStore so we can control the active theme
// (the CockpitEqCard hides the "current" theme from the
// compare list).
vi.mock("@/stores/theme", () => ({
  useThemeStore: (selector: (s: { theme: string }) => unknown) =>
    selector({ theme: "gundam-ntd" }),
}));

const FLAT_PRESET = {
  name: "Flat",
  description: "No equalization",
  bands: [
    { type: "lowshelf", frequency: 100, gain: 0, Q: 0.7 },
    { type: "peaking", frequency: 250, gain: 0, Q: 1 },
    { type: "peaking", frequency: 1000, gain: 0, Q: 1 },
    { type: "peaking", frequency: 2500, gain: 0, Q: 1 },
    { type: "highshelf", frequency: 6000, gain: 0, Q: 0.7 },
  ],
};

// Stub useEqStore so the test starts with no override.
let mockOverride: unknown = null;
const mockSetPreset = vi.fn();
const mockReset = vi.fn();
vi.mock("@/stores/eq", () => ({
  useEqStore: (selector: (s: { override: unknown; setPreset: typeof mockSetPreset; resetToThemePreset: typeof mockReset }) => unknown) =>
    selector({
      override: mockOverride,
      setPreset: mockSetPreset,
      resetToThemePreset: mockReset,
    }),
}));

describe("CockpitEqCard A/B compare (Sprint 62 A-A3)", () => {
  beforeEach(() => {
    mockOverride = null;
    mockSetPreset.mockClear();
    mockReset.mockClear();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    cleanup();
  });

  it("renders the Compare row with one chip per non-current theme", () => {
    render(<CockpitEqCard />);
    expect(screen.getByTestId("eq-compare-row")).toBeTruthy();
    // The current theme is "gundam-ntd" — should NOT show.
    expect(screen.queryByTestId("eq-compare-gundam-ntd")).toBeNull();
    // Other 7 themes should show.
    expect(screen.getByTestId("eq-compare-gundam-seed")).toBeTruthy();
    expect(screen.getByTestId("eq-compare-gundam-crossbone")).toBeTruthy();
    expect(screen.getByTestId("eq-compare-gundam-cartoon")).toBeTruthy();
  });

  it("clicking a theme chip enters A/B state with a countdown", () => {
    render(<CockpitEqCard />);
    fireEvent.click(screen.getByTestId("eq-compare-gundam-seed"));
    expect(screen.getByTestId("eq-compare-countdown")).toBeTruthy();
    expect(screen.getByTestId("eq-compare-countdown").textContent).toMatch(
      /gundam-seed.*10s/,
    );
  });

  it("Pin promotes the compare to a permanent override", () => {
    render(<CockpitEqCard />);
    fireEvent.click(screen.getByTestId("eq-compare-gundam-seed"));
    fireEvent.click(screen.getByTestId("eq-compare-pin"));
    expect(mockSetPreset).toHaveBeenCalledTimes(1);
    // The compare should be cleared.
    expect(screen.queryByTestId("eq-compare-countdown")).toBeNull();
  });

  it("✕ cancels the compare without modifying the override", () => {
    render(<CockpitEqCard />);
    fireEvent.click(screen.getByTestId("eq-compare-gundam-seed"));
    fireEvent.click(screen.getByTestId("eq-compare-cancel"));
    expect(mockSetPreset).not.toHaveBeenCalled();
    expect(screen.queryByTestId("eq-compare-countdown")).toBeNull();
  });

  it("shows 'Reset override' button when an override is active", () => {
    mockOverride = {
      name: "SEED Prismatic",
      bands: [
        { type: "lowshelf", frequency: 100, gain: -1, Q: 0.7 },
        { type: "peaking", frequency: 250, gain: 0, Q: 1 },
        { type: "peaking", frequency: 1000, gain: 1, Q: 1 },
        { type: "peaking", frequency: 2500, gain: 3, Q: 1 },
        { type: "highshelf", frequency: 6000, gain: 2, Q: 0.7 },
      ],
    };
    render(<CockpitEqCard />);
    expect(screen.getByTestId("eq-compare-reset-override")).toBeTruthy();
    fireEvent.click(screen.getByTestId("eq-compare-reset-override"));
    expect(mockReset).toHaveBeenCalledTimes(1);
  });
});
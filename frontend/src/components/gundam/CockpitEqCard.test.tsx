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
    setBandGain(_band: number, _gainDb: number) {
      // No-op in tests (the real implementation writes to
      // BiquadFilterNode.gain, which doesn't exist in jsdom).
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

  // Sprint 63 A-A4: EQ editor (UI skeleton). The 3 tests
  // pin the edit-mode affordance without touching audio
  // graph plumbing (Sprint 64's job).
  it("Edit button toggles the per-band slider grid", () => {
    render(<CockpitEqCard />);
    expect(screen.queryByTestId("eq-editor-grid")).toBeNull();
    fireEvent.click(screen.getByTestId("eq-edit-toggle"));
    expect(screen.getByTestId("eq-editor-grid")).toBeTruthy();
    // 5 sliders, one per band.
    expect(screen.getByTestId("eq-editor-band-0")).toBeTruthy();
    expect(screen.getByTestId("eq-editor-band-4")).toBeTruthy();
  });

  it("slider change updates the readout", () => {
    render(<CockpitEqCard />);
    fireEvent.click(screen.getByTestId("eq-edit-toggle"));
    const band0 = screen.getByTestId("eq-editor-band-0");
    fireEvent.change(band0, { target: { value: "5" } });
    expect(
      screen.getByTestId("eq-editor-band-0-readout").textContent,
    ).toMatch(/\+5\.0 dB/);
  });

  it("readout formats negative values with a minus sign", () => {
    render(<CockpitEqCard />);
    fireEvent.click(screen.getByTestId("eq-edit-toggle"));
    const band4 = screen.getByTestId("eq-editor-band-4");
    fireEvent.change(band4, { target: { value: "-3" } });
    expect(
      screen.getByTestId("eq-editor-band-4-readout").textContent,
    ).toMatch(/−3\.0 dB|-3\.0 dB/);
  });

  // Sprint 64 A-A4 (audio): Apply + Reset buttons
  it("Apply button promotes per-band edits to a permanent override", () => {
    render(<CockpitEqCard />);
    fireEvent.click(screen.getByTestId("eq-edit-toggle"));
    // Edit band 0
    fireEvent.change(screen.getByTestId("eq-editor-band-0"), {
      target: { value: "6" },
    });
    // Apply
    fireEvent.click(screen.getByTestId("eq-editor-apply"));
    expect(mockSetPreset).toHaveBeenCalledTimes(1);
    const arg = mockSetPreset.mock.calls[0]?.[0] as { name: string; bands: { gain: number }[] };
    expect(arg.name).toContain("(custom)");
    expect(arg.bands[0]?.gain).toBe(6);
  });

  it("Reset button restores the preset's default gains", () => {
    render(<CockpitEqCard />);
    fireEvent.click(screen.getByTestId("eq-edit-toggle"));
    // Edit band 0 to something wild
    fireEvent.change(screen.getByTestId("eq-editor-band-0"), {
      target: { value: "10" },
    });
    expect(screen.getByTestId("eq-editor-band-0-readout").textContent).toMatch(
      /\+10\.0 dB/,
    );
    // Reset
    fireEvent.click(screen.getByTestId("eq-editor-reset"));
    // Edit mode closed (the readout + actions are gone)
    expect(screen.queryByTestId("eq-editor-actions")).toBeNull();
    expect(screen.queryByTestId("eq-editor-band-0-readout")).toBeNull();
    // The Edit button is back, allowing the user to re-open
    expect(screen.getByTestId("eq-edit-toggle")).toBeTruthy();
  });
});
/**
 * stores/eq.test.ts — Sprint 67 C-A1.
 *
 * Tests the localStorage persistence of the EQ override:
 *   1. setPreset writes to localStorage
 *   2. resetToThemePreset removes the localStorage key
 *   3. An invalid localStorage value is silently ignored
 *      on mount + a warning is logged
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { EQ_OVERRIDE_LS_KEY } from "./eq.schema";
import type { EqPreset } from "@/lib/audio-eq";

// Re-import the store fresh for each test so the
// `readPersistedOverride` initializer sees the new
// localStorage value.
async function freshStore() {
  vi.resetModules();
  return await import("./eq");
}

const CUSTOM_PRESET: EqPreset = {
  name: "Custom test preset",
  description: "for the persistence test",
  bands: [
    { type: "lowshelf", frequency: 100, gain: 3, Q: 0.7 },
    { type: "peaking", frequency: 250, gain: 1, Q: 1.0 },
    { type: "peaking", frequency: 1000, gain: -1, Q: 1.0 },
    { type: "peaking", frequency: 2500, gain: 2, Q: 1.0 },
    { type: "highshelf", frequency: 6000, gain: -3, Q: 0.7 },
  ],
};

describe("useEqStore persistence (Sprint 67 C-A1)", () => {
  beforeEach(() => {
    // Clean the key between tests.
    if (typeof window !== "undefined") {
      window.localStorage.removeItem(EQ_OVERRIDE_LS_KEY);
    }
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("setPreset writes the preset to localStorage", async () => {
    const { useEqStore } = await freshStore();
    useEqStore.getState().setPreset(CUSTOM_PRESET);
    const raw = window.localStorage.getItem(EQ_OVERRIDE_LS_KEY);
    expect(raw).toBeTruthy();
    const parsed = JSON.parse(raw ?? "{}");
    expect(parsed.name).toBe("Custom test preset");
  });

  it("resetToThemePreset removes the localStorage key", async () => {
    const { useEqStore } = await freshStore();
    useEqStore.getState().setPreset(CUSTOM_PRESET);
    useEqStore.getState().resetToThemePreset();
    const raw = window.localStorage.getItem(EQ_OVERRIDE_LS_KEY);
    expect(raw).toBeNull();
  });

  it("an invalid localStorage value is ignored on mount + warning logged", async () => {
    // Pre-seed an invalid value (missing the `bands` field).
    window.localStorage.setItem(
      EQ_OVERRIDE_LS_KEY,
      JSON.stringify({ name: "broken" }),
    );
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
    const { useEqStore } = await freshStore();
    expect(useEqStore.getState().override).toBeNull();
    // The schema-parse failure logs a warning.
    expect(warnSpy).toHaveBeenCalled();
    warnSpy.mockRestore();
  });
});

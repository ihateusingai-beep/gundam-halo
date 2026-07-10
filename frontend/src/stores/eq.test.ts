/**
 * eq.test.ts — Sprint 62 A-A2 tests.
 *
 * 7 tests pinning the per-USER EQ store contract. Covers the
 * default state, set/reset semantics, the theme-vs-override
 * precedence, and the non-React `getActiveEqPreset` helper.
 */
import { beforeEach, describe, expect, it } from "vitest";

import { getEqPreset, type EqPreset } from "@/lib/audio-eq";
import { getActiveEqPreset, useEqStore } from "./eq";

const SEED: EqPreset = getEqPreset("gundam-seed");
const NTD: EqPreset = getEqPreset("gundam-ntd");

describe("useEqStore (Sprint 62 A-A2)", () => {
  beforeEach(() => {
    // Reset store between tests.
    useEqStore.setState({ override: null });
  });

  it("default state: override is null", () => {
    expect(useEqStore.getState().override).toBeNull();
  });

  it("getActivePreset(theme) returns the theme's preset when no override", () => {
    expect(useEqStore.getState().getActivePreset("gundam-ntd").name).toBe(
      NTD.name,
    );
    expect(useEqStore.getState().getActivePreset("gundam-seed").name).toBe(
      SEED.name,
    );
  });

  it("getActivePreset(null) returns the Flat fallback", () => {
    const fallback = useEqStore.getState().getActivePreset(null);
    expect(fallback.name).toBe("Flat");
  });

  it("setPreset(p) stores the override", () => {
    useEqStore.getState().setPreset(SEED);
    expect(useEqStore.getState().override).toEqual(SEED);
  });

  it("setPreset(SEED) overrides NT-D's preset", () => {
    useEqStore.getState().setPreset(SEED);
    const active = useEqStore.getState().getActivePreset("gundam-ntd");
    expect(active.name).toBe(SEED.name);
  });

  it("resetToThemePreset() clears the override", () => {
    useEqStore.getState().setPreset(SEED);
    useEqStore.getState().resetToThemePreset();
    expect(useEqStore.getState().override).toBeNull();
    expect(useEqStore.getState().getActivePreset("gundam-ntd").name).toBe(
      NTD.name,
    );
  });

  it("setPreset(null) is equivalent to resetToThemePreset()", () => {
    useEqStore.getState().setPreset(SEED);
    useEqStore.getState().setPreset(null);
    expect(useEqStore.getState().override).toBeNull();
  });

  it("non-React helper getActiveEqPreset matches store.getActivePreset", () => {
    useEqStore.getState().setPreset(SEED);
    expect(getActiveEqPreset("gundam-ntd").name).toBe(
      useEqStore.getState().getActivePreset("gundam-ntd").name,
    );
  });
});
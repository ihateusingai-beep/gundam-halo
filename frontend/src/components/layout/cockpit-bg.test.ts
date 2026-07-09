/**
 * cockpit-bg.test.ts — Sprint 58 per-theme cockpit BG wiring.
 *
 * The CockpitLayout component reads (theme, background) from
 * `useThemeStore` and computes the asset URL via
 * `resolveBgAsset(slug, theme)`. We don't render the full
 * CockpitLayout (20+ child components + Tauri-only hooks) —
 * instead we test the contract by stubbing the store and
 * asserting the URL.
 *
 * Pre-Sprint 58 bug: the CSS rule on `.gundam-cockpit-bg` had
 * `background-image: none` as the safety net and the inline
 * style was never set, so the cockpit wallpaper NEVER showed
 * regardless of theme or bg slug. Sprint 58 Phase 4 adds the
 * inline style so the wallpaper renders correctly.
 *
 * 4 tests pin:
 *   1. NT-D + core-01 → unicorn-core-01 (legacy baseline)
 *   2. SEED + core-01 → seed-core-01 (per-theme hero)
 *   3. HALO + core-01 → halo-core-01 (per-theme hero)
 *   4. ANY + none     → null (no image, pure hex grid)
 */
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { resolveBgAsset } from "@/routes/settings/constants";

describe("cockpit-bg asset URL (Sprint 58 Phase 4)", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  afterEach(() => {
    window.localStorage.clear();
  });

  it("NT-D + core-01 → unicorn-core-01 (legacy baseline)", () => {
    expect(resolveBgAsset("core-01", "gundam-ntd")).toBe(
      "/gundam-assets/backgrounds/bg-unicorn-core-01.jpg",
    );
  });

  it("SEED + core-01 → seed-core-01 (per-theme hero)", () => {
    expect(resolveBgAsset("core-01", "gundam-seed")).toBe(
      "/gundam-assets/backgrounds/bg-seed-core-01.jpg",
    );
  });

  it("HALO + core-01 → halo-core-01 (per-theme hero)", () => {
    expect(resolveBgAsset("core-01", "gundam-halo")).toBe(
      "/gundam-assets/backgrounds/bg-halo-core-01.jpg",
    );
  });

  it("ANY theme + 'none' → null (no image, pure hex grid)", () => {
    expect(resolveBgAsset("none", "gundam-ntd")).toBeNull();
    expect(resolveBgAsset("none", "gundam-seed")).toBeNull();
    expect(resolveBgAsset("none", "gundam-halo")).toBeNull();
    expect(resolveBgAsset("none", null)).toBeNull();
  });
});
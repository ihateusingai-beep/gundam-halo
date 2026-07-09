/**
 * settings-constants-bg.test.ts — Sprint 58 per-theme BG resolver.
 *
 * 3 tests pinning the bg-<theme>-<slug>.jpg path builder and
 * the default-bg fallback. The asset filenames are user-visible
 * (the wizard thumbnail renders them); a wrong path would show
 * a broken image icon.
 *
 * Imports from the source-of-truth (`lib/theme-bg-constants`)
 * rather than the re-export (`./constants`) so this test pins
 * the actual implementation, not the re-export wiring.
 */
import { describe, expect, it } from "vitest";

import { defaultBgForTheme, resolveBgAsset } from "@/lib/theme-bg-constants";

describe("resolveBgAsset (Sprint 58)", () => {
  it("returns null for the 'none' background (pure hex grid)", () => {
    expect(resolveBgAsset("none", "gundam-ntd")).toBeNull();
    expect(resolveBgAsset("none", "gundam-seed")).toBeNull();
  });

  it("builds the per-theme asset path: bg-<theme>-<slug>.jpg", () => {
    expect(resolveBgAsset("core-01", "gundam-seed")).toBe(
      "/gundam-assets/backgrounds/bg-seed-core-01.jpg",
    );
    expect(resolveBgAsset("core-01", "gundam-destiny")).toBe(
      "/gundam-assets/backgrounds/bg-destiny-core-01.jpg",
    );
    // NT-D keeps the historical "unicorn" slug — its 4 legacy
    // variants (core-01..04) live at /bg-unicorn-core-XX.jpg.
    expect(resolveBgAsset("core-01", "gundam-ntd")).toBe(
      "/gundam-assets/backgrounds/bg-unicorn-core-01.jpg",
    );
  });

  it("falls back to unicorn-core-XX for unknown themes", () => {
    expect(resolveBgAsset("core-01", null)).toBe(
      "/gundam-assets/backgrounds/bg-unicorn-core-01.jpg",
    );
    expect(resolveBgAsset("core-02", "gundam-unknown-future")).toBe(
      "/gundam-assets/backgrounds/bg-unicorn-core-02.jpg",
    );
  });
});
describe("defaultBgForTheme (Sprint 58)", () => {
  it("returns 'core-01' for every known theme", () => {
    const known = [
      // gundam-ntd intentionally absent — it's the fallback path
      // (returns core-01 implicitly, see the next test)
      "gundam-seed",
      "gundam-crossbone",
      "gundam-ntd-green",
      "gundam-00",
      "gundam-destiny",
      "gundam-god",
      "gundam-cartoon",
      "gundam-halo",
    ];
    for (const id of known) {
      expect(defaultBgForTheme(id), `theme=${id}`).toBe("core-01");
    }
  });

  it("falls back to 'core-01' for NT-D, unknown, and null themes", () => {
    // NT-D is the baseline — its default is the historical Unicorn
    // core-01 wallpaper. The mapping is implicit (no THEME_DEFAULT_BG
    // entry for "gundam-ntd" → fallthrough returns core-01).
    expect(defaultBgForTheme("gundam-ntd")).toBe("core-01");
    expect(defaultBgForTheme(null)).toBe("core-01");
    expect(defaultBgForTheme(undefined)).toBe("core-01");
    expect(defaultBgForTheme("gundam-future-9")).toBe("core-01");
  });
});

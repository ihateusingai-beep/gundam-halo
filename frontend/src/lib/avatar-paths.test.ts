/**
 * avatar-paths.test.ts — Sprint 58 per-theme avatar URL builder.
 *
 * 3 tests pinning the URL builder contract. A wrong path shows
 * up as a broken-image icon in the cockpit; a wrong emotion
 * silently falls through to idle.
 */
import { describe, expect, it } from "vitest";

import {
  avatarDirForTheme,
  buildAvatarImageMap,
} from "./avatar-paths";

describe("avatarDirForTheme (Sprint 58)", () => {
  it("maps each theme to its emotions-<slug>/ directory", () => {
    // NT-D uses the BARE "emotions/" directory (the legacy NT-D
    // Unicorn baseline set, which we kept on disk). All other
    // known themes use the per-theme "emotions-<slug>/" directory.
    expect(avatarDirForTheme("gundam-ntd")).toBe("emotions");
    expect(avatarDirForTheme("gundam-seed")).toBe("emotions-seed");
    expect(avatarDirForTheme("gundam-ntd-green")).toBe("emotions-ntd-green");
    expect(avatarDirForTheme("gundam-00")).toBe("emotions-00");
    expect(avatarDirForTheme("gundam-destiny")).toBe("emotions-destiny");
    expect(avatarDirForTheme("gundam-god")).toBe("emotions-god");
    expect(avatarDirForTheme("gundam-crossbone")).toBe("emotions-crossbone");
  });

  it("falls back to 'emotions' (NT-D baseline) for unknown / null themes", () => {
    expect(avatarDirForTheme(null)).toBe("emotions");
    expect(avatarDirForTheme(undefined)).toBe("emotions");
    expect(avatarDirForTheme("gundam-future-99")).toBe("emotions");
  });
});

describe("buildAvatarImageMap (Sprint 58)", () => {
  it("emits 9 emotion URLs for the given theme", () => {
    const map = buildAvatarImageMap("gundam-seed");
    expect(Object.keys(map)).toHaveLength(9);
    expect(map.idle).toBe("/avatars/emotions-seed/idle.png");
    expect(map.listening).toBe("/avatars/emotions-seed/listening.png");
    expect(map.damage).toBe("/avatars/emotions-seed/damage.png");
    expect(map.confused).toBe("/avatars/emotions-seed/confused.png");
  });

  it("falls back to NT-D 'emotions/' for unknown themes", () => {
    const map = buildAvatarImageMap("gundam-future-99");
    expect(map.idle).toBe("/avatars/emotions/idle.png");
    expect(map.speaking).toBe("/avatars/emotions/speaking.png");
  });
});
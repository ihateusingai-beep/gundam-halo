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

describe("buildAvatarImageMap (Sprint 58 + 59)", () => {
  it("emits 9 emotion URLs for the given theme", () => {
    const map = buildAvatarImageMap("gundam-seed");
    expect(Object.keys(map)).toHaveLength(9);
    // Sprint 59: per-(dir, emotion) extension. Seed is all jpg.
    expect(map.idle).toBe("/avatars/emotions-seed/idle.jpg");
    expect(map.listening).toBe("/avatars/emotions-seed/listening.jpg");
    expect(map.damage).toBe("/avatars/emotions-seed/damage.jpg");
    expect(map.confused).toBe("/avatars/emotions-seed/confused.jpg");
  });

  it("falls back to NT-D 'emotions/' (PNG) for unknown themes", () => {
    const map = buildAvatarImageMap("gundam-future-99");
    expect(map.idle).toBe("/avatars/emotions/idle.png");
    expect(map.speaking).toBe("/avatars/emotions/speaking.png");
  });

  it("emits valid URLs for every per-theme set (Sprint 59: full coverage)", () => {
    // Sprint 59 closed the P4 deferred item — every per-theme
    // directory has a full 9-emotion set now. URLs may be .jpg
    // or .png depending on matrix MCP's per-call format choice.
    const themes = [
      "gundam-seed",
      "gundam-ntd-green",
      "gundam-00",
      "gundam-destiny",
      "gundam-god",
      "gundam-crossbone",
      "gundam-halo",
      "gundam-cartoon",
    ];
    for (const t of themes) {
      const map = buildAvatarImageMap(t);
      for (const [emotion, url] of Object.entries(map)) {
        expect(url, `${t}.${emotion}`).toMatch(/\.(jpg|png)$/);
        expect(url, `${t}.${emotion}`).toContain(`/avatars/emotions-`);
      }
    }
  });

  it("emits .png URLs only for the NT-D baseline 'emotions/' dir", () => {
    const map = buildAvatarImageMap("gundam-ntd");
    expect(map.idle).toBe("/avatars/emotions/idle.png");
    expect(map.listening).toBe("/avatars/emotions/listening.png");
    expect(map.damage).toBe("/avatars/emotions/damage.png");
  });

  it("crossbone full set uses per-emotion extension table (Sprint 59)", () => {
    const map = buildAvatarImageMap("gundam-crossbone");
    // crossbone has mixed jpg/png — pin the truth.
    expect(map.idle).toBe("/avatars/emotions-crossbone/idle.jpg");
    expect(map.listening).toBe("/avatars/emotions-crossbone/listening.png");
    expect(map.thinking).toBe("/avatars/emotions-crossbone/thinking.jpg");
    expect(map.speaking).toBe("/avatars/emotions-crossbone/speaking.png");
    expect(map.damage).toBe("/avatars/emotions-crossbone/damage.png");
    expect(map.joy).toBe("/avatars/emotions-crossbone/joy.jpg");
    expect(map.sad).toBe("/avatars/emotions-crossbone/sad.jpg");
    expect(map.confused).toBe("/avatars/emotions-crossbone/confused.jpg");
    expect(map.warning).toBe("/avatars/emotions-crossbone/warning.jpg");
  });
});
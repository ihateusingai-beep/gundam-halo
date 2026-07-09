import { create } from "zustand";
import type { GundamTheme } from "@/types/api";
import { defaultBgForTheme } from "@/lib/theme-bg-constants";

export type CockpitBackground =
  | "none" // pure hex grid, no JPG
  | "core-01"
  | "core-02"
  | "core-03"
  | "core-04";

const ACCENT_STORAGE_KEY = "gundam-halo-theme-accent";
const ACCENT_REGEX = /^#[0-9a-f]{6}$/i;

function readPersistedAccent(): string | null {
  try {
    const v = localStorage.getItem(ACCENT_STORAGE_KEY);
    return v && ACCENT_REGEX.test(v) ? v : null;
  } catch {
    return null;
  }
}

/**
 * Sprint 51 — apply a custom accent color to the document via a
 * CSS variable indirection (NOT inline `--accent`). The reason:
 * the spec calls for `[data-custom-accent]` selector to win over
 * `[data-theme="gundam-..."]` rules via CSS cascade order. Setting
 * `style="--accent: ..."` inline on <html> would always win the
 * cascade, defeating the hover-preview mechanism. We instead set
 * `style="--custom-accent: <hex>"` and let CSS do the cascade.
 */
function applyAccentToDom(hex: string | null) {
  if (hex) {
    document.documentElement.style.setProperty("--custom-accent", hex);
    document.documentElement.setAttribute("data-custom-accent", "");
  } else {
    document.documentElement.style.removeProperty("--custom-accent");
    document.documentElement.removeAttribute("data-custom-accent");
  }
}

interface ThemeState {
  theme: GundamTheme;
  setTheme: (t: GundamTheme) => void;

  /**
   * Sprint 50: live preview theme (not persisted). Set by the
   * ThemeHoverCard when the user hovers a swatch — the DOM
   * `data-theme` attribute is updated so the cockpit renders the
   * previewed theme immediately. When the hover ends, the
   * ThemeHoverCard calls `clearHoverTheme()` to revert to the
   * committed theme. The hover value is intentionally NOT saved
   * to localStorage — only explicit clicks commit.
   */
  hoverTheme: GundamTheme | null;
  setHoverTheme: (t: GundamTheme | null) => void;

  background: CockpitBackground;
  setBackground: (b: CockpitBackground) => void;

  /**
   * Sprint 51: optional custom accent color override. When set,
   * `[data-custom-accent]` is present on <html> and the CSS rule
   * `[data-custom-accent] { --accent: var(--custom-accent); }`
   * (declared LAST in gundam.css) wins the cascade over per-theme
   * `--accent` values. `null` = no override, use theme preset.
   */
  accent: string | null;
  setAccent: (hex: string | null) => void;
}

function applyBackground(b: CockpitBackground) {
  if (b === "none") {
    document.documentElement.removeAttribute("data-bg");
  } else {
    document.documentElement.setAttribute("data-bg", b);
  }
  localStorage.setItem("gundam-halo-bg", b);
}

// Apply persisted accent on store init so the first render shows the
// committed accent (matches existing pattern for theme + background at
// lines 41/70 — NOT Zustand onRehydrateStorage, which this store does
// not use).
const _initialAccent = readPersistedAccent();
if (_initialAccent) applyAccentToDom(_initialAccent);

export const useThemeStore = create<ThemeState>((set, get) => ({
  theme: (localStorage.getItem("gundam-halo-theme") as GundamTheme) || "gundam-ntd",
  setTheme: (t) => {
    if (t) {
      document.documentElement.setAttribute("data-theme", t);
      localStorage.setItem("gundam-halo-theme", t);
      // Sprint 58: auto-cascade the cockpit background to the
      // per-theme default. Each Gundam theme has its own hero
      // wallpaper (bg-<theme>-core-01.jpg); picking SEED no
      // longer leaves you looking at Unicorn NT-D background art.
      //
      // Only auto-switch when the current bg is "none" (user
      // never picked one) or "core-01" (the historical default
      // -- they get the new theme's variant). If the user picked
      // core-02 / 03 / 04 explicitly, preserve their choice.
      const currentBg = get().background;
      if (currentBg === "none" || currentBg === "core-01") {
        const newBg = defaultBgForTheme(t);
        applyBackground(newBg);
        set({ background: newBg });
      }
    } else {
      document.documentElement.removeAttribute("data-theme");
      localStorage.removeItem("gundam-halo-theme");
    }
    set({ theme: t });
  },

  hoverTheme: null,
  setHoverTheme: (t) => {
    if (t) {
      document.documentElement.setAttribute("data-theme", t);
    } else {
      // Revert to the committed theme (or remove if committed is null).
      const committed = get().theme;
      if (committed) {
        document.documentElement.setAttribute("data-theme", committed);
      } else {
        document.documentElement.removeAttribute("data-theme");
      }
    }
    set({ hoverTheme: t });
  },

  background:
    (localStorage.getItem("gundam-halo-bg") as CockpitBackground) || "none",
  setBackground: (b) => {
    applyBackground(b);
    set({ background: b });
  },

  accent: _initialAccent,
  setAccent: (hex) => {
    // Validate: must be #rrggbb (6-digit hex) or null. Invalid strings
    // (including 3-digit shorthand) are silently rejected per spec.
    const validated = hex && ACCENT_REGEX.test(hex) ? hex : null;
    if (hex !== null && validated === null) {
      // Invalid input — leave state unchanged.
      return;
    }
    applyAccentToDom(validated);
    try {
      if (validated) {
        localStorage.setItem(ACCENT_STORAGE_KEY, validated);
      } else {
        localStorage.removeItem(ACCENT_STORAGE_KEY);
      }
    } catch {
      /* localStorage unavailable — non-fatal */
    }
    set({ accent: validated });
  },
}));

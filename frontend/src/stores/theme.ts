import { create } from "zustand";
import type { GundamTheme } from "@/types/api";

export type CockpitBackground =
  | "none" // pure hex grid, no JPG
  | "core-01"
  | "core-02"
  | "core-03"
  | "core-04";

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
}

function applyBackground(b: CockpitBackground) {
  if (b === "none") {
    document.documentElement.removeAttribute("data-bg");
  } else {
    document.documentElement.setAttribute("data-bg", b);
  }
  localStorage.setItem("gundam-halo-bg", b);
}

export const useThemeStore = create<ThemeState>((set, get) => ({
  theme: (localStorage.getItem("gundam-halo-theme") as GundamTheme) || "gundam-ntd",
  setTheme: (t) => {
    if (t) {
      document.documentElement.setAttribute("data-theme", t);
      localStorage.setItem("gundam-halo-theme", t);
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
}));

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

export const useThemeStore = create<ThemeState>((set) => ({
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

  background:
    (localStorage.getItem("gundam-halo-bg") as CockpitBackground) || "none",
  setBackground: (b) => {
    applyBackground(b);
    set({ background: b });
  },
}));

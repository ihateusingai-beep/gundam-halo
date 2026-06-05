import { create } from "zustand";
import type { GundamTheme } from "@/types/api";

interface ThemeState {
  theme: GundamTheme;
  setTheme: (t: GundamTheme) => void;
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
}));

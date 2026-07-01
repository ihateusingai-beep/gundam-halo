/**
 * ThemeSwitcher — Sprint 50 refactor.
 *
 * Floating 56×56px button (bottom-right) that opens a
 * ThemeHoverCard on hover/focus. The card shows all 8 themes in
 * a 2×4 grid; mousing over a swatch previews the cockpit theme
 * live (DOM `data-theme` attribute, NOT persisted). Click
 * commits + closes the card. Escape closes without committing.
 *
 * Sprint 36: original design used a Radix DropdownMenu with
 * 8 radio items + a "OFF" toggle. The user feedback was that
 * "click to see name → click another to see name → click to commit"
 * is 3 clicks per theme; we want 1 hover to preview + 1 click to
 * commit = 1 click per theme.
 *
 * The committed theme's emoji + name are shown in the button
 * subtitle so the user always knows the current theme at a
 * glance (was previously the generic "MS MODE" string).
 */
import { useState } from "react";

import { useThemeStore } from "@/stores/theme";
import type { GundamTheme, ThemeInfo } from "@/types/api";
import { cn } from "@/lib/utils";

import { ThemeHoverCard } from "./ThemeHoverCard";

export const THEMES: ThemeInfo[] = [
  { id: "gundam-ntd", name: "NT-D", emoji: "🦄", description: "Unicorn psychoframe" },
  { id: "gundam-seed", name: "SEED", emoji: "⚡", description: "Freedom prismatic" },
  { id: "gundam-crossbone", name: "CROSS", emoji: "💀", description: "X-1 skull" },
  { id: "gundam-ntd-green", name: "GREEN", emoji: "🌿", description: "Green Frame" },
  { id: "gundam-00", name: "00", emoji: "🌐", description: "Qubit Trans-Am" },
  { id: "gundam-destiny", name: "DESTINY", emoji: "⚔", description: "Beam blade" },
  { id: "gundam-god", name: "GOD", emoji: "🔥", description: "Flame of God" },
  { id: "gundam-cartoon", name: "KAWAII", emoji: "✨", description: "Cartoon chibi" },
];

/** Floating theme picker (always visible, bottom-right). */
export function ThemeSwitcher() {
  const theme = useThemeStore((s) => s.theme);
  const [hoverOpen, setHoverOpen] = useState(false);
  const committedInfo = THEMES.find((t) => t.id === theme);

  return (
    <div
      style={{
        position: "fixed",
        bottom: 24,
        right: 24,
        zIndex: 9999,
      }}
      onMouseEnter={() => setHoverOpen(true)}
      onMouseLeave={() => setHoverOpen(false)}
      onFocus={() => setHoverOpen(true)}
      onBlur={(e) => {
        // Close when focus leaves the entire switcher + card.
        if (!e.currentTarget.contains(e.relatedTarget as Node)) {
          setHoverOpen(false);
        }
      }}
    >
      <button
        type="button"
        data-testid="theme-switcher-button"
        aria-label="Open Gundam theme hover preview"
        aria-haspopup="dialog"
        aria-expanded={hoverOpen}
        className={cn(
          "w-14 h-14 rounded-full border-[3px] cursor-pointer text-2xl",
          "transition-shadow hover:shadow-[0_0_16px_var(--accent)]",
          "border-white bg-gradient-to-br from-pink-400 via-cyan-400 to-yellow-400",
        )}
      >
        <span aria-hidden="true">{committedInfo?.emoji ?? "🎮"}</span>
        <span
          data-testid="theme-switcher-subtitle"
          className="block text-[9px] mt-0.5 font-mono uppercase tracking-wider text-black/80"
        >
          {committedInfo?.name ?? "OFF"}
        </span>
      </button>
      <ThemeHoverCard open={hoverOpen} onClose={() => setHoverOpen(false)} />
    </div>
  );
}
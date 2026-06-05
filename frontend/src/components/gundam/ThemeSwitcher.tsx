import { useState } from "react";
import { useThemeStore } from "@/stores/theme";
import type { GundamTheme, ThemeInfo } from "@/types/api";
import { cn } from "@/lib/utils";

const THEMES: ThemeInfo[] = [
  { id: "gundam-ntd", name: "NT-D", emoji: "🦄", description: "Unicorn psychoframe" },
  { id: "gundam-seed", name: "SEED", emoji: "⚡", description: "Freedom prismatic" },
  { id: "gundam-crossbone", name: "CROSS", emoji: "💀", description: "X-1 skull" },
  { id: "gundam-ntd-green", name: "GREEN", emoji: "🌿", description: "Green Frame" },
  { id: "gundam-00", name: "00", emoji: "🌐", description: "Qubit Trans-Am" },
  { id: "gundam-destiny", name: "DESTINY", emoji: "⚔", description: "Beam blade" },
  { id: "gundam-god", name: "GOD", emoji: "🔥", description: "Flame of God" },
  { id: "gundam-cartoon", name: "KAWAII", emoji: "✨", description: "Cartoon chibi" },
];

/** Floating 8-mode theme switcher (always visible, bottom-right). */
export function ThemeSwitcher() {
  const { theme, setTheme } = useThemeStore();
  const [open, setOpen] = useState(false);

  return (
    <div
      style={{
        position: "fixed",
        bottom: 24,
        right: 24,
        zIndex: 9999,
        display: "flex",
        flexDirection: "column",
        alignItems: "flex-end",
        gap: 8,
      }}
    >
      {open && (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {THEMES.map((t) => (
            <button
              key={t.id}
              onClick={() => {
                setTheme(t.id);
                setOpen(false);
              }}
              className={cn(
                "w-24 h-9 rounded-full border-2 cursor-pointer text-xs",
                "font-[Rajdhani] uppercase tracking-wider",
                "transition-all hover:scale-105",
                theme === t.id && "ring-2 ring-[var(--accent)]",
              )}
              style={{
                borderColor: "var(--accent)",
                background: "var(--bg-card)",
                color: "var(--accent)",
              }}
              title={t.description}
            >
              {t.emoji} {t.name}
            </button>
          ))}
          <button
            onClick={() => {
              setTheme(null as unknown as GundamTheme);
              setOpen(false);
            }}
            className="w-24 h-9 rounded-full border-2 border-gray-500 bg-gray-800 text-gray-400 text-xs cursor-pointer font-[Rajdhani]"
          >
            ✖ OFF
          </button>
        </div>
      )}
      <button
        onClick={() => setOpen(!open)}
        className="w-[72px] h-[72px] rounded-full border-[3px] border-white cursor-pointer text-2xl"
        style={{
          background: "linear-gradient(135deg, #FF69B4, #00D4FF, #FFD700)",
        }}
        aria-label="Toggle Gundam theme switcher"
      >
        🎮
        <span style={{ display: "block", fontSize: 10, marginTop: 2 }}>
          MS MODE
        </span>
      </button>
    </div>
  );
}

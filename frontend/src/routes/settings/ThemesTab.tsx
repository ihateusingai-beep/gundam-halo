import { toast } from "sonner";

import { HudCard } from "@/components/gundam/HudCard";
import { THEMES } from "@/components/gundam/ThemeSwitcher";
import { useThemeStore } from "@/stores/theme";

import { BACKGROUNDS } from "./constants";
import { Section } from "./shared";

export function ThemesTab() {
  const { theme, setTheme, background, setBackground } = useThemeStore();
  return (
    <HudCard>
      <h3 className="text-sm font-[Orbitron] text-[var(--accent)] uppercase tracking-widest mb-3">
        Themes
      </h3>
      <Section title="Theme">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          {THEMES.map((t) => (
            <button
              key={t.id}
              onClick={() => {
                setTheme(t.id);
                toast.success(`Theme → ${t.name}`, { description: t.description });
              }}
              className={`p-3 rounded border text-left transition-all hover:border-[var(--accent)] ${
                theme === t.id
                  ? "border-[var(--accent)] bg-[var(--bg-elevated)]"
                  : "border-[var(--border-color)] bg-[var(--bg-card)]"
              }`}
            >
              <div className="text-2xl">{t.emoji}</div>
              <div className="text-sm font-[Rajdhani] uppercase tracking-wider mt-1">
                {t.name}
              </div>
              <div className="text-[10px] text-[var(--text-muted)]">
                {t.description}
              </div>
            </button>
          ))}
        </div>
      </Section>

      <Section title="Cockpit Background">
        <p className="text-xs text-[var(--text-muted)] mb-3 font-mono">
          Default: pure CSS hex grid. Optional: 4 NT-D psychoframe JPGs.
        </p>
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
          {BACKGROUNDS.map((b) => (
            <button
              key={b.id}
              onClick={() => {
                setBackground(b.id);
                toast.success(`Background → ${b.label}`, {
                  description: b.description,
                });
              }}
              className={`p-2 rounded border text-left transition-all hover:border-[var(--accent)] ${
                background === b.id
                  ? "border-[var(--accent)] bg-[var(--bg-elevated)]"
                  : "border-[var(--border-color)] bg-[var(--bg-card)]"
              }`}
            >
              <div
                className="w-full h-16 rounded mb-2 border border-[var(--border-color)] overflow-hidden flex items-center justify-center"
                style={
                  b.thumb
                    ? {
                        backgroundImage: `url(${b.thumb})`,
                        backgroundSize: "cover",
                        backgroundPosition: "center",
                        filter: "brightness(0.7) saturate(1.1)",
                      }
                    : {
                        backgroundImage:
                          "repeating-linear-gradient(60deg, transparent 0 8px, rgba(0,212,255,0.08) 8px 9px), repeating-linear-gradient(120deg, transparent 0 8px, rgba(0,212,255,0.08) 8px 9px)",
                      }
                }
              />
              <div className="text-sm font-[Rajdhani] uppercase tracking-wider">
                {b.label}
              </div>
              <div className="text-[10px] text-[var(--text-muted)]">
                {b.description}
              </div>
            </button>
          ))}
        </div>
      </Section>
    </HudCard>
  );
}

import { toast } from "sonner";

import { HudCard } from "@/components/gundam/HudCard";
import { THEMES } from "@/components/gundam/ThemeSwitcher";
import { useThemeStore } from "@/stores/theme";

import { BACKGROUNDS } from "../constants";
import { Section } from "../shared";

/**
 * Sprint 51 — global accent color override.
 *
 * Renders a color input + reset button on the Themes tab. The
 * store applies the accent via `[data-custom-accent]` selector
 * declared LAST in gundam.css, which wins the cascade over
 * per-theme `--accent` rules. Without that ordering, inline
 * `style="--accent: ..."` would always win and hover-preview
 * could never show theme defaults.
 */
function AccentPicker() {
  const accent = useThemeStore((s) => s.accent);
  const setAccent = useThemeStore((s) => s.setAccent);

  // Default the color input to a theme accent when none is set;
  // we use the second common accent from the brand (cyan #00D4FF)
  // since NTD is the default theme.
  const fallback = "#00D4FF";

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3 flex-wrap">
        <label
          htmlFor="accent-input"
          className="text-sm font-mono text-[var(--text-primary)]"
        >
          Custom accent
        </label>
        <input
          id="accent-input"
          data-testid="accent-input"
          type="color"
          value={accent ?? fallback}
          onChange={(e) => setAccent(e.target.value)}
          aria-describedby="accent-help"
          className="w-10 h-10 rounded cursor-pointer border border-[var(--border-color)] bg-transparent"
        />
        <span
          data-testid="accent-hex-display"
          className="font-mono text-xs text-[var(--text-muted)]"
        >
          {accent ?? "(theme default)"}
        </span>
        <button
          type="button"
          data-testid="accent-reset"
          onClick={() => setAccent(null)}
          disabled={accent === null}
          aria-label="Reset accent to theme default"
          className="px-3 py-1 text-xs font-mono rounded border border-[var(--border-color)]
                     hover:border-[var(--accent)] disabled:opacity-40 disabled:cursor-not-allowed
                     disabled:hover:border-[var(--border-color)]"
        >
          Reset
        </button>
      </div>
      <p id="accent-help" className="text-[10px] text-[var(--text-muted)] font-mono">
        Overrides <code>--accent</code> across all themes. Click Reset to restore the active theme's preset.
      </p>
    </div>
  );
}

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

      <Section title="Accent color">
        <AccentPicker />
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

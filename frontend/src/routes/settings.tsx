import { HudCard } from "@/components/gundam/HudCard";
import { useThemeStore, type CockpitBackground } from "@/stores/theme";
import { THEMES } from "@/components/gundam/ThemeSwitcher";
import { toast } from "sonner";

interface BgOption {
  id: CockpitBackground;
  label: string;
  description: string;
  thumb: string | null; // null = no thumb, render placeholder
}

const BACKGROUNDS: BgOption[] = [
  { id: "none",    label: "NONE",    description: "Pure hex grid — fast, no asset", thumb: null },
  { id: "core-01", label: "CORE-01", description: "Psychoframe — pink pulse",       thumb: "/gundam-assets/backgrounds/bg-unicorn-core-01.jpg" },
  { id: "core-02", label: "CORE-02", description: "Psychoframe — cyan glow",        thumb: "/gundam-assets/backgrounds/bg-unicorn-core-02.jpg" },
  { id: "core-03", label: "CORE-03", description: "Psychoframe — strong pulse",     thumb: "/gundam-assets/backgrounds/bg-unicorn-core-03.jpg" },
  { id: "core-04", label: "CORE-04", description: "Psychoframe — soft glow",        thumb: "/gundam-assets/backgrounds/bg-unicorn-core-04.jpg" },
];

/** Settings page — theme picker + cockpit background picker. */
export function SettingsPage() {
  const { theme, setTheme, background, setBackground } = useThemeStore();

  return (
    <div className="space-y-4">
      <HudCard>
        <h2 className="text-2xl font-[Orbitron] text-[var(--accent)] tracking-widest uppercase mb-3">
          Settings
        </h2>
        <p className="text-sm text-[var(--text-secondary)]">
          Configuration for Gundam Halo. Most settings come from{" "}
          <code className="text-[var(--accent)]">~/.gundam-halo/config.toml</code>.
        </p>
      </HudCard>

      <HudCard>
        <h3 className="text-sm font-[Orbitron] text-[var(--accent)] uppercase tracking-widest mb-3">
          Theme
        </h3>
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
      </HudCard>

      <HudCard>
        <h3 className="text-sm font-[Orbitron] text-[var(--accent)] uppercase tracking-widest mb-3">
          Cockpit Background
        </h3>
        <p className="text-xs text-[var(--text-muted)] mb-3 font-mono">
          Default: pure CSS hex grid (no asset). Optional: switch to one of 4 NT-D psychoframe JPGs.
        </p>
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
          {BACKGROUNDS.map((b) => (
            <button
              key={b.id}
              onClick={() => {
                setBackground(b.id);
                toast.success(`Background → ${b.label}`, { description: b.description });
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
      </HudCard>

      <HudCard>
        <h3 className="text-sm font-[Orbitron] text-[var(--accent)] uppercase tracking-widest mb-3">
          About
        </h3>
        <p className="text-xs text-[var(--text-muted)] font-mono">
          Gundam Halo v0.1.0 · MIT License · Built by Ken with Mavis
        </p>
      </HudCard>
    </div>
  );
}

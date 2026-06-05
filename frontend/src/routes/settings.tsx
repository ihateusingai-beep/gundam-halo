import { HudCard } from "@/components/gundam/HudCard";
import { useThemeStore } from "@/stores/theme";
import { THEMES } from "@/components/gundam/ThemeSwitcher";
import { toast } from "sonner";

/** Settings page — theme picker + (future) other settings. */
export function SettingsPage() {
  const { theme, setTheme } = useThemeStore();

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
          About
        </h3>
        <p className="text-xs text-[var(--text-muted)] font-mono">
          Gundam Halo v0.1.0 · MIT License · Built by Ken with Mavis
        </p>
      </HudCard>
    </div>
  );
}

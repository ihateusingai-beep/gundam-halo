/**
 * StepTheme — Wizard step 5. Pick from 8 Gundam themes.
 *
 * Each theme card shows the accent color + a 2-line sample text.
 * Clicking a card applies the theme IMMEDIATELY (via
 * document.documentElement.setAttribute('data-theme', …)) so the
 * pilot can preview before clicking Next.
 *
 * The default theme is gundam-ntd (Unicorn psychoframe — most iconic
 * of the 8 themes per the project memory). See app/core/setup_state.py
 * for the canonical list.
 */

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { ThemeConfig } from "@/types/api";
import type { WizardError } from "@/hooks/useSetupWizard";

export interface StepThemeProps {
  form: ThemeConfig;
  onChange: (cfg: ThemeConfig) => Promise<void>;
  errors: WizardError[];
  busy: boolean;
}

interface ThemeMeta {
  id: ThemeConfig["themeId"];
  name: string;
  accent: string;
  sample: string;
}

const THEMES: ThemeMeta[] = [
  { id: "gundam-ntd", name: "NT-D / Unicorn", accent: "#ff2dd4", sample: "Psychoframe online." },
  { id: "gundam-god", name: "Gundam God", accent: "#ffaa00", sample: "Divine strike." },
  { id: "gundam-seed", name: "Gundam SEED", accent: "#ff5577", sample: "Phase Shift on." },
  { id: "gundam-crossbone", name: "Crossbone", accent: "#5dafff", sample: "Pirate trail." },
  { id: "gundam-destiny", name: "Destiny", accent: "#aa55ff", sample: "Wings of Light." },
  { id: "gundam-halo", name: "Gundam Halo", accent: "#00d4ff", sample: "Cockpit standby." },
  { id: "gundam-ntd-green", name: "NT-D Green", accent: "#5dffa0", sample: "Awakening." },
  { id: "gundam-cartoon", name: "Cartoon", accent: "#ffdd55", sample: "Original 1979." },
];

export function StepTheme({ form, onChange, errors, busy }: StepThemeProps) {
  return (
    <div className="space-y-3 py-2" data-testid="step-theme">
      <h2 className="text-lg font-[Rajdhani] text-[var(--text-primary)]">
        Theme
      </h2>
      <p className="text-[10px] text-[var(--text-muted)] font-mono">
        Click a theme to preview. Click Next to save.
      </p>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        {THEMES.map((t) => {
          const isSelected = form.themeId === t.id;
          return (
            <button
              key={t.id}
              data-testid={`theme-${t.id}`}
              onClick={() => {
                // Apply immediately for live preview.
                document.documentElement.setAttribute("data-theme", t.id);
                onChange({ themeId: t.id });
              }}
              className={cn(
                "border-2 p-2 text-left transition-all",
                isSelected
                  ? "shadow-[0_0_12px_var(--accent)]"
                  : "hover:scale-[1.02]",
              )}
              style={{
                borderColor: isSelected ? t.accent : "var(--border-color)",
              }}
            >
              <div
                className="h-8 w-full mb-2 rounded-sm"
                style={{ background: t.accent }}
              />
              <div className="text-xs font-[Rajdhani] font-bold">{t.name}</div>
              <div className="text-[10px] text-[var(--text-muted)] font-mono">
                {t.sample}
              </div>
            </button>
          );
        })}
      </div>

      {errors.length > 0 && (
        <p className="text-[10px] text-[var(--danger)] font-mono">
          {errors[0].message}
        </p>
      )}

      <Button
        onClick={() => onChange(form)}
        disabled={busy}
        data-testid="theme-next"
      >
        {busy ? "Saving…" : "Next →"}
      </Button>
    </div>
  );
}

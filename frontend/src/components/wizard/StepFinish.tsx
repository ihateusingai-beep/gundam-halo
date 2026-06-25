/**
 * StepFinish — Wizard success screen.
 *
 * Shown after the wizard completes (or the user clicks Skip /
 * Reset). The "Open cockpit" CTA navigates to "/" — the parent
 * WizardShell handles the navigate() call so this component stays
 * purely presentational.
 */

import { HudCard } from "@/components/gundam/HudCard";
import { Button } from "@/components/ui/button";

export interface StepFinishProps {
  redirect: string | null;
  onOpenCockpit: () => void;
}

export function StepFinish({ redirect, onOpenCockpit }: StepFinishProps) {
  return (
    <div className="max-w-2xl mx-auto p-4 space-y-4" data-testid="step-finish">
      <HudCard className="!border-[var(--accent)]">
        <div className="text-center py-8 space-y-3">
          <div className="text-6xl">✓</div>
          <h1 className="text-2xl font-[Orbitron] text-[var(--accent)] uppercase tracking-widest">
            Setup complete
          </h1>
          <p className="text-sm text-[var(--text-secondary)] font-mono">
            All 7 steps finished. Gundam Halo is ready.
          </p>
          <p className="text-[10px] text-[var(--text-muted)] font-mono">
            {redirect
              ? `Redirecting to ${redirect}…`
              : "Click below to open the cockpit."}
          </p>
          <div className="pt-4">
            <Button onClick={onOpenCockpit} data-testid="finish-open-cockpit">
              Open cockpit →
            </Button>
          </div>
        </div>
      </HudCard>
    </div>
  );
}

import { MissionSelect } from "@/components/gundam/MissionSelect";
import { HeldOutEvalCard } from "@/components/dashboard/HeldOutEvalCard";
import { ModelSwapDialog } from "@/components/dashboard/ModelSwapDialog";
import { SetupWizard } from "@/components/dashboard/SetupWizard";
import { VoiceWsIndicator } from "@/components/dashboard/VoiceWsIndicator";

/**
 * Overview page — cockpit standby view.
 *
 * Layout (Sprint 39):
 *   ┌────────────────────────────────────────────┐
 *   │ Mission Select (existing)                  │
 *   ├────────────────────────────────────────────┤
 *   │ System Status (new 2×2 grid)               │
 *   │   ┌──────────────┬────────────────┐        │
 *   │   │ SetupWizard  │ VoiceWsLink    │        │
 *   │   ├──────────────┼────────────────┤        │
 *   │   │ HeldOutEval  │ ModelSwap      │        │
 *   │   └──────────────┴────────────────┘        │
 *   └────────────────────────────────────────────┘
 *
 * The 4 dashboard cards surface backend capabilities that
 * would otherwise be hidden in settings tabs and CLI scripts.
 * On mobile (<768 px) the grid stacks vertically via the
 * existing Tailwind grid (`grid-cols-1 md:grid-cols-2`).
 */
export function OverviewPage() {
  return (
    <div className="space-y-4">
      <MissionSelect />
      <section aria-label="System Status" className="space-y-3">
        <h2 className="text-[10px] font-[Orbitron] text-[var(--text-muted)] uppercase tracking-widest">
          System Status
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <SetupWizard />
          <VoiceWsIndicator />
          <HeldOutEvalCard />
          <ModelSwapDialog />
        </div>
      </section>
    </div>
  );
}

import { SetupWizard } from "./SetupWizard";
import { VoiceWsIndicator } from "./VoiceWsIndicator";
import { HeldOutEvalCard } from "./HeldOutEvalCard";
import { ModelSwapDialog } from "./ModelSwapDialog";

/**
 * SystemStatusGrid — the 4-card 2×2 dashboard on the Overview
 * page (`/`).
 *
 * Sprint 68.6 X-C1: extracted from `routes/index.tsx` so the
 * 4 cards can be lazy-loaded as ONE chunk (Sprint 68.5 left
 * the main bundle at 665.92 kB; the dashboard cards are the
 * biggest remaining contributor since OverviewPage is eager).
 *
 * ## Why extract + lazy as one unit (not 4 individual cards)
 *
 *  - **Chunk efficiency**: 1 chunk instead of 4. Less HTTP
 *    overhead, simpler cache invalidation.
 *  - **Suspense UX**: 1 skeleton for the whole grid instead
 *    of 4 popping in sequentially.
 *  - **Testability**: 1 mount test covers all 4 cards'
 *    composition. The cards themselves have their own tests.
 *  - **Diff size**: 1 file change in `routes/index.tsx`
 *    (replace 4 imports with 1 lazy import).
 *
 * ## Trade-off: brief skeleton flash on `/` first paint
 *
 * The cards are not critical for the cockpit's "mission
 * select" surface (which is already eager). Users see
 * MissionSelect immediately, then the 2×2 grid pops in
 * ~50-100ms later. Acceptable per the Sprint 68.6 plan
 * (vs. ~150 kB LHCI savings).
 */
export function SystemStatusGrid() {
  return (
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
  );
}

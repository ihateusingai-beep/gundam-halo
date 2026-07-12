import { Suspense } from "react";

import { MissionSelect } from "@/components/gundam/MissionSelect";
import { SystemStatusGrid } from "@/components/dashboard/SystemStatusGrid";
import { RouteFallback } from "@/components/layout/RouteFallback";
import { lazyRoute } from "@/lib/lazy-route";

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
 *
 * Sprint 68.6 X-C1: the System Status grid is lazy-loaded
 * via `lazyRoute()` + per-component `<Suspense>`. The 4
 * cards are extracted to `components/dashboard/
 * SystemStatusGrid.tsx` so they ship as ONE chunk. Trade-off:
 * brief skeleton flash on `/` first paint; reward: ~150 kB
 * savings on the main bundle (LHCI 500 kB budget).
 */
const LazySystemStatusGrid = lazyRoute(
  () => import("@/components/dashboard/SystemStatusGrid"),
  "SystemStatusGrid",
);

export function OverviewPage() {
  return (
    <div className="space-y-4">
      <MissionSelect />
      <Suspense fallback={<RouteFallback />}>
        <LazySystemStatusGrid />
      </Suspense>
    </div>
  );
}

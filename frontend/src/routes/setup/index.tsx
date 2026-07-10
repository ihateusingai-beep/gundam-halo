/**
 * /setup — Sprint 44 7-step setup wizard.
 *
 * The wizard backend is fully implemented (see
 * `backend/app/api/setup.py` — 11 endpoints, 979 LoC, 38+ tests).
 * Sprint 44 ships the UI that drives those endpoints.
 *
 * Pre-step gate: if the BackendHealthBanner reports the backend is
 * unhealthy, the wizard blocks with a "Backend is restarting" screen
 * rather than letting the user fill 7 steps against a dying backend.
 * The wizard auto-resumes once the backend recovers.
 *
 * The page itself is just a thin wrapper around <WizardShell /> —
 * all state lives in the useSetupWizard hook.
 */

import { useEffect, useState } from "react";

import { Card } from "@/components/ui/card";
import { WizardShell } from "@/components/wizard/WizardShell";
import { getWatchdogStatus, subscribeWatchdog } from "@/services/halo-watchdog-events";

export function SetupPage() {
  const [health, setHealth] = useState(() => getWatchdogStatus());

  useEffect(() => {
    return subscribeWatchdog((s) => setHealth(s));
  }, []);

  // Block the wizard if the backend is in trouble — saves the user
  // from filling 7 steps against a dying backend.
  if (health.state === "respawn-disabled") {
    return (
      <div className="max-w-2xl mx-auto p-4">
        <Card className="border-[var(--danger)]">
          <div
            className="p-6 text-center space-y-3"
            data-testid="setup-health-blocked"
          >
            <h2 className="text-xl font-[Orbitron] text-[var(--danger)] uppercase tracking-widest">
              Backend unhealthy
            </h2>
            <p className="text-sm text-[var(--text-secondary)] font-mono">
              The backend has crashed {health.crashCount60m} times in the last
              hour and respawn is disabled. Fix the backend first
              (clear the crash log from the cockpit banner), then reopen
              this wizard.
            </p>
          </div>
        </Card>
      </div>
    );
  }

  return <WizardShell />;
}

/**
 * BackendHealthBanner — Sprint 43 cockpit banner.
 *
 * Mounted above BackendOutdatedBanner in CockpitLayout. Hidden by
 * default (when the backend is healthy). Renders on three states
 * driven by `services/halo-watchdog-events.ts`:
 *
 *   1. **healthy** (default) — hidden
 *   2. **unhealthy** — yellow "Backend unreachable — checking…"
 *      banner. Auto-clears on `backend-recovered` event.
 *   3. **respawn-disabled** — red "Respawn disabled" banner with
 *      two action buttons:
 *        - "Clear crash log & retry" → calls `clear_crash_log` IPC
 *          → backend truncates `crash_log.jsonl` → the watchdog's
 *          next 60s tick re-checks health.
 *        - "Install launchd supervisor" → calls
 *          `install_launchd_supervisor` IPC (one-click when the
 *          user never ran `scripts/install-launchd.sh`).
 *
 * The banner also reads the initial backend health via the
 * `get_backend_health` IPC at mount time (so the user doesn't
 * wait up to 60s for the first watchdog tick).
 */

import { useEffect, useState } from "react";
import { toast } from "sonner";

import { HudCard } from "@/components/gundam/HudCard";
import { isTauriRuntime, tryTauriInvoke } from "@/lib/tauri";
import {
  type WatchdogStatus,
  getWatchdogStatus,
  subscribeWatchdog,
} from "@/services/halo-watchdog-events";

interface BackendHealthIpc {
  installed: boolean;
  pid: number | null;
  crash_count_60m: number;
  last_crash_at: string | null;
  last_check_at: string | null;
  respawn_disabled: boolean;
}

export function BackendHealthBanner() {
  const [status, setStatus] = useState<WatchdogStatus>(() => getWatchdogStatus());
  const [installing, setInstalling] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [initialFetchDone, setInitialFetchDone] = useState(false);
  const inTauri = isTauriRuntime();

  // Subscribe to watchdog events (Tauri runtime only).
  useEffect(() => {
    const unsubscribe = subscribeWatchdog((next) => {
      setStatus(next);
    });
    return unsubscribe;
  }, []);

  // Initial fetch via IPC — so the banner doesn't wait 60s for
  // the first watchdog tick to render the correct initial state.
  useEffect(() => {
    if (!inTauri) {
      setInitialFetchDone(true);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const health = await tryTauriInvoke<BackendHealthIpc>("get_backend_health");
        if (cancelled || !health) {
          setInitialFetchDone(true);
          return;
        }
        // Seed the singleton so the banner reflects reality even
        // before any watchdog event fires.
        const current = getWatchdogStatus();
        const newState: WatchdogStatus["state"] = health.respawn_disabled
          ? "respawn-disabled"
          : health.crash_count_60m > 0
            ? "unhealthy"
            : "healthy";
        // Avoid stomping a real event-driven state.
        if (current.state === "healthy" && newState !== "healthy") {
          setStatus({
            ...current,
            state: newState,
            crashCount60m: health.crash_count_60m,
            lastCrashAt: health.last_crash_at,
            lastTransitionAt: health.last_check_at ?? new Date().toISOString(),
          });
        }
      } catch (e) {
        // best-effort; the watchdog will catch up on its next tick.
        console.warn("[BackendHealthBanner] initial fetch failed:", e);
      } finally {
        if (!cancelled) setInitialFetchDone(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [inTauri]);

  async function handleClearCrashLog() {
    setClearing(true);
    try {
      const cleared = await tryTauriInvoke<number>("clear_crash_log");
      if (cleared === null) {
        toast.error("Not running in the Tauri shell.");
        return;
      }
      toast.success(`Cleared ${cleared} crash entries`, {
        description:
          "Backend will retry on next watchdog tick (within 60 seconds).",
      });
      // Optimistically flip the banner state — the watchdog will
      // confirm on its next poll. This gives the user immediate
      // feedback rather than waiting up to 60s.
      setStatus((prev) => ({ ...prev, state: "healthy" }));
    } catch (e) {
      toast.error("Failed to clear crash log", {
        description: String(e),
      });
    } finally {
      setClearing(false);
    }
  }

  async function handleInstallSupervisor() {
    setInstalling(true);
    try {
      const out = await tryTauriInvoke<string>("install_launchd_supervisor");
      if (out === null) {
        toast.error("Not running in the Tauri shell.");
        return;
      }
      toast.success("Launchd supervisor installed", {
        description: out.split("\n")[0] ?? "Restart backend via menu bar.",
      });
    } catch (e) {
      toast.error("Install failed", {
        description: String(e),
      });
    } finally {
      setInstalling(false);
    }
  }

  // Hidden when healthy AND we've confirmed the initial state (so we
  // don't flash the banner during the first 100ms before the initial
  // IPC fetch returns).
  if (status.state === "healthy" && initialFetchDone) {
    return null;
  }

  if (status.state === "respawn-disabled") {
    return (
      <div className="mx-2 mt-2" data-testid="backend-health-banner">
        <HudCard className="!border-[var(--danger)] !bg-[var(--danger)]/5">
          <div className="flex items-start gap-3">
            <span className="text-2xl text-[var(--danger)]" aria-hidden>
              ⚠
            </span>
            <div className="flex-1 min-w-0">
              <div
                className="text-sm font-[Orbitron] uppercase tracking-widest text-[var(--danger)]"
                data-state="respawn-disabled"
              >
                Backend respawn disabled
              </div>
              <p className="text-xs text-[var(--text-secondary)] font-mono mt-1">
                {status.crashCount60m >= 3
                  ? `Backend has crashed ${status.crashCount60m} times in the last hour.`
                  : "Backend has crashed multiple times in the last hour."}{" "}
                Respawn disabled to protect your Mac. Investigate{" "}
                <code className="text-[var(--accent)]">
                  ~/.gundam-halo/logs/launchd.err.log
                </code>{" "}
                before retrying.
              </p>
              <div className="flex items-center gap-2 mt-3 flex-wrap">
                <button
                  onClick={handleClearCrashLog}
                  disabled={clearing}
                  className="px-3 py-1 text-[10px] uppercase tracking-wider font-[Rajdhani] border border-[var(--danger)] text-[var(--danger)] hover:bg-[var(--danger)] hover:text-[var(--bg-primary)] transition-colors disabled:opacity-40"
                >
                  {clearing ? "Clearing…" : "Clear crash log & retry"}
                </button>
                <button
                  onClick={handleInstallSupervisor}
                  disabled={installing}
                  className="px-3 py-1 text-[10px] uppercase tracking-wider font-[Rajdhani] border border-[var(--warning)] text-[var(--warning)] hover:bg-[var(--warning)] hover:text-[var(--bg-primary)] transition-colors disabled:opacity-40"
                  title="Re-install the launchd supervisor plist (com.gundam.halo)"
                >
                  {installing ? "Installing…" : "Install launchd supervisor"}
                </button>
              </div>
            </div>
          </div>
        </HudCard>
      </div>
    );
  }

  // unhealthy (yellow)
  return (
    <div className="mx-2 mt-2" data-testid="backend-health-banner">
      <HudCard className="!border-[var(--warning)] !bg-[var(--warning)]/5">
        <div className="flex items-start gap-3">
          <span className="text-2xl text-[var(--warning)]" aria-hidden>
            ◌
          </span>
          <div className="flex-1 min-w-0">
            <div
              className="text-sm font-[Orbitron] uppercase tracking-widest text-[var(--warning)]"
              data-state="unhealthy"
            >
              Backend unreachable
            </div>
            <p className="text-xs text-[var(--text-secondary)] font-mono mt-1">
              {status.consecutiveFailures} consecutive failures (threshold 3).
              Waiting for the backend to recover — checking every 60s.
            </p>
          </div>
        </div>
      </HudCard>
    </div>
  );
}

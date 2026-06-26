/**
 * RestartNudgeBanner — Sprint 41 (Feature I).
 *
 * Mounts at the top of the cockpit. Visible ONLY when the
 * backend has a self-restart scheduled (the user changed
 * asr_backend or asr_corrector, and the 5-second countdown is
 * ticking). Renders a cyan pulsing pill with a live countdown
 * + "Cancel" button.
 *
 * Data source: `GET /voice/config` polled every 1 s while
 * a restart is scheduled. The polling is gated — the interval
 * only runs while `restart_scheduled === true`, stops
 * immediately when false (cancelled or fired).
 *
 * Outside the Tauri shell (web dev mode), the "Cancel" button
 * shows a manual-restart instructions toast instead — the
 * endpoint requires the backend process to be reachable, and
 * a curl command from the Tauri shell is more discoverable.
 *
 * The banner auto-hides when `restart_in_seconds <= 0` — by
 * that time the restart has either fired (websocket briefly
 * disconnects) or been cancelled.
 */

import { useEffect, useState } from "react";
import { toast } from "sonner";

import { HudCard } from "@/components/gundam/HudCard";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { isTauriRuntime, tryTauriInvoke } from "@/lib/tauri";

const POLL_INTERVAL_MS = 1_000;

export function RestartNudgeBanner() {
  const [restartScheduled, setRestartScheduled] = useState(false);
  const [restartInSeconds, setRestartInSeconds] = useState<number | null>(
    null,
  );
  const [cancelling, setCancelling] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let intervalId: ReturnType<typeof setInterval> | null = null;

    async function poll() {
      try {
        const c = await api.getVoiceConfig();
        if (cancelled) return;
        const scheduled = !!c.restart_scheduled;
        setRestartScheduled(scheduled);
        setRestartInSeconds(c.restart_in_seconds ?? null);

        if (scheduled && intervalId === null) {
          intervalId = setInterval(poll, POLL_INTERVAL_MS);
        } else if (!scheduled && intervalId !== null) {
          clearInterval(intervalId);
          intervalId = null;
        }
      } catch {
        // best-effort — banner hides on error.
        if (!cancelled) {
          setRestartScheduled(false);
          setRestartInSeconds(null);
        }
      }
    }

    void poll();
    return () => {
      cancelled = true;
      if (intervalId !== null) clearInterval(intervalId);
    };
  }, []);

  async function handleCancel() {
    setCancelling(true);
    try {
      const res = await tryTauriInvoke<boolean>("cancel_restart");
      if (res === null) {
        // Outside the Tauri shell — show manual instructions.
        toast.info("Manual restart required", {
          description:
            "Run: pkill -f 'uvicorn app.main:app' && cd backend && uv run --project . uvicorn app.main:app --host 0.0.0.0 --port 8765",
          duration: 12_000,
        });
        return;
      }
      toast.success("Restart cancelled");
      // Optimistic update — the polling will confirm on the
      // next tick. Avoids the 1-second wait for visual feedback.
      setRestartScheduled(false);
      setRestartInSeconds(null);
    } catch (e) {
      toast.error("Failed to cancel restart", {
        description: e instanceof Error ? e.message : String(e),
      });
    } finally {
      setCancelling(false);
    }
  }

  if (!restartScheduled) return null;

  // Floors at 0 (Sprint 41 spec — never negative).
  const secondsLeft = Math.max(0, Math.ceil(restartInSeconds ?? 0));

  return (
    <div className="mx-2 mt-2" data-testid="restart-nudge-banner">
      <HudCard pulse>
        <div className="flex items-center gap-3">
          <span className="text-xl text-[var(--accent)]" aria-hidden>
            ⟳
          </span>
          <div className="flex-1 min-w-0">
            <div
              className="text-sm font-[Orbitron] uppercase tracking-widest text-[var(--accent)]"
              data-state="scheduled"
              data-seconds-left={secondsLeft}
            >
              Backend restarting in {secondsLeft}s…
            </div>
            <p className="text-xs text-[var(--text-secondary)] font-mono mt-1">
              New ASR engine / corrector will load on the next process.
              Click Cancel to abort.
            </p>
          </div>
          <Button
            data-testid="cancel-restart-button"
            onClick={handleCancel}
            disabled={cancelling}
            variant="outline"
            size="sm"
          >
            {cancelling ? "Cancelling…" : "Cancel"}
          </Button>
        </div>
      </HudCard>
    </div>
  );
}
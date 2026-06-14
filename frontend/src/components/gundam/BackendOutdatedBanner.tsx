/**
 * BackendOutdatedBanner — top-of-cockpit warning when the running
 * backend is on a different git SHA than this frontend bundle, or
 * is missing required features.
 *
 * Two actions:
 *   - "Copy restart command" — copies a `uvicorn` restart one-liner
 *     to the clipboard, so the user can paste it in their terminal
 *   - "Restart backend" — Tauri-only. Invokes a Rust command that
 *     kills + respawns the uvicorn process. Web dev mode hides the
 *     button (no supervisor in another tab).
 *   - "Reload page" — reloads the browser to pick up the new build
 *
 * The banner is dismissible (snooze for the session) but re-appears
 * on the next poll if the mismatch persists.
 */

import { useState } from "react";
import { toast } from "sonner";

import { HudCard } from "@/components/gundam/HudCard";
import { isTauriRuntime } from "@/lib/tauri";

export interface BackendOutdatedBannerProps {
  /** The frontend bundle's git SHA (build-time constant). */
  frontendSha: string;
  /** The backend's currently-reported git SHA. */
  backendSha: string;
  /** Features required by this frontend but missing from the backend. */
  missingFeatures?: string[];
  /** Optional: hint about why this happened. */
  hint?: string;
}

const FRONTEND_GIT_SHA = __GIT_SHA__;

/** Default restart command for the production launch script. */
const DEFAULT_RESTART_CMD =
  "cd ~/workspace/working/gundam-halo/backend && " +
  "lsof -ti tcp:8000 | xargs kill -9 2>/dev/null; " +
  "uv run --project . uvicorn app.main:app --host 0.0.0.0 --port 8000";

export function BackendOutdatedBanner({
  frontendSha,
  backendSha,
  missingFeatures = [],
  hint,
}: BackendOutdatedBannerProps) {
  const [dismissed, setDismissed] = useState(false);
  const [restarting, setRestarting] = useState(false);
  const inTauri = isTauriRuntime();

  if (dismissed) return null;

  const shortFe = (sha: string) => sha.slice(0, 8);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(DEFAULT_RESTART_CMD);
      toast.success("Restart command copied", {
        description: "Paste into your terminal to restart the backend.",
      });
    } catch (e) {
      toast.error("Couldn't copy", {
        description: `Select the command manually: ${DEFAULT_RESTART_CMD}`,
      });
    }
  };

  const handleRestart = async () => {
    setRestarting(true);
    try {
      const { invoke } = await import("@tauri-apps/api/core");
      await invoke("restart_backend");
      toast.success("Backend restarting…", {
        description: "Wait ~3s then click Reload.",
      });
    } catch (e) {
      toast.error("Tauri restart failed", { description: String(e) });
      setRestarting(false);
    }
  };

  return (
    <div className="mx-2 mt-2">
      <HudCard className="!border-[var(--warning)] !bg-[var(--warning)]/5">
        <div className="flex items-start gap-3">
          <span className="text-2xl text-[var(--warning)]" aria-hidden>
            ⚠
          </span>
          <div className="flex-1 min-w-0">
            <div className="text-sm font-[Orbitron] uppercase tracking-widest text-[var(--warning)]">
              Backend outdated
            </div>
            <p className="text-xs text-[var(--text-secondary)] font-mono mt-1">
              The frontend is on{" "}
              <span className="text-[var(--text-primary)]">
                {shortFe(frontendSha)}
              </span>{" "}
              but the backend is on{" "}
              <span className="text-[var(--text-primary)]">
                {shortFe(backendSha)}
              </span>
              . Restart the backend to load the latest changes.
            </p>
            {missingFeatures.length > 0 && (
              <p className="text-[10px] text-[var(--text-muted)] font-mono mt-1">
                Missing features: {missingFeatures.join(", ")}
              </p>
            )}
            {hint && (
              <p className="text-[10px] text-[var(--text-muted)] font-mono mt-1">
                {hint}
              </p>
            )}
            <div className="flex items-center gap-2 mt-3 flex-wrap">
              <button
                onClick={handleCopy}
                className="px-3 py-1 text-[10px] uppercase tracking-wider font-[Rajdhani] border border-[var(--warning)] text-[var(--warning)] hover:bg-[var(--warning)] hover:text-[var(--bg-primary)] transition-colors"
              >
                Copy restart command
              </button>
              {inTauri && (
                <button
                  onClick={handleRestart}
                  disabled={restarting}
                  className="px-3 py-1 text-[10px] uppercase tracking-wider font-[Rajdhani] border border-[var(--accent)] text-[var(--accent)] hover:bg-[var(--accent)] hover:text-[var(--bg-primary)] transition-colors disabled:opacity-40"
                >
                  {restarting ? "Restarting…" : "Restart backend (Tauri)"}
                </button>
              )}
              <button
                onClick={() => window.location.reload()}
                className="px-3 py-1 text-[10px] uppercase tracking-wider font-[Rajdhani] border border-[var(--border-color)] text-[var(--text-muted)] hover:border-[var(--accent)] hover:text-[var(--accent)] transition-colors"
              >
                Reload page
              </button>
              <button
                onClick={() => setDismissed(true)}
                className="px-2 py-1 text-[10px] uppercase tracking-wider font-[Rajdhani] text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
                title="Snooze — re-appears on next poll if mismatch persists"
              >
                Snooze
              </button>
            </div>
          </div>
        </div>
      </HudCard>
    </div>
  );
}

/** Convenience: only render the banner when there's a real reason to. */
export function MaybeBackendOutdatedBanner({
  outdated,
  backend,
  missingFeatures,
}: {
  outdated: boolean;
  backend: { git_sha: string } | null;
  missingFeatures: string[];
}) {
  if (!outdated || !backend) {
    // Even when not outdated, if missing features is non-empty, show
    // a softer version of the banner.
    if (missingFeatures.length === 0) return null;
    return (
      <div className="mx-2 mt-2">
        <HudCard className="!border-[var(--warning)] !bg-[var(--warning)]/5">
          <div className="text-xs font-mono text-[var(--warning)]">
            ⚠ Backend missing features this frontend requires:{" "}
            {missingFeatures.join(", ")}
          </div>
        </HudCard>
      </div>
    );
  }
  return (
    <BackendOutdatedBanner
      frontendSha={FRONTEND_GIT_SHA}
      backendSha={backend.git_sha}
      missingFeatures={missingFeatures}
    />
  );
}

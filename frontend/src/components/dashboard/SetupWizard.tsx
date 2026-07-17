/**
 * SetupWizard — Sprint 39 cockpit card.
 *
 * Renders the M13 first-run setup wizard's current state on
 * the home page so the pilot can see at a glance whether
 * onboarding is complete. Three states:
 *
 *   1. **Complete / not started** (status === "complete" OR
 *      no state file on disk) → green HudCard with "Setup
 *      complete" + "Review" link to `/setup`.
 *   2. **In progress** (status === "in_progress") → yellow
 *      pulsing HudCard with "Step N of 3" (essential) or
 *      "Step N of 7" (advanced) + "Resume setup" link.
 *   3. **Skipped** (status === "skipped") → grey HudCard with
 *      "Setup skipped" + reason text.
 *
 * Data source: `GET /api/setup/state` (the same endpoint the
 * existing `/setup` page reads). We poll every 5s when the
 * card is mounted so the pulse state stays current without
 * requiring a page reload after each wizard step.
 *
 * Sprint 74 X-A — the dot count + "Step N of M" label now
 * reads `total_steps` and `mode` from the server response
 * (3 dots in essential, 7 in advanced). The old hardcoded
 * `TOTAL_STEPS = 8` was wrong (it counted `StepFinish` as a
 * navigable step; Finish is only rendered when the wizard
 * is finished).
 *
 * Graceful degradation: if `/api/setup/state` returns 404
 * (wizard hasn't been started yet — no state file), the
 * card renders "Setup not started" instead of crashing.
 * If the fetch throws for any other reason, we render an
 * "unavailable" grey state and log to console.
 *
 * The card never crashes the home page — even on network
 * error, the cockpit stays usable.
 */

import { useEffect, useState } from "react";
import { Link } from "react-router";

import { HudCard } from "@/components/gundam/HudCard";
import { api } from "@/lib/api";
import type { SetupState } from "@/types/api";

/** Polling interval for the setup state. 5s matches the VoiceTab poll. */
const POLL_INTERVAL_MS = 5_000;

type DisplayState =
  | { kind: "loading" }
  | { kind: "complete"; state: SetupState }
  | { kind: "in_progress"; state: SetupState }
  | { kind: "skipped"; state: SetupState }
  | { kind: "not_started" }
  | { kind: "unavailable"; reason: string };

function classify(state: SetupState | null): DisplayState {
  if (!state) return { kind: "not_started" };
  // The backend normalises "not started" to status="pending"
  // with current_step=1 and empty completed_steps; we treat
  // both "pending" and the "no state file" case as not_started.
  if (state.status === "complete") return { kind: "complete", state };
  if (state.status === "skipped") return { kind: "skipped", state };
  if (state.status === "in_progress" || state.status === "pending") {
    return { kind: "in_progress", state };
  }
  // Unknown status — treat as unavailable so the pilot
  // sees the badge but no crash.
  return { kind: "unavailable", reason: `unknown status: ${state.status}` };
}

export function SetupWizard() {
  const [display, setDisplay] = useState<DisplayState>({ kind: "loading" });

  useEffect(() => {
    let cancelled = false;

    async function poll() {
      try {
        const state = await api.getSetupState();
        if (!cancelled) setDisplay(classify(state));
      } catch (e) {
        // 404 → wizard not started. Any other error → unavailable.
        if (cancelled) return;
        const status = (e as { status?: number }).status;
        if (status === 404) {
          setDisplay({ kind: "not_started" });
        } else {
          setDisplay({
            kind: "unavailable",
            reason: e instanceof Error ? e.message : String(e),
          });
        }
      }
    }

    void poll();
    const id = setInterval(poll, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  // ---- Render branches ----
  if (display.kind === "loading") {
    return (
      <HudCard>
        <div data-testid="setup-wizard-card" data-state="loading">
          <span className="text-[10px] font-[Orbitron] text-[var(--text-muted)] uppercase tracking-widest">
            Setup
          </span>
          <p className="text-xs text-[var(--text-muted)] mt-1">Loading…</p>
        </div>
      </HudCard>
    );
  }

  if (display.kind === "complete") {
    return (
      <HudCard>
        <div data-testid="setup-wizard-card" data-state="complete">
          <span className="text-[10px] font-[Orbitron] text-[var(--text-muted)] uppercase tracking-widest">
            Setup
          </span>
          <h3 className="text-lg font-[Rajdhani] text-[var(--accent)] mt-1">
            Complete
          </h3>
          <p className="text-[10px] text-[var(--text-muted)] font-mono mt-1">
            All {display.state.total_steps ?? 3} steps finished
            {display.state.mode === "advanced" ? " (advanced)" : ""}.
          </p>
          <Link
            to="/setup"
            className="inline-block mt-2 text-[10px] font-[Rajdhani] uppercase tracking-wider text-[var(--text-secondary)] hover:text-[var(--accent)] transition-colors"
          >
            Review →
          </Link>
        </div>
      </HudCard>
    );
  }

  if (display.kind === "skipped") {
    return (
      <HudCard>
        <div data-testid="setup-wizard-card" data-state="skipped">
          <span className="text-[10px] font-[Orbitron] text-[var(--text-muted)] uppercase tracking-widest">
            Setup
          </span>
          <h3 className="text-lg font-[Rajdhani] text-[var(--text-muted)] mt-1">
            Skipped
          </h3>
          {display.state.reason && (
            <p className="text-[10px] text-[var(--text-muted)] font-mono mt-1">
              {display.state.reason}
            </p>
          )}
          <Link
            to="/setup"
            className="inline-block mt-2 text-[10px] font-[Rajdhani] uppercase tracking-wider text-[var(--text-secondary)] hover:text-[var(--accent)] transition-colors"
          >
            Run setup →
          </Link>
        </div>
      </HudCard>
    );
  }

  if (display.kind === "not_started") {
    return (
      <HudCard>
        <div data-testid="setup-wizard-card" data-state="not_started">
          <span className="text-[10px] font-[Orbitron] text-[var(--text-muted)] uppercase tracking-widest">
            Setup
          </span>
          <h3 className="text-lg font-[Rajdhani] text-[var(--text-secondary)] mt-1">
            Not started
          </h3>
          <p className="text-[10px] text-[var(--text-muted)] font-mono mt-1">
            Run the wizard to configure voice + LLM.
          </p>
          <Link
            to="/setup"
            className="inline-block mt-2 text-[10px] font-[Rajdhani] uppercase tracking-wider text-[var(--text-secondary)] hover:text-[var(--accent)] transition-colors"
          >
            Start setup →
          </Link>
        </div>
      </HudCard>
    );
  }

  if (display.kind === "unavailable") {
    return (
      <HudCard>
        <div data-testid="setup-wizard-card" data-state="unavailable">
          <span className="text-[10px] font-[Orbitron] text-[var(--text-muted)] uppercase tracking-widest">
            Setup
          </span>
          <h3 className="text-lg font-[Rajdhani] text-[var(--text-muted)] mt-1">
            Unavailable
          </h3>
          <p className="text-[10px] text-[var(--text-muted)] font-mono mt-1 truncate" title={display.reason}>
            {display.reason}
          </p>
        </div>
      </HudCard>
    );
  }

  // In progress — the most visually prominent state.
  const { state } = display;
  // Sprint 74 X-A — totalSteps is read from the server's
  // setup_state.json (3 in essential, 7 in advanced). Old responses
  // (pre-0.3.15 backend) won't have it; fall back to 3 (essential).
  const totalSteps = state.total_steps ?? 3;
  const stepLabel = `Step ${state.current_step} of ${totalSteps}`;
  const completedCount = state.completed_steps.length;
  const modeLabel = state.mode === "advanced" ? "advanced" : "essential";
  return (
    <HudCard pulse>
      <div data-testid="setup-wizard-card" data-state="in_progress">
        <div className="flex items-center justify-between">
          <span className="text-[10px] font-[Orbitron] text-[var(--warning)] uppercase tracking-widest">
            Setup · {modeLabel}
          </span>
          <span className="text-[10px] font-mono text-[var(--text-muted)]">
            {completedCount}/{totalSteps} done
          </span>
        </div>
        <h3 className="text-lg font-[Rajdhani] text-[var(--warning)] mt-1">
          {stepLabel}
        </h3>
        {/* Tiny progress dots — visual cue for "X of Y". Renders
         * 3 dots in essential mode, 7 in advanced. */}
        <div className="flex gap-1 mt-2" aria-hidden>
          {Array.from({ length: totalSteps }).map((_, i) => {
            const stepNum = i + 1;
            const isDone = state.completed_steps.includes(stepNum);
            const isCurrent = stepNum === state.current_step;
            return (
              <span
                key={stepNum}
                className={
                  "h-1 flex-1 rounded-sm " +
                  (isDone
                    ? "bg-[var(--accent)]"
                    : isCurrent
                      ? "bg-[var(--warning)]"
                      : "bg-[var(--border-color)]")
                }
              />
            );
          })}
        </div>
        <Link
          to="/setup"
          className="inline-block mt-3 text-[10px] font-[Rajdhani] uppercase tracking-wider text-[var(--warning)] hover:text-[var(--accent)] transition-colors"
        >
          Resume setup →
        </Link>
      </div>
    </HudCard>
  );
}

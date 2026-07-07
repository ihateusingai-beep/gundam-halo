/**
 * useBackendHealth — 3-state health-check hook.
 *
 * Sprint 49 B3: replaces the all-or-nothing `LOADING` placeholder.
 * The cockpit now:
 *   1. Renders the shell (sidebar, theme switcher, status rail) immediately
 *   2. Tries ONE health check with a 5 s timeout (AbortController)
 *   3. If success → `kind: "ready"` → render content
 *   4. If fail → `kind: "offline"` with the classified reason → render
 *      `<OfflineBanner>` (and the per-card content still tries; the
 *      banner is a "we tried, here's why it failed" affordance)
 *
 * The hook is mounted ONCE in `CockpitLayout`. Children that need
 * the health state use `useBackendHealthContext()` (re-exported
 * from a small context) or just call `api.health()` themselves
 * if they want a different timeout (rare).
 */
import { useEffect, useState } from "react";

import { api } from "./api";
import {
  backendErrorMessage,
  classifyBackendError,
  type BackendErrorKind,
} from "./backend-error";

/** Health-check discriminated union. Add new kinds sparingly;
 *  the existing 3 cover all current scenarios. */
export type HealthState =
  | { kind: "loading" }
  | { kind: "ready" }
  | {
      kind: "offline";
      reason: BackendErrorKind;
      /** Human-readable detail (server message, network error, etc). */
      detail: string;
    };

const HEALTH_TIMEOUT_MS = 5_000;

/** Run one health check with timeout. Re-runs on remount only. */
export function useBackendHealth(): HealthState {
  const [state, setState] = useState<HealthState>({ kind: "loading" });

  useEffect(() => {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), HEALTH_TIMEOUT_MS);
    api
      .health()
      .then(() => {
        if (!controller.signal.aborted) {
          setState({ kind: "ready" });
        }
      })
      .catch((e: unknown) => {
        if (controller.signal.aborted) return;
        const reason = classifyBackendError(e);
        // Compose the offline detail from the two-line
        // {headline, hint} shape so the OfflineBanner can
        // surface the actionable hint in a single line.
        const { headline, hint, detail: serverDetail } = backendErrorMessage(
          reason,
          e,
        );
        const detail = serverDetail
          ? `${headline} ${hint} (Server: ${serverDetail})`
          : `${headline} ${hint}`;
        setState({ kind: "offline", reason, detail });
      })
      .finally(() => clearTimeout(timeout));
    return () => {
      controller.abort();
      clearTimeout(timeout);
    };
  }, []);

  return state;
}

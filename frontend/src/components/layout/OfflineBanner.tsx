/**
 * OfflineBanner — friendly error surface for unreachable backend.
 *
 * Sprint 49 B3 + B5: replaces the silent "Failed to load…" toasts
 * with a dedicated banner at the top of the cockpit.
 *
 * After the mid-implementation audit, the per-kind hint mapping
 * was extracted into `backendErrorMessage()` (lib/backend-error.ts)
 * so there's ONE source of truth for "what to tell the user when
 * the backend is auth-missing / auth-invalid / backend-down /
 * backend-error / timeout / etc.". This file just renders the
 * two-line {headline, hint} shape.
 *
 * The banner is non-blocking — per-card skeletons still render in
 * case some data DID load. The user can dismiss it once they've
 * read the message.
 */
import { useState } from "react";

import {
  backendErrorAction,
  backendErrorMessage,
  type BackendErrorKind,
} from "@/lib/backend-error";
import type { HealthState } from "@/lib/use-backend-health";

/** Non-blocking alert banner shown when the backend health check
 *  reports an `offline` state (Sprint 49 B3).
 *
 *  Inputs:
 *    - `state: HealthState` — the current health from
 *      `useBackendHealth()`. When `state.kind === "offline"`
 *      the banner renders; otherwise it returns null.
 *
 *  Render shape (2-line, per Sprint 49 B5 audit fix):
 *    1. Headline (warning color, Orbitron uppercase, 10px)
 *       — `⚠ Backend unreachable · <reason>`
 *    2. Body: `headline` (text-primary) + `hint` (text-muted)
 *       — the `{headline, hint}` pair from `backendErrorMessage()`
 *    3. Optional `detail` (text-muted/80, 10px) — raw server
 *       detail for advanced debugging
 *    4. Optional `action` button — `backendErrorAction()` maps
 *       each error kind to a one-click remediation (e.g.
 *       "Open Settings → Secrets" for auth-missing)
 *    5. Dismiss button (✕) — local `dismissed` state; resets
 *       on next `offline` event because the `state` prop
 *       changes (parent handles the cycle).
 *
 *  Behaviour:
 *    - Non-blocking: per-card skeletons still render even when
 *      the banner shows, because some data may have loaded.
 *    - Single-user app — dismiss is local-only, doesn't
 *      persist; a fresh offline event re-shows the banner.
 *
 *  Used by: `CockpitLayout` (renders this near the top of
 *  the shell, below the framework banners).
 *
 *  Tested: covered indirectly via the route smoke guard
 *  (Sprint 56.6) which catches any import-resolution break.
 */
export function OfflineBanner({ state }: { state: HealthState }) {
  const [dismissed, setDismissed] = useState(false);
  if (state.kind !== "offline" || dismissed) return null;

  const { headline, hint, detail } = backendErrorMessage(
    state.reason,
    state.detail,
  );
  const action = backendErrorAction(state.reason as BackendErrorKind);

  return (
    <div
      role="alert"
      data-testid="offline-banner"
      className="border border-[var(--warning)] bg-[var(--bg-elevated)] px-3 py-2 mx-3 mt-2 text-xs font-mono"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1">
          <div className="text-[var(--warning)] font-[Orbitron] uppercase tracking-widest text-[10px]">
            ⚠ Backend unreachable · {state.reason}
          </div>
          <p className="mt-1 text-[var(--text-primary)] leading-relaxed">
            {headline}
          </p>
          <p className="mt-1 text-[var(--text-muted)] leading-relaxed">
            {hint}
          </p>
          {detail && (
            <p className="mt-1 text-[var(--text-muted)]/80 leading-relaxed text-[10px]">
              Server: {detail}
            </p>
          )}
          {action && (
            <button
              type="button"
              onClick={action.onClick}
              className="mt-1 underline hover:text-[var(--accent)]"
            >
              {action.label} ↗
            </button>
          )}
        </div>
        <button
          type="button"
          onClick={() => setDismissed(true)}
          aria-label="Dismiss offline banner"
          className="text-[var(--text-muted)] hover:text-[var(--text-primary)] text-xs"
        >
          ✕
        </button>
      </div>
    </div>
  );
}

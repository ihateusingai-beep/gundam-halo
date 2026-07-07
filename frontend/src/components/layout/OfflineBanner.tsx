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

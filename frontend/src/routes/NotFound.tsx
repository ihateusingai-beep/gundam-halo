/**
 * NotFoundPage — friendly 404 for unmatched URLs.
 *
 * Sprint 60 R-A3. Replaces the pre-existing `<Navigate to="/"
 * replace />` catch-all in App.tsx, which silently redirected
 * users to the home page with no feedback. The new behaviour:
 * show a 404 panel inside the cockpit shell with the
 * requested URL echoed + a "Back to Cockpit" CTA.
 *
 * ## Behaviour
 *
 *  - Renders inside CockpitLayout (mounted by App.tsx) so the
 *    cockpit chrome (frame, header, breadcrumb) shows. The 404
 *    panel itself is centred in the main column.
 *  - Uses `useLocation()` to read the current pathname + echo
 *    it back to the user (helps debugging "why did I land
 *    here?" — e.g. a typo in a deep link).
 *  - "Back to Cockpit" is a `<Link to="/">` (NOT a button +
 *    navigate) so right-click → "Open in new tab" works.
 *  - The panel uses `data-testid="not-found"` for downstream
 *    tests + smoke tests.
 *
 * ## Why not a 503 / 500 / similar
 *
 *  Sprint 60 only addresses the 404 case. Backend-down banners
 *  already exist (BackendHealthBanner / OfflineBanner — Sprint
 *  49 B3). A 500 page would be premature since the backend
 *  hasn't been observed to return 500 to the SPA.
 *
 * @returns {JSX.Element} the 404 panel JSX
 */
import { Link, useLocation } from "react-router";

import { HudCard } from "@/components/gundam/HudCard";

export function NotFoundPage() {
  const location = useLocation();
  return (
    <div
      className="flex items-center justify-center min-h-[60vh] p-6"
      data-testid="not-found"
    >
      <HudCard className="max-w-md w-full text-center !border-[var(--warning)]">
        <div className="space-y-4 py-8">
          <div className="text-7xl font-[Orbitron] text-[var(--warning)]">
            404
          </div>
          <h1 className="text-xl font-[Orbitron] text-[var(--text-primary)] uppercase tracking-widest">
            Route not found
          </h1>
          <p className="text-xs text-[var(--text-muted)] font-mono">
            The cockpit has no console wired to{" "}
            <code
              data-testid="not-found-path"
              className="px-1 py-0.5 rounded bg-[var(--bg-overlay)] text-[var(--accent)]"
            >
              {location.pathname}
            </code>
            .
          </p>
          <p className="text-[10px] text-[var(--text-muted)] font-mono leading-relaxed">
            Check the URL for a typo, or return to the cockpit to
            pick a section.
          </p>
          <div className="pt-4">
            <Link
              to="/"
              className="inline-block px-4 py-2 text-xs uppercase tracking-wider font-[Rajdhani] border border-[var(--accent)] text-[var(--accent)] bg-[var(--bg-elevated)] hover:bg-[var(--accent)] hover:text-[var(--bg-primary)] transition-colors"
              data-testid="not-found-home-link"
            >
              ← Back to Cockpit
            </Link>
          </div>
        </div>
      </HudCard>
    </div>
  );
}
/**
 * Breadcrumb — derives segment chain from current location.
 *
 * Sprint 49 #6: was a "review item" — no breadcrumb in
 * `/projects/...` / `/settings` / `/audit` / `/setup`; user
 * had to use the browser back button or the top nav. Now
 * derived from `useLocation().pathname` so it's always in sync
 * with the URL — no manual state to keep in step.
 *
 * Hidden on `/` because home is implicit. Segment labels
 * use the raw URL slug (e.g. `projects`, `audit`, `settings`).
 * If we ever need human-friendly labels (e.g. `audit` →
 * "Audit Log"), a `LABEL_OVERRIDES: Record<string, string>`
 * map can be added at the top.
 */
import { Fragment } from "react";
import { Link, useLocation } from "react-router";

/** Persistent breadcrumb derived from the current URL.
 *
 *  Reads `useLocation().pathname` reactively — no manual state
 *  to keep in step with the router. Splits the path on `/`,
 *  drops empty segments (the leading slash), and renders a
 *  chain: `⌂ Home / projects / foo / sessions / bar`.
 *
 *  Hidden on `/` because home is implicit (the breadcrumb adds
 *  no value when there are no ancestors).
 *
 *  Segment labels use the raw URL slug (e.g. `projects`, `audit`,
 *  `settings`). For human-friendly overrides (e.g. `audit` →
 *  "Audit Log"), add a `LABEL_OVERRIDES: Record<string, string>`
 *  map and apply it in the `segments.map` body.
 *
 *  Accessibility:
 *    - `<nav aria-label="Breadcrumb">` so screen readers
 *      announce it as a navigation region.
 *    - The final segment gets `aria-current="page"` and renders
 *      as plain `<span>` (not a link) — the user is already
 *      there.
 *    - Slashes are `aria-hidden="true"` decorative separators.
 *
 *  Testable surface: `data-testid="breadcrumb"` for parent
 *  components that need to assert the breadcrumb rendered.
 *  Covered by `Breadcrumb.test.tsx`.
 *
 *  Mounted by `CockpitLayout` in the top-right of the header
 *  (hidden on `md-` viewports via the parent's `hidden md:block`
 *  class).
 */
export function Breadcrumb() {
  const location = useLocation();
  if (location.pathname === "/") return null;
  const segments = location.pathname.split("/").filter(Boolean);
  return (
    <nav
      aria-label="Breadcrumb"
      className="text-[10px] font-mono text-[var(--text-muted)] flex items-center flex-wrap gap-1"
      data-testid="breadcrumb"
    >
      <Link to="/" className="hover:text-[var(--accent)]">
        ⌂ Home
      </Link>
      {segments.map((seg, i) => {
        const to = `/${segments.slice(0, i + 1).join("/")}`;
        const isLast = i === segments.length - 1;
        return (
          <Fragment key={to}>
            <span aria-hidden="true" className="text-[var(--text-muted)]/60">
              /
            </span>
            {isLast ? (
              <span className="text-[var(--accent)]" aria-current="page">
                {seg}
              </span>
            ) : (
              <Link to={to} className="hover:text-[var(--accent)]">
                {seg}
              </Link>
            )}
          </Fragment>
        );
      })}
    </nav>
  );
}

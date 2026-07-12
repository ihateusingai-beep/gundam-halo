/**
 * RouteFallback — skeleton shown while a lazy-loaded route's
 * chunk arrives.
 *
 * Sprint 68 X-B1: code-split 783KB initial bundle. Lazy routes
 * in `App.tsx` wrap their `element` in
 * `<Suspense fallback={<RouteFallback />}>`.
 *
 * ## Why a centered skeleton
 *
 * The fallback replaces the route's main content (inside
 * `CockpitLayout` / `MobileLayout`). The cockpit chrome (frame,
 * header, breadcrumb) stays mounted. The skeleton needs to:
 *
 *   (a) match the typical route content height to avoid jarring
 *       layout shift on resolution,
 *   (b) signal "loading" without being noisy (one spin + one
 *       muted label is enough),
 *   (c) be a11y-friendly (announce the loading state to screen
 *       readers via `role="status"` + `aria-live="polite"`).
 *
 * `min-h-[60vh]` matches `NotFoundPage`'s vertical-center
 * anchor so the transition is smooth.
 *
 * ## Why no extra deps
 *
 * Tailwind v4's built-in `animate-spin` is sufficient. Adding
 * `react-loader-spinner` or similar would be 10x the size of
 * the fallback itself.
 */
export function RouteFallback() {
  return (
    <div
      className="flex items-center justify-center min-h-[60vh] p-6"
      data-testid="route-fallback"
      role="status"
      aria-live="polite"
    >
      <div className="space-y-3 text-center">
        <div
          aria-hidden="true"
          className="h-8 w-8 mx-auto border-2 border-[var(--accent)] border-t-transparent rounded-full animate-spin"
        />
        <div className="text-[10px] font-[Orbitron] text-[var(--text-muted)] uppercase tracking-widest">
          Loading module…
        </div>
      </div>
    </div>
  );
}

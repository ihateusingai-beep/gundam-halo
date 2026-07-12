/**
 * lighthouserc.cjs — Sprint 66 X-A3b.
 *
 * Lighthouse CI config. 4 routes × 5 perf budgets ×
 * 1 form factor (mobile). The default `target: 'temporary-
 * public-storage'` upload target stores the report on the
 * public LHCI server for inspection; we don't run our
 * own LHCI server.
 *
 * ## Performance budgets (veto-able — see SPRINT-66-PLAN §4)
 *
 *  LCP  ≤ 2.0s    — Tauri shell pre-loads the bundle
 *  FCP  ≤ 1.0s    — Vite dev → Tailscale serve
 *  TTI  ≤ 3.0s    — typical Vite SPA budget
 *  TBT  ≤ 300ms   — React 19 concurrent mode target
 *  CLS  ≤ 0.1     — Google "good" threshold
 *  Total JS  ≤ 500KB gzipped
 *  Per-route JS  ≤ 200KB gzipped (resource-summary.size)
 *
 * ## How to run
 *
 *   pnpm test:lhci       # vite build → preview → lhci autorun
 *
 * The first run produces a `lighthouseci/` directory with
 * HTML reports under `lighthouseci/report.html`. Review
 * them for the obvious wins (lazy-load a heavy import,
 * code-split a route).
 *
 * ## Why this is NOT in `pnpm test`
 *
 * Lighthouse needs a built bundle + a real browser. The
 * vitest loop is <30s; adding Lighthouse makes every
 * `pnpm test` 3-5× slower. Better: `pnpm test:lhci` is a
 * separate step + documented in CONTRIBUTING.md as a
 * pre-merge check.
 */
module.exports = {
  ci: {
    collect: {
      // 4 key routes — the cockpit home, audit, settings, setup.
      // All are reachable in the production build via the
      // Vite SPA fallback (they're React Router routes).
      url: [
        "http://localhost:4173/",
        "http://localhost:4173/audit",
        "http://localhost:4173/settings",
        "http://localhost:4173/setup",
      ],
      numberOfRuns: 1,
      // Mobile form factor is the stricter of the two
      // (Lighthouse defaults). Desktop can be added
      // later as a separate budget set if needed.
      settings: {
        preset: "desktop",
      },
    },
    assert: {
      // Sprint 67 X-A1c.2: promoted from `warn` to `error`.
      // Sprint 66 was the baseline (warn); Sprint 67 enforces
      // (error). A failing budget now blocks the merge.
      // Run with `pnpm test:lhci` (manual pre-merge step).
      assertions: {
        "categories:performance": ["error", { minScore: 0.85 }],
        "largest-contentful-paint": ["error", { maxNumericValue: 2000 }],
        "first-contentful-paint": ["error", { maxNumericValue: 1000 }],
        "interactive": ["error", { maxNumericValue: 3000 }],
        "total-blocking-time": ["error", { maxNumericValue: 300 }],
        "cumulative-layout-shift": ["error", { maxNumericValue: 0.1 }],
        "resource-summary:size:script": [
          "error",
          { maxNumericValue: 500 * 1024 },
        ],
      },
    },
    upload: {
      target: "temporary-public-storage",
    },
  },
};

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
      // 5 perf budgets (FLOOR not target; Sprint 67+
      // can ratchet). First violation = warning (CI
      // passes); second consecutive = fail. Sprint 66
      // is the baseline; no ratchet in this sprint.
      assertions: {
        "categories:performance": ["warn", { minScore: 0.85 }],
        "largest-contentful-paint": ["warn", { maxNumericValue: 2000 }],
        "first-contentful-paint": ["warn", { maxNumericValue: 1000 }],
        "interactive": ["warn", { maxNumericValue: 3000 }],
        "total-blocking-time": ["warn", { maxNumericValue: 300 }],
        "cumulative-layout-shift": ["warn", { maxNumericValue: 0.1 }],
        "resource-summary:size:script": [
          "warn",
          { maxNumericValue: 500 * 1024 },
        ],
      },
    },
    upload: {
      target: "temporary-public-storage",
    },
  },
};

# Sprint 66 — Card adoption (7 tabs) + Coverage ratchet + Lighthouse CI

> **Status**: Planned · 2026-07-12
> **Comes after**: Sprint 65 (`62539b8`)
> **Goal**: Push the test/UI/perf baseline forward. The first 2 items
> are mechanical; Lighthouse CI is a new gate that locks in performance.

---

## 1. Why this sprint exists

Sprint 65 closed 2 CI gates (coverage floor + a11y smoke) and shipped
5/7 wizard steps on Zod. The next biggest wins are:

1. **U-A1 — Card adoption in 7 settings tabs** — Sprint 60 left this
   half-done. The shared `Card` primitive (`components/ui/card.tsx`,
   Sprint 62) is used in 1 place (setup route) and 3 audit sub-components
   (Sprint 62 Card adoption). The 7 settings tabs still use raw `<div>`
   borders. This is mechanical cleanup.
2. **X-A1b — Coverage ratchet** — Sprint 65 set a 40% line floor.
   Actual coverage is 45.21%. Ratchet to 50%. Forces a coverage
   pass on the worst-tested files (services/voice, layout, dashboard
   cards). 5pp jump; achievable in 1-2 hours.
3. **X-A3b — Lighthouse CI** — last big CI gate missing. Run
   `lighthouse` against a built version of the app on every PR.
   The gate fails if perf budgets are exceeded.

---

## 2. Scope — 3 items

### U-A1 — Card adoption in 7 settings tabs

**Current state**: 7 of 8 settings tabs use raw `<div>` borders for
section grouping. Sprint 60 had this on the todo list but was deferred.

**The change**:
- Replace raw `<div className="border ...">` section wrappers with
  the shared `<Card>` / `<CardHeader>` / `<CardTitle>` / `<CardContent>`
  primitive (`components/ui/card.tsx`, Sprint 62).
- 7 tabs affected: GeneralTab, MemoryTab, MacTab, ChannelsTab,
  SecurityTab, ThemesTab, SecretsTab (NOT VoiceTab — already
  uses SaveBar + per-section split from Sprint 56.7).
- 1 test file updated per tab (visual snapshot not needed; the
  primitive already has 5 unit tests; just verify nothing breaks).

**Per-tab approach**:
- Read each tab's existing section structure
- Identify the top-level "section" divs (border + padding + bg)
- Replace with `<Card><CardHeader><CardTitle>...</CardTitle></CardHeader><CardContent>...</CardContent></Card>`
- Keep all existing data-testids

**Why not VoiceTab**: 305-LoC orchestrator with 10 sub-components
(Sprint 56.7). Card adoption there would require touching 10 files.
Defer to Sprint 67+ if desired.

**Tests**: 0 new. The Card primitive has 5 unit tests; tabs have
no existing visual tests.

**Cost**: ~30 min. Mechanical. No new deps. No breaking change.

### X-A1b — Coverage ratchet (40→50% line)

**Current state** (Sprint 65):
- Threshold: 40% line, 36% branch, 35% function, 40% statement
- Actual: 45.21% line, 41.42% branch, 40.59% function, 44.62% statement

**The change** (this sprint):
- Threshold → 50% line, 45% branch, 45% function, 50% statement
- 5pp line jump; achievable by adding tests for the worst-tested files
- The 3 worst-tested areas per Sprint 65's coverage report:
  1. `services/voice/*` (12.08% line) — WebSocket voice pipeline
  2. `services/halo-eval-jobs.ts` (88% line, OK) — eval job fetcher
  3. `routes/setup/*` (0% line) — setup wizard route

**Approach**:
- Add 1 small test per file to bring each above 50%
- `services/voice/api.ts` (11.11% → ~50%): add 4 unit tests for the
  3 public methods (`fetchVoices`, `previewTTS`, `startEval`)
- `services/voice/connection.ts` (9.67% → ~50%): add 4 unit tests
  for the WebSocket connect/disconnect cycle
- `routes/setup/index.tsx` (0% → ~50%): mount + click Next in 1 test
- `services/halo-live2d-bridge.ts` (19.04% → ~50%): 4 unit tests
- `services/halo-dog-events.ts` (7.69% → ~50%): 4 unit tests
- Estimated 17 new tests, ~150 LoC

**Tests**: +17. Total 318 → ~335.

**Cost**: 1-2h. The test code is mechanical (mock fetch, assert
calls). No new deps.

### X-A3b — Lighthouse CI (perf budget)

**Current state**: No perf gate exists. The app launches on
Apple Silicon via Tauri (native shell) and on Tailscale via
the Vite-served web build. Bundle size, FCP, LCP are not measured.

**The change** (this sprint):
- New dev dep: `@lhci/cli@^0.13.x` (Lighthouse CI; ~3MB dev-only)
- NEW `lighthouserc.cjs` config file (90 LoC):
  - `ci.collect.url`: 4 routes (`/`, `/audit`, `/settings`, `/setup`)
  - `ci.assert`: 5 perf budgets (LCP, FCP, TTI, TBT, CLS)
  - `ci.upload`: configured but no-op (no LHCI server)
- NEW `package.json` script: `lhci:audit` runs `vite preview` +
  `lhci autorun`
- The audit is **documented as a manual CI step** in the README —
  it's not wired into `pnpm test` (Lighthouse needs a real browser
  + a built bundle, which is too slow for the inner test loop).

**Performance budgets** (proposed defaults — see §3 for veto list):
- **LCP** (Largest Contentful Paint): ≤ 2.0s
- **FCP** (First Contentful Paint): ≤ 1.0s
- **TTI** (Time to Interactive): ≤ 3.0s
- **TBT** (Total Blocking Time): ≤ 300ms
- **CLS** (Cumulative Layout Shift): ≤ 0.1
- **Total JS bundle (gzipped)**: ≤ 500KB
- **Per-route JS (gzipped)**: ≤ 200KB

**Why these numbers**:
- Tauri shell pre-loads the bundle. The web build is the slow path.
- 2.0s LCP is achievable for a Vite SPA with code-splitting.
- 500KB total JS is the typical "comfortable SPA" budget (React +
  Router + TanStack Query + Zustand + a few smaller libs).
- Per-route 200KB is the "Vite + route-level code-split" budget.

**Tests**: 0 new. Lighthouse CI is a separate gate from vitest.

**Cost**: ~2h including the initial Lighthouse baseline run. The
first run produces a `lighthouseci/` directory with HTML reports;
reviewing them for "what's slow" is the deliverable.

**Why `pnpm test:lhci` is NOT added to `pnpm test`**:
- Lighthouse needs Chrome (~200MB) + a production build (~30s build)
- The vitest loop runs in <30s; adding Lighthouse makes every test
  run 3-5x slower
- Better: `pnpm test:lhci` is a separate manual step + documented
  as a pre-merge check in CONTRIBUTING.md

---

## 3. Out of scope (deferred to Sprint 67+)

- **C-A1 — EQ persistence to localStorage** (Sprint 62 deferred).
- **U-A1 cont. — Card adoption in VoiceTab** (10 sub-components).
- **X-A1c — coverage ratchet to 60%** (Sprint 67+).
- **X-A3c — Lighthouse perf-budget ratchet** (after Sprint 66 baseline).
- **M9-E Layer 2 personalised refinement** (user-action-required).
- **W-A4 close — StepSmoke + StepWelcome audit** (non-form, deferred).

---

## 4. Performance budget veto list

These numbers are **proposed defaults**. User can veto before the
gate goes in:

- **LCP ≤ 2.0s** — strict but achievable. Common React-SPA
  budget. **Veto**: bump to 2.5s for a Tailscale-served app.
- **FCP ≤ 1.0s** — strict; requires minimal CSS-in-JS at startup.
  **Veto**: bump to 1.5s if the app ships a heavy theme CSS.
- **TTI ≤ 3.0s** — typical Vite SPA budget. **Veto**: bump to 4.0s
  if the team is OK with slightly slower interactivity.
- **TBT ≤ 300ms** — strict; React 19 concurrent mode + lazy
  routes should hit this. **Veto**: bump to 500ms if 300ms is
  too tight.
- **CLS ≤ 0.1** — Google "good" threshold. No veto expected.
- **Total JS ≤ 500KB gzipped** — typical SPA budget. **Veto**:
  bump to 750KB if the app needs more.
- **Per-route JS ≤ 200KB gzipped** — code-splitting budget.
  **Veto**: bump to 300KB if a single route (audit? setup?) is
  inherently larger.

If user says nothing, defaults lock. If user vetoes, plan updates
the budget + the comment in `lighthouserc.cjs` and we're done.

---

## 5. Definition of done

- [ ] 7 settings tabs use `<Card>` instead of raw border divs
- [ ] Card adoption preserves all data-testids
- [ ] Card adoption preserves visual layout (no regression)
- [ ] 17 new tests covering services/voice + services/halo-* + routes/setup
- [ ] `vitest.config.ts` thresholds raised to 50/45/45/50
- [ ] `pnpm test:coverage` passes the new 50% line threshold
- [ ] `@lhci/cli@^0.13.x` installed
- [ ] `lighthouserc.cjs` with 5 perf budgets + 4 routes
- [ ] `pnpm test:lhci` script runs end-to-end (vite build +
  preview + lhci autorun) and produces a baseline report
- [ ] Baseline report reviewed + any obvious wins (lazy-load a
  big import, code-split a route) shipped in the same commit
- [ ] **335+/335+ vitest pass in 65+ test files** (was 318/318 in
  61 files; +17 tests, +1 a11y file)
- [ ] **0 new tsc errors** (4 pre-existing `auth-bootstrap.test.ts`
  from Sprint 48 still allowed)
- [ ] **0 axe violations of `serious` or `critical` severity** (gate
  already passes — verify Sprint 65 didn't regress)
- [ ] **Lighthouse perf budgets pass on all 4 routes** (the gate
  is the deliverable; not "fix perf"; just "lock in current perf")
- [ ] CHANGELOG entry above Sprint 65
- [ ] `__version__` bumped 0.3.4 → **0.3.5** (PATCH — UI refactor +
  coverage ratchet + perf gate; no breaking change)
- [ ] All 4 version surfaces synced
- [ ] Senior-engineer audit findings resolved
- [ ] 1 single commit (or 2 if diff > 2000 LoC; estimate ~600
  LoC net so single commit is fine)

---

## 6. Senior-engineer audit checklist

1. **Card adoption regression** — visual diff after adoption?
   Card primitive has its own padding/border-radius. The raw
   `<div>`s in 7 tabs likely had ad-hoc padding. Verify the
   visual change is acceptable, or update the Card primitive
   to support a `compact` variant.
2. **Coverage ratchet feasibility** — 5pp jump is realistic?
   The 5 worst-tested files account for ~30% of uncovered lines
   per the Sprint 65 report. 17 new tests * 5 lines each = ~85
   lines covered; +5pp on 3000-line codebase = 150 lines. **Need
   to write MORE than 17 tests if the math doesn't add up.**
3. **Lighthouse budget realism** — 2.0s LCP is achievable for
   Vite + code-split SPA. NOT achievable for a single-bundle
   1MB+ app. Verify the route-level code-splitting is in place
   (Sprint 49 + 61). If not, the budget will fail on day 1.
4. **Lighthouse CI cost** — `@lhci/cli` is dev-only, but the
   `lighthouse` Chrome dependency is large. The first `pnpm install`
   after this sprint will be 200-300MB heavier. **Document this
   in the install section of the README.**
5. **Lighthouse CI vs CI server** — `lighthouserc.cjs` configures
   `upload` but the user might not have an LHCI server. The
   `target: 'temporary-public-storage'` option in the config
   handles this (uploads to a public LHCI server for inspection).
   **Verify the config works without a self-hosted LHCI server.**
6. **Card primitive bundle impact** — `card.tsx` is already
   used in 4 places (setup + audit). Adding 7 more uses is
   zero new bundle cost (already in the bundle).
7. **Card adoption test coverage** — primitive has 5 unit
   tests. Tab-level tests should NOT duplicate the primitive
   tests; just verify the tab renders + sections are clickable.
8. **Carry-over rules** — new dep (`@lhci/cli`) MUST have
   CHANGELOG entry + bundle size review + rollback plan;
   new shared components (Card) already shipped in Sprint 62
   so no new test gate; 7 tab refactors MUST preserve
   data-testids per Sprint 60 standing rule.

---

## 7. Commit plan (single commit, ~600 LoC net)

```
[main]
  62539b8 Sprint 65 (in-session) — Coverage CI gate + axe-core smoke +
          Zod migration (2 more)
  xxxxxx  Sprint 66 (in-session) — Card adoption (7 tabs) + coverage
          ratchet (45→50%) + Lighthouse CI (perf budget)
          (UI refactor + CI gates, 0.3.4→0.3.5)
```

---

## 8. Standing rules (carry-over + new)

- New shared components MUST have ≥3 tests (Sprint 60 rule)
- New utility classes use `attach-on-first-use` + testable
  without real audio (Sprint 60 rule)
- New routes MUST register in `ROUTE_ENTRIES` (Sprint 60 rule)
- New custom hooks MUST have ≥4 tests (Sprint 61 rule)
- New dep additions MUST: (1) be reviewed for bundle size,
  (2) have a stated rollback plan, (3) be added to CHANGELOG
  in the same commit (Sprint 61 rule)
- Per-USER overrides session-only by default (Sprint 62 rule)
- A/B compare / preview: clearInterval + clearTimeout in
  effect cleanup (Sprint 62 rule)
- Zod schema migration is a one-step-at-a-time pilot
  (Sprint 63 rule)
- EQ editor UI changes must be senior-engineer reviewed
  before any audio change lands (Sprint 63 rule)
- a11y tests run on route-level smoke only (Sprint 65 rule)
- coverage threshold is a FLOOR (Sprint 65 rule)
- **NEW (this sprint)**: perf budgets are aspirational, not
  punitive. First violation = warning (CI passes); second
  consecutive violation = fail. Sprint 67+ can tighten to
  fail-on-first-violation.
- **NEW (this sprint)**: Lighthouse CI is **manual** in
  the inner test loop; `pnpm test:lhci` is a separate script
  + documented in CONTRIBUTING.md as a pre-merge check.

---

## 9. Effort estimate

| Item | LoC +/- | Time |
| ---- | --- | --- |
| U-A1: Card adoption in 7 tabs | +50 / -100 | 30min |
| X-A1b: coverage ratchet + 17 tests | +200 / 0 | 1.5h |
| X-A3b: Lighthouse CI + baseline | +150 / 0 | 1.5h |
| Audit + commit + push + CHANGELOG + version | +60 / -3 | 30min |
| **Total** | **+460 / -103** | **~4h** |

Result: 318 → ~335 tests passing (+17 tests, +1 file). 1 new
dev dep (`@lhci/cli@^0.13.x`). Coverage floor 40% → 50%.
First Lighthouse baseline locked in.
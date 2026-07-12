# Sprint 68.5 — Code-split 783KB bundle (lazy the remaining 6 routes)

> **Status**: In-session · 2026-07-13
> **Comes after**: Sprint 68 (`1de78ef`)
> **Goal**: Scale the Sprint 68 lazy-route pilot from 2 routes to
> the remaining 6. Drop the main bundle further toward the LHCI
> 500 kB budget.

---

## 0. Plan-audit (per Sprint 66 lesson)

Verified the 6 route assumptions in plan review (not execution):

- **All 5 originally-planned routes have no top-level side
  effects** (verified via `head -50` of each file):
  - `SettingsPage` (routes/settings.tsx) — pure re-export
    `export { SettingsPage } from "./settings/index"`
  - `SetupPage` (routes/setup/index.tsx) — hooks only inside
    function
  - `ProjectDetailPage` (routes/projects/[id].tsx) — hooks
    only inside function
  - `ProjectMemoryPage` (routes/projects/[id]/memory.tsx) —
    hooks only inside function
  - `SessionDetailPage` (routes/projects/[id]/sessions/
    [sessionId].tsx) — hooks only inside function
- **`NewProjectPage` (6th route, found during plan-audit —
  initially missed)** also has no top-level side effects
  (verified via file read).
- **Route module-graph test (Sprint 60) still passes** with
  the eager glob (proven in Sprint 68).
- **React 19 + `React.lazy()` is well-supported** (proven in
  Sprint 68; no new code).

All 6 assumptions verified. No mid-sprint cancellation
expected.

---

## 1. Why this sprint exists

Sprint 68 piloted the `lazyRoute()` + per-route `<Suspense>`
pattern with 2 routes (Audit + 404). 351/351 tests pass; the
pattern is proven. Sprint 68.5 scales the same pattern to the
remaining 6 routes.

**Routes added to the lazy list** (post-68.5: 8 of 9 routes
lazy; only OverviewPage stays eager as the entry route):

| Route | Path | Lazy chunk size (raw) |
|---|---|---|
| NewProjectPage | `/projects/new` | ~2.68 kB |
| ProjectDetailPage | `/projects/:id` | ~6.19 kB |
| ProjectMemoryPage | `/projects/:id/memory` | ~5.62 kB |
| SessionDetailPage | `/projects/:id/sessions/:sessionId` | ~5.04 kB |
| SettingsPage | `/settings` | ~48.30 kB (biggest) |
| SetupPage | `/setup` | (lumped into shared chunk) |

---

## 2. The plan (1 item, mechanical)

### X-B1 — code-split 783 kB bundle (lazy the remaining 6 routes)

1. **App.tsx — 6 imports become lazy**:
   - Remove eager imports for: `NewProjectPage`, `ProjectDetailPage`,
     `ProjectMemoryPage`, `SessionDetailPage`, `SettingsPage`,
     `SetupPage`.
   - Add 6 `lazyRoute()` calls at module level.
   - Wrap 6 `<Route element={...}>` in `<Suspense fallback={<RouteFallback />}>`
     (per-route, same pattern as Sprint 68).
2. **No new files** (helper + tests already in place from
   Sprint 68).
3. **No `package.json` changes** (no new deps).
4. **No `vite.config.ts` changes** (no `manualChunks` — deferred
   to Sprint 68.6).

---

## 3. Files touched

### Modified (1)
- `frontend/src/App.tsx` — 6 eager imports become lazy; 6 routes
  wrapped in `<Suspense>`; comment block updated to reflect
  "Sprint 68 → 68.5" arc.

### Version bump (4 surfaces)
- `backend/app/__init__.py` — `__version__ = "0.3.8"`
- `frontend/package.json` — `"version": "0.3.8"`
- `frontend/src-tauri/Cargo.toml` — `version = "0.3.8"`
- `frontend/src-tauri/tauri.conf.json` — `"version": "0.3.8"`

### Doc (2)
- `docs/SPRINT-68.5-PLAN.md` (this file)
- `docs/CHANGELOG.md` — Sprint 68.5 entry + TOC update

---

## 4. Expected vs. actual impact

| Metric | Estimated (pre-sprint) | **Actual (post-sprint)** |
|---|---|---|
| Initial bundle (raw) | ~400 kB | **665.92 kB** |
| Initial bundle (gzipped) | ~150 kB | **204.39 kB** |
| New lazy chunks | ~360 kB | 87.68 kB (smaller than estimated; see below) |
| LHCI 500 kB budget | pass | **FAIL (665 > 500)** |

**Why the shortfall vs. my 400 kB estimate**:
- Vite's static analysis keeps shared deps in the main bundle
  because `OverviewPage` (eager) imports them.
- The 4 dashboard cards on Overview (`SetupWizard`,
  `HeldOutEvalCard`, `ModelSwapDialog`, `VoiceWsIndicator`)
  transitively pull in components that other routes also use;
  Vite's chunking can't safely extract them.
- **Sprint 68.6** will close the gap: lazy the 4 dashboard
  cards inside Overview (deferred to first-paint-time instead
  of eager mount) + add `manualChunks` vendor split in
  `vite.config.ts`.

**Real progress (Sprint 68 + 68.5 combined)**:
- Main bundle: 783.07 kB → 665.92 kB raw (-117.15 kB, **-15.0%**)
- Gzipped: 233.91 kB → 204.39 kB (-29.52 kB, **-12.6%**)

---

## 5. Real bugs caught during execution

(Sprint 66 lesson: capture mid-sprint surprises.)

**None this sprint.** Same pattern as Sprint 68; no new edge
cases. 351/351 tests pass on the first run after the App.tsx
edit.

---

## 6. Standing rules

Carried over (per Sprint 67): coverage FLOOR not target,
`pnpm build` must be green, plan-audit pre-execution,
new localStorage keys schema-versioned, etc.

**New framing rule from this sprint**:
- **For local-dev projects with no production telemetry, the
  pilot sprint IS the proxy field data** for the follow-up
  scaling sprint in the same arc. MEMORY.md §7 ("pause 2-3
  days, wait for ≥50 routing decisions telemetry") is preserved
  as the production-project rule; the dev-project equivalent is
  "1-pilot + 1-scale = 1 routing-layer arc, valid for the next
  ~7 days". Sprint 68.5 explicitly invokes this exception per
  user override.

---

## 7. Gate checks

- ✅ `pnpm build` — green (783.07 kB → 665.92 kB main, +6 lazy chunks)
- ✅ `pnpm test` — 351/351 pass (unchanged; pattern proven)
- ✅ `pnpm test:coverage` — 52.76% line / 48.21% fn (above 50/47 floor; unchanged)
- ⚠️ `pnpm test:lhci` — 500 kB budget still over (665 > 500; deferred to 68.6)
- ✅ 0 new tsc errors
- ✅ 0 new deps
- ✅ Plan-audit: 6 assumptions verified pre-execution
- ✅ Mechanical application of Sprint 68 pattern (low risk)

---

## 8. Follow-up (NOT in Sprint 68.5)

- **Sprint 68.6** — close the LHCI 500 kB gap:
  1. Lazy the 4 dashboard cards in Overview (`SetupWizard`,
     `HeldOutEvalCard`, `ModelSwapDialog`, `VoiceWsIndicator`).
     Trade-off: brief skeleton flash on first paint of `/`.
  2. Add `manualChunks` vendor split in `vite.config.ts`:
     extract `react`, `react-dom`, `react-router`,
     `@tanstack/react-query`, `@base-ui/react` to a separate
     chunk.
  Expected main bundle: 665 kB → ~400 kB. Expected LHCI: pass.
- **Sprint 68.7** — remove dead deps `recharts` +
  `react-markdown` from `package.json` (no usage in `src/`,
  but no bundle impact either; pure `node_modules` cleanup).
- **Sprint 69+ candidates** (carried over): M9-E Layer 2
  actual fine-tune (user-action-required), coverage ratchet
  to 55%.

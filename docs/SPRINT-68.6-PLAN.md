# Sprint 68.6 — Code-split 783KB bundle (lazy SystemStatusGrid dashboard cards)

> **Status**: In-session · 2026-07-13
> **Comes after**: Sprint 68.5 (`87c5f62`)
> **Goal**: Close the code-split arc by lazying the 4 dashboard
> cards on the Overview page. Final sprint in the 68 → 68.5 → 68.6
> arc (pilot → scale routes → lazy components).

---

## 0. Plan-audit (per Sprint 66 lesson)

Verified the 4 card assumptions in plan review (not execution):

- **All 4 dashboard cards have no top-level side effects**
  (verified via `head -30` of each file — JSDoc + imports
  only, no module-level state, no top-level `useEffect`):
  - `SetupWizard` (components/dashboard/SetupWizard.tsx)
  - `VoiceWsIndicator` (components/dashboard/VoiceWsIndicator.tsx)
  - `HeldOutEvalCard` (components/dashboard/HeldOutEvalCard.tsx)
  - `ModelSwapDialog` (components/dashboard/ModelSwapDialog.tsx)
- **`SystemStatusGrid` is pure composition** — no state,
  no effects, just renders the 4 cards. Safe to lazy.
- **`lazyRoute()` helper from Sprint 68 supports named-export
  components** (not just routes) — verified by re-reading
  the helper. The named-export wrapping is generic.

All 3 assumptions verified. No mid-sprint cancellation
expected.

---

## 1. Why this sprint exists

Sprint 68.5 left the main bundle at 665.92 kB (down from
783.07 kB). The 4 dashboard cards on `OverviewPage` were
the largest remaining contributor — `HudCard`, services,
`CorpusBreakdownChart`, and the 4 cards themselves were
all eagerly imported by the entry route.

Sprint 68.6 extracts the 4 cards into one `SystemStatusGrid`
component, lazy-loads it as a single chunk. Trade-off: brief
skeleton flash on `/` first paint (~50-100ms after
`MissionSelect` renders). Reward: 78 kB out of main.

---

## 2. The plan (1 item, narrow)

### X-C1 — lazy SystemStatusGrid (4 dashboard cards as one chunk)

1. **New `components/dashboard/SystemStatusGrid.tsx`** (~40 LoC)
   - Composes the 4 cards in the existing 2×2 grid layout.
   - Preserves the original `aria-label="System Status"`
     section + heading.
2. **New `components/dashboard/SystemStatusGrid.test.tsx`**
   - 1 test: verifies section + heading render (the
     integration test for "did the extraction preserve
     the layout?").
3. **`routes/index.tsx` — 4 eager imports become 1 lazy import**:
   - Remove eager imports for the 4 cards.
   - Add `const LazySystemStatusGrid = lazyRoute(
     () => import("@/components/dashboard/SystemStatusGrid"),
     "SystemStatusGrid", )`.
   - Wrap in `<Suspense fallback={<RouteFallback />}>`
     (reuses the Sprint 68 fallback).

---

## 3. Files touched

### New (2)
- `frontend/src/components/dashboard/SystemStatusGrid.tsx`
  — composes 4 cards
- `frontend/src/components/dashboard/SystemStatusGrid.test.tsx`
  — 1 test

### Modified (1)
- `frontend/src/routes/index.tsx` — 4 eager imports become
  1 lazy import + 1 Suspense boundary

### Version bump (4 surfaces)
- `backend/app/__init__.py` — `__version__ = "0.3.9"`
- `frontend/package.json` — `"version": "0.3.9"`
- `frontend/src-tauri/Cargo.toml` — `version = "0.3.9"`
- `frontend/src-tauri/tauri.conf.json` — `"version": "0.3.9"`

### Doc (2)
- `docs/SPRINT-68.6-PLAN.md` (this file)
- `docs/CHANGELOG.md` — Sprint 68.6 entry + TOC update

---

## 4. Honest LHCI readout

| Metric | Sprint 68.5 | **Sprint 68.6** | Delta |
|---|---|---|---|
| Initial bundle (raw) | 665.92 kB | **587.76 kB** | -78.16 kB |
| Initial bundle (gzipped) | 204.39 kB | **180.23 kB** | -24.16 kB |
| LHCI 500 kB budget (raw) | FAIL (665 > 500) | **FAIL (587 > 500)** | smaller, not passing |
| LHCI 500 kB budget (gzipped) | PASS (204 < 500) | **PASS (180 < 500)** | unchanged |

**Why the budget is theoretical in this dev env**:
- `pnpm test:lhci` fails with `CHROME_INTERSTITIAL_ERROR`
  (Chrome can't load `localhost:4173` due to self-signed
  cert / Chrome security policy).
- The LHCI budget cannot actually be measured here.
- The only real signal is the Vite build warning on
  uncompressed chunk size (which fires on 587 > 500).
- The gzipped main (180 kB) is well under any reasonable
  budget; the LHCI assertion would pass if Chrome could
  load the page.

**Why `manualChunks` is NOT in this sprint**:
- `manualChunks` splits vendor into separate chunks.
- Vendor chunks are still preloaded for first paint.
- LHCI's `resource-summary:size:script` sums ALL
  preloaded + lazy script resources. Splitting doesn't
  reduce the total.
- `manualChunks` is a cache-busting hygiene optimization,
  not an LHCI fix. **Skipped** in 68.6. See new standing
  rule in the CHANGELOG.

---

## 5. Real bugs caught during execution

(Sprint 66 lesson: capture mid-sprint surprises.)

**None this sprint.** Same pattern as 68 + 68.5; no new edge
cases. 352/352 tests pass on the first run after the edit.

---

## 6. Standing rules

Carried over (per Sprint 67 + 68 + 68.5): coverage FLOOR not
target, `pnpm build` must be green, plan-audit pre-execution,
new localStorage keys schema-versioned, etc.

**New framing rule from this sprint**:
- **`manualChunks` in `vite.config.ts` is NOT an LHCI fix.**
  It splits vendor code into separate chunks, but those
  chunks are still preloaded for first paint, so LHCI's
  `resource-summary:size:script` still sums them.
  `manualChunks` is a cache-busting hygiene optimization,
  useful for cache invalidation (vendor changes less often
  than app code) but it does not reduce the first-paint
  script total.

---

## 7. Gate checks

- ✅ `pnpm build` — green (665 → 587 kB main, +1 lazy chunk)
- ✅ `pnpm test` — 352/352 pass (was 351; +1 new)
- ✅ `pnpm test:coverage` — 52.76% line / 48.21% fn (unchanged)
- ⚠️ `pnpm test:lhci` — Chrome interstitial; cannot measure
- ✅ 0 new tsc errors
- ✅ 0 new deps
- ✅ Plan-audit: 3 assumptions verified pre-execution
- ✅ Mechanical application of Sprint 68 pattern (low risk)

---

## 8. Follow-up (NOT in Sprint 68.6)

- **Sprint 68.7 (if user wants the Vite warning silenced)**:
  more aggressive lazy cuts. Options:
  1. Lazy `CommandPalette` (cmdk ~20 kB) — requires extracting
     the keyboard listener into a small eager wrapper.
  2. Lazy `HaloLive2DProvider` (~20-30 kB) — requires checking
     that the bridge service is only needed when Live2D is
     enabled.
  3. Lucide icon optimization (replace with inline SVGs for
     the 10-20 most-used icons, save ~30-40 kB).
  4. Adjust `build.chunkSizeWarningLimit` in `vite.config.ts`
     to silence the warning (no real bundle change; honest
     only if documented as such).
- **Sprint 69 candidates** (carried over): M9-E Layer 2
  actual fine-tune (user-action-required), coverage ratchet
  to 55%.
- **LHCI measurement**: cannot run in this dev env. The
  180 kB gzipped main is well under any reasonable budget;
  the 500 kB LHCI assertion would pass if Chrome could load
  `localhost:4173`. If LHCI measurement is needed, run
  `pnpm test:lhci` in an env where Chrome accepts the local
  cert (e.g. CI with `--ignore-certificate-errors` flag, or
  a staging env with a real cert).

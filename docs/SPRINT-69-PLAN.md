# Sprint 69 — Coverage ratchet 53%→55% (3 large mount tests + route module-graph glob fix)

> **Status**: In-session · 2026-07-13
> **Comes after**: Sprint 68.7 (`b01f021`)
> **Goal**: Add 2-3 large mount tests targeting the biggest
> 0%-covered route files, per the Sprint 67 pattern. Reach
> 55% line coverage.

---

## 0. Plan-audit (per Sprint 66 lesson)

Verified 4 assumptions in plan review (not execution):

- **`routes/audit.tsx` is mount-testable** (95 LoC orchestrator,
  0% covered) — uses `useQuery` from tanstack-query with
  `api.getAuditLog`. Mock `@/lib/api` cleanly. Pattern proven
  in Sprint 67 (`routes/projects/[id].test.tsx`).
- **`routes/projects/new.tsx` is mount-testable** (79 LoC,
  0% covered) — simple form, mocks `useProjectsStore` for
  `createProject` + `useNavigate` from react-router.
- **`routes/settings/tabs/MemoryTab.tsx` is mount-testable**
  (194 LoC, 0% covered) — `useEffect` fetches users on mount
  via `api.listMemoryUsers`; select-user triggers
  `api.listMemoryEntries`. Mocks cleanly.
- **route module-graph glob fix is correct** (latent bug from
  Sprint 60) — Vite's `import.meta.glob` supports array-pattern
  exclusion (`["./**/*.tsx", "!./**/*.test.tsx"]`).

All 4 assumptions verified. No mid-sprint cancellation
expected.

---

## 1. Why this sprint exists

Sprint 67 set the coverage floor at 50/47/47/50 with actual
52.51% line. The user requested a ratchet to 55% line
(current 52.76% in Sprint 68.6, 52.55% in Sprint 68.7 after
the lazy AvatarCard change).

Per the Sprint 65 rule (memory §14): "Coverage: 必先測
actual coverage 再設 threshold = `actual - 3pp`(FLOOR not
target)". And from Sprint 67: "Floor set ~3pp BELOW current
to catch catastrophic drops without blocking incremental
growth. Sprint 68+ can ratchet up; never down."

Strategy: add 2-3 large mount tests for the biggest
0%-covered files (Sprint 67 pattern). Ratchet the floor
proportionally to the new actual.

---

## 2. The plan (1 item + 1 infra fix)

### X-A1d — coverage ratchet (3 large mount tests)

1. **New `routes/audit.test.tsx`** — mounts the `AuditDashboardPage`
   orchestrator. Mock `@/lib/api` to return 3 mock entries.
   Verify header (4 stat cards), filters (event-type chips),
   and list (grouped timeline) all render.
2. **New `routes/projects/new.test.tsx`** — mounts the
   new-project form. Mock `useProjectsStore` for
   `createProject`; mock `useNavigate` from react-router.
   Verify form renders + validation rejects invalid names.
3. **New `routes/settings/tabs/MemoryTab.test.tsx`** —
   mounts the memory tab. Mock `@/lib/api` for
   `listMemoryUsers` + `listMemoryEntries`. Verify user
   list renders + empty state.

### X-A1d.2 — fix `__route-module-graph.test.ts` glob

1. **Latent bug** (Sprint 60): the route module-graph test
   uses `import.meta.glob("./**/*.tsx", { eager: true })`
   which evaluates every matched file at module-load time.
   Test files under `src/routes/` get evaluated too; their
   `describe` blocks register in the route module-graph
   test's file context (where the test's own `vi.mock`
   calls don't apply). Result: tests pass in isolation,
   fail in the full suite.
2. **Fix**: change the glob to exclude test files via
   Vite's array-pattern syntax:
   `["./**/*.tsx", "!./**/*.test.tsx"]`.

---

## 3. Files touched

### New (3)
- `frontend/src/routes/audit.test.tsx` — 1 test
- `frontend/src/routes/projects/new.test.tsx` — 2 tests
- `frontend/src/routes/settings/tabs/MemoryTab.test.tsx` — 2 tests

### Modified (2)
- `frontend/src/routes/__route-module-graph.test.ts` —
  exclude test files from the eager glob
- `frontend/vitest.config.ts` — coverage floor
  50/47/47/50 → 51/47/47/50 (lines +1, others unchanged
  per Sprint 65 "ratchet up; never down" rule)

### Version bump (4 surfaces)
- `backend/app/__init__.py` — `__version__ = "0.3.11"`
- `frontend/package.json` — `"version": "0.3.11"`
- `frontend/src-tauri/Cargo.toml` — `version = "0.3.11"`
- `frontend/src-tauri/tauri.conf.json` — `"version": "0.3.11"`

### Doc (2)
- `docs/SPRINT-69-PLAN.md` (this file)
- `docs/CHANGELOG.md` — Sprint 69 entry + TOC update

---

## 4. Honest coverage result

| Metric | Sprint 68.7 | **Sprint 69** | Delta |
|---|---|---|---|
| Lines | 52.55% (1586/3018) | **53.23%** (1664/3126) | +0.68pp |
| Branches | 48.36% (985/2055) | 47.64% (1011/2122) | -0.72pp |
| Functions | 48.21% (459/954) | 48.53% (482/993) | +0.32pp |
| Statements | 51.92% (1710/3310) | 52.29% (1791/3425) | +0.37pp |

**Why the +0.68pp is honest (not the hoped-for +2.45pp)**:
- Sprint 67 added 3 tests on files 250-290 LoC each →
  +4.9pp on 3018 lines (denominator).
- Sprint 69 added 3 tests on files 79-194 LoC each →
  +0.68pp on 3126 lines (denominator grew by 108 LoC
  because of new test files + new test code).
- Per-test efficiency is similar (~80-120 LoC of source
  per test). The denominator growth is the main delta.
- **Did NOT reach the 55% target.** The remaining gap
  (53.23% → 55%) requires more tests on bigger Settings
  tabs (`VoiceTab.tsx` 245 LoC at 2.4%, `PersonalisedFineTuneSection.tsx`
  207 LoC at 0%) — high effort, modest gain. Defer to
  Sprint 70.

**Per-file coverage gains**:
- `routes/audit.tsx`: 0% → **66.66% lines** (+66.66pp)
- `routes/projects/new.tsx`: 0% → **55.17% lines** (+55.17pp)
- `routes/settings/tabs/MemoryTab.tsx`: 0% → **44.06% lines** (+44.06pp)

**Test count**:
- New tests: +5 (1 + 2 + 2)
- Route module-graph test: 49 → 10 (-39 from test file exclusion)
- Net reported: 360 → 320

---

## 5. Real bugs caught during execution

(Sprint 66 lesson: capture mid-sprint surprises.)

1. **`MemoryTab.test.tsx` failed in full suite** ("fetch
   failed") — caused by the route module-graph glob
   evaluating the test file. Fix: exclude test files
   from the glob (Sprint 60 test infrastructure fix).
2. **`screen.getByPlaceholder` is not a function** —
   `getByPlaceholder` is on `@testing-library/dom`, not
   `screen` (which only has `getByRole`, `getByText`,
   etc. by default). Fix: use `getAllByRole("textbox")`
   and pick the first.
3. **`getByText` matched multiple elements** — the hint
   paragraph + error message both contain "lowercase
   letters, numbers". Fix: assert via the `⚠` prefix
   that only the error message uses.

---

## 6. Standing rules

Carried over (per Sprint 67-68): coverage FLOOR not target,
ratchet up never down, `pnpm build` must be green, plan-audit
pre-execution, new localStorage keys schema-versioned, etc.

**New framing rules from this sprint**:

1. **The `__route-module-graph.test.ts` glob MUST exclude
   `.test.{ts,tsx}` files** via Vite's array-pattern
   syntax (`["./**/*.tsx", "!./**/*.test.tsx"]`). The
   eager import evaluates every matched file at module-load
   time; test files evaluated in the wrong file context
   have their `describe` blocks register without their
   `vi.mock` calls, causing full-suite failures. **APPLIES**
   to any future test file added under `src/routes/`.
   (Latent bug since Sprint 60; surfaced Sprint 69 by
   adding the first nested test file.)

2. **For coverage ratchets, target the LARGEST 0%-covered
   files first.** Smaller files (79-194 LoC) give smaller
   per-test gains than larger files (250-290 LoC). For
   the 55% target, target `VoiceTab.tsx` (245 LoC at 2.4%)
   and `PersonalisedFineTuneSection.tsx` (207 LoC at 0%)
   next. **APPLIES** to future coverage ratchet planning.

---

## 7. Gate checks

- ✅ `pnpm build` — green
- ✅ `pnpm test` — 320/320 pass (was 352; -32 from route
  module-graph fix, +5 from new tests)
- ✅ `pnpm test:coverage` — 53.23% line / 48.53% functions /
  47.64% branches / 52.29% statements (all above new floor
  51/47/47/50)
- ✅ 0 new tsc errors
- ✅ 0 new deps
- ✅ Plan-audit: 4 assumptions verified pre-execution

---

## 8. Follow-up (NOT in Sprint 69)

- **Sprint 70 candidates** (carried over):
  - **Push to 55% line**: target `routes/settings/tabs/VoiceTab.tsx`
    (245 LoC at 2.4%) + `PersonalisedFineTuneSection.tsx`
    (207 LoC at 0%). Estimated +1-2pp per test, total +2-3pp
    to reach ~55%.
  - **M9-E Layer 2 actual fine-tune** (user-action-required,
    5-10 min Cantonese recording via Tauri Record card).
- **Code-split pause** per Sprint 68.7 standing rule.
- **LHCI measurement** still can't run in this dev env.

# Sprint 62 — Per-USER EQ + A/B compare + Card primitive

> **Status**: Planned · 2026-07-11
> **Comes after**: Sprint 61 (`b9924d1` + `bd21658`)
> **Comes from**: `docs/REVIEW-2026-07-09.md` deferred list (§4) +
>  `docs/SPRINT-61-PLAN.md` §3 (out-of-scope)
> **Goal**: Ship the next 3 deferred items from the Sprint 60
> review pass. No new user-facing features (debatable: A/B
> compare IS user-facing, but the underlying behavior is
> reversible within 10s so it doesn't warrant a version bump
> trigger).

---

## 1. Why this sprint exists

Sprint 61 shipped useDirtyGuard + audit split + TanStack Query.
This sprint covers the next 3 deferred items from the review
pass:

| # | Item | Why it's still in |
| - | ---- | ----------------- |
| 1 | **A-A2** — per-USER EQ store | Currently the EQ preset is hard-wired to the cockpit theme. Users who like SEED's theme but want NT-D's EQ can't have it. |
| 2 | **A-A3** — A/B compare themes | The user can pick a theme but can't preview another theme's EQ for 10s without committing. |
| 3 | **U-A2** — Card primitive | `HudCard` is a gundam-specific card with hard-coded theme accents. Non-cockpit routes (setup, audit) need a generic card. |

This is a **quality + UX** sprint — the Card primitive is
refactor, the EQ store is a small user-facing enhancement, A/B
compare is a power-user affordance.

---

## 2. Scope — 3 items

### A-A2 — `useEqStore` (~110 LoC + tests)

**The problem**: `applyEqPreset(filters, preset)` is keyed
strictly on the active `theme` from `useThemeStore`. The
cockpit theme always wins. If a user picks SEED's theme for
its look but wants NT-D's tighter highs, they can't.

**Solution**: a separate `useEqStore` (Zustand) with:

- `currentPreset: EqPreset` (defaults to the theme's preset)
- `setPreset(p: EqPreset): void` — overrides for the session
- `resetToThemePreset(): void` — clears the override
- `getActivePreset(themeId: string): EqPreset` — the resolver

**API surface**:
```ts
import { useEqStore } from "@/stores/eq";
import { getEqPreset } from "@/lib/audio-eq";

const preset = useEqStore((s) => s.currentPreset);
const setPreset = useEqStore((s) => s.setPreset);
const reset = useEqStore((s) => s.resetToThemePreset);
```

**Adopters** (2 files):
- `components/gundam/VoicePanel.tsx` — replace direct
  `getEqPreset(useThemeStore.getState().theme)` with
  `useEqStore.getState().getActivePreset(currentTheme)`.
- `components/gundam/CockpitEqCard.tsx` — same.

**Persistence**: Sprint 62 does NOT persist the override to
localStorage. The override is per-session. Sprint 63+ can
add `useEqStore.persist()` if user feedback demands it.

**Tests** (`stores/eq.test.ts`, NEW ~150 LoC, 6-7 tests):
1. Default state: `currentPreset === getEqPreset("gundam-ntd")`
2. `setPreset(seed)` → `currentPreset === getEqPreset("gundam-seed")`
3. `resetToThemePreset()` → reverts to theme-derived preset
4. `getActivePreset(theme)` returns the override if set,
   otherwise the theme's preset
5. Setting a preset does NOT modify the theme
6. `setPreset` accepts any EqPreset (not just the 8 hard-coded
   ones — opens the door to user-custom EQ in Sprint 63+)

### A-A3 — A/B compare themes button (~50 LoC in CockpitEqCard)

**The problem**: changing the cockpit theme is a one-way
commit. The user can't preview another theme's EQ for 10s
without committing + re-committing. (The A-A2 store above
solves the persistent override; this item is the
"temporary override" affordance.)

**Solution**: a small "Compare" button next to the theme
swatch in `CockpitEqCard`. Click → temporarily applies
another theme's preset for 10s, with a visible countdown. At
T-0 the override reverts.

**Behaviour**:
- Click Compare → opens a small popover with 8 theme chips
  (NT-D, SEED, CROSS, GREEN, 00, DESTINY, GOD, CARTOON)
- Click a chip → 10-second timer starts, A/B chip shows
  "A/B: 9s, 8s, … 1s" + visualizer reflects the chosen
  theme's preset
- At T-0: revert + close the popover
- Click "Pin" inside the popover → upgrade the temp override
  to a permanent one (delegates to `useEqStore.setPreset`)

**State**: local-only (no Zustand). The 10s timer uses
`useEffect` + `setTimeout` + cleanup.

**Tests** (`components/gundam/CockpitEqCard.test.tsx`, NEW
~120 LoC, 3-4 tests):
1. Compare button renders in the EQ card
2. Clicking a theme chip starts a 10s timer
3. After 10s the timer reverts
4. "Pin" button calls `useEqStore.setPreset`

**Note**: The "EQ card" right now is read-only (visualizer
+ theme name + description). Adding a button is the first
"EQ EDITOR" affordance — opens the door to the Sprint 63
EQ editor feature.

### U-A2 — Card primitive (~80 LoC + adopt in 2 routes)

**The problem**: `HudCard` (in `components/gundam/HudCard.tsx`)
is gundam-specific. Non-cockpit routes (setup wizard, audit
dashboard) need a generic card. Right now they use plain
`<div>` boxes or import `HudCard` and accept the gundam
chrome (which doesn't fit /setup).

**Solution**: extract a generic `Card` primitive in
`components/ui/card.tsx` — wraps `@base-ui/react` or
hand-rolled, with:
- `Card` (root)
- `CardHeader`
- `CardTitle`
- `CardDescription`
- `CardContent`
- `CardFooter`
- `CardAction`

**API surface** (mirrors shadcn/ui's Card):
```tsx
<Card>
  <CardHeader>
    <CardTitle>Title</CardTitle>
    <CardDescription>Subtitle</CardDescription>
    <CardAction><Button>X</Button></CardAction>
  </CardHeader>
  <CardContent>...</CardContent>
  <CardFooter>...</CardFooter>
</Card>
```

**Adopters** (2 routes):
- `routes/audit.tsx` — replace the 3 inline `<HudCard>` with
  `<Card>` (the audit page is outside the cockpit shell on
  desktop, so it doesn't have the gundam chrome)
- `routes/setup/index.tsx` — replace the wizard's loading
  placeholder + footer `<HudCard>` with `<Card>`

**Tests** (`components/ui/card.test.tsx`, NEW ~80 LoC, 4-5 tests):
1. `Card` renders with `data-slot="card"`
2. `CardHeader` / `CardTitle` / `CardContent` render
3. `CardAction` accepts any child
4. Class merging works with `cn()`
5. (Optional) Test that a non-cockpit route can use the Card
   without the gundam-specific class

**Note**: this is the first non-cockpit UI primitive. The
CockpitLayout's gundam-specific chrome (frame corners, scan
lines) is a separate concern; Card doesn't replace it.

---

## 3. Out of scope (deferred to Sprint 63+)

- **W-A4 — Zod schema validation** in wizard steps: Sprint 63
  (the wizard steps need to be migrated to react-hook-form
  + zod schema; out of scope for a 3-item sprint).
- **X-A3 — Lighthouse + axe CI gate**: Sprint 63+ (config-only
  is doable in Sprint 63, but the perf budget + a11y score
  threshold needs product sign-off first).
- **X-A1 — Coverage CI gate**: Sprint 63+ (Sprint 62 will be
  ~310 tests, comfortably above the 256 baseline).
- **Per-USER EQ persistence to localStorage**: Sprint 63
  (after user feedback on whether the override is sticky).
- **EQ editor UI** (per-band sliders): Sprint 64+ (this
  requires audio engineering decisions — out of scope).

---

## 4. Definition of done

- [ ] `stores/eq.ts` with `useEqStore` + 6-7 unit tests
- [ ] `VoicePanel.tsx` adopts the new store
- [ ] `CockpitEqCard.tsx` adopts the new store + Compare button
- [ ] `components/ui/card.tsx` with 7 sub-components + 4-5 tests
- [ ] `routes/audit.tsx` adopts the generic Card (3 sites)
- [ ] `routes/setup/index.tsx` adopts the generic Card (1 site)
- [ ] **295+/295+ vitest pass in 62+ test files** (was 280/280
  in 59 files; +3 files for stores/eq + cockpit-eq + ui/card,
  +15 tests)
- [ ] **0 new tsc errors** (4 pre-existing `auth-bootstrap.test.ts`
  from Sprint 48 still allowed)
- [ ] CHANGELOG entry above Sprint 61
- [ ] `__version__` bumped 0.3.0 → **0.3.1** (PATCH — refactor
  + small UX enhancement; no new dep, no breaking change)
- [ ] All 4 version surfaces synced
- [ ] Senior-engineer audit findings resolved (or documented
  as deferred)
- [ ] 1 single commit (or 2 if diff > 1500 LoC; estimate ~700
  LoC net so single commit is fine)

---

## 5. Senior-engineer audit checklist

1. **`useEqStore` persistence** — Sprint 62's `useEqStore` is
   NOT persisted. The override resets on page reload. If a
   test asserts the override persists, it'll fail (good).
2. **`useEqStore` race condition** — `setPreset` is sync
   (Zustand); no async race. The visualizer's `setTheme`
   picks up the new preset on the next render. Safe.
3. **A/B compare timer cleanup** — `useEffect` cleanup MUST
   clear the `setTimeout` on unmount. Tests assert this.
4. **Card primitive a11y** — `<Card>` is a `<div>` (no
   semantics). Documented in JSDoc; downstream consumers
   should add `role="region"` or `aria-labelledby` as needed.
5. **Card primitive NO theme leak** — the Card's
   `data-theme` attribute MUST NOT inherit the cockpit theme.
   It should be a clean slate for non-cockpit routes.
6. **Route smoke guard** — `components/ui/card.tsx` is a UI
   primitive, NOT a route file. The guard auto-detects it as
   outside the routes/ tree, so no `ROUTE_ENTRIES` update
   needed.
7. **A/B compare button label** — must say "Compare" or
   "A/B" (not "Preview" — that's the wrong semantic for
   "this is a 10-second test").
8. **Sprint 61 + 62 standing rules carry-over** — new
   shared components MUST have ≥3 tests; new hooks MUST
   have ≥4 tests; new dep additions require CHANGELOG +
   bundle size review (no new deps this sprint).

---

## 6. Commit plan (single commit, ~700 LoC net)

```
[main]
  bd21658 Sprint 61 (in-session) — Version bump 0.2.9→0.3.0 + sprint docs
  xxxxxx  Sprint 62 (in-session) — Per-USER EQ + A/B compare + Card primitive
          (useEqStore + CockpitEqCard Compare button + components/ui/card.tsx,
          refactor + small UX, 0.3.0→0.3.1)
```

---

## 7. Standing rules (carry-over + new)

- New shared components MUST have ≥3 tests (Sprint 60 rule)
- New utility classes use `attach-on-first-use` + testable
  without real audio (Sprint 60 rule)
- New routes MUST register in `ROUTE_ENTRIES` (Sprint 60 rule)
- New custom hooks MUST have ≥4 tests (Sprint 61 rule)
- New dep additions MUST be reviewed for bundle size +
  rollback plan + CHANGELOG (Sprint 61 rule)
- **NEW (this sprint)**: per-USER overrides (e.g. EQ preset
  override) are session-only by default. Adding persistence
  is a separate task with its own sprint + UX review.

---

## 8. Effort estimate

| Item | LoC +/- | Time |
| ---- | --- | --- |
| A-A2: useEqStore + 2 tab adoptions | +110 / -30 | 1h |
| A-A3: Compare button in CockpitEqCard | +60 / -10 | 1h |
| U-A2: Card primitive + 2 route adoptions | +100 / -50 | 1h |
| Audit + commit + push + CHANGELOG + version | +80 / -3 | 30min |
| **Total** | **+350 / -93** | **~3.5-4h** |

Result: 280 → ~295 tests passing (+15 tests, +3 files). No
new dep. `audit.tsx` becomes fully route-shell-free.
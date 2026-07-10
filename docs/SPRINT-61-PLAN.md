# Sprint 61 — Coverage of deferred items from Sprint 60 review

> **Status**: Planned · 2026-07-11
> **Comes after**: Sprint 60 (`637288c` + `e7e9d8a`)
> **Comes from**: `docs/REVIEW-2026-07-09.md` deferred list (§4) +
>  `docs/SPRINT-60-PLAN.md` §4 (out-of-scope)
> **Goal**: Ship the next 4 deferred items from the Sprint 60
> review pass. Same shape as Sprint 60 — quality + coverage
> improvements, no new user-facing features.

---

## 1. Why this sprint exists

Sprint 60 shipped the top-5 review picks. This sprint covers the
**4 next-highest-ROI items** from the deferred list (§4 of the
Sprint 60 plan):

| Item | Why it's still in |
| :--: | ----------------- |
| **S-A3** | Dirty-state guard — every settings tab that has draft state loses edits on navigation. Currently `useState` + uncontrolled inputs; user-side bug. |
| **S-A2** | SecretsTab 282 LoC — same refactor pattern that worked for VoiceTab (Sprint 56.7). |
| **R-A1** | audit.tsx 482 LoC with 7 inline components + 6 useState. Largest route file in the codebase. |
| **R-A4** | TanStack Query for /audit — every mount re-fetches. Cache + refetch-on-focus dedupes. |

This is a **refactor + UX** sprint — same shape as Sprint 60. No
new features. End state: 256 → ~290 tests passing, 0 new tech
debt, 1 new dep (`@tanstack/react-query`).

---

## 2. Scope — 4 items

### S-A3 — `useDirtyGuard` hook + adopt in 4 tabs (NEW, ~80 LoC + adoptions)

**The problem**: a user opens Settings → Secrets, types a new API
key, then clicks "Settings → Memory" in the sidebar. The
uncommitted draft is lost with no warning. Repeated user
complaint (Sprint 50 standing-rule review #4: "no dirty-state
guard").

**Solution**: a single `useDirtyGuard(dirty: boolean)` hook that:

1. Listens to the user's `popstate` event (browser back/forward)
   + intercepts `<Link>` navigation via a custom
   `useBlocker`-style pattern. When `dirty=true` and the user
   attempts to leave, shows a `confirm()` dialog: "You have
   unsaved changes. Leave anyway?".
2. Returns nothing (the dialog is fire-and-forget). The
   **caller** decides what counts as "dirty" — typically a
   comparison of form drafts against the last-saved state.
3. SSR-safe (no `window` references during initial render).

**API surface**:
```ts
useDirtyGuard({
  when: boolean   // true → block; false → no-op
  message?: string // confirm dialog body (default: "You have
                   // unsaved changes...")
})
```

**Adopters** (4 tabs with draft state):
- GeneralTab (6 useState — likely has drafts)
- MemoryTab (8 useState — user-memory CRUD)
- SecretsTab (15 useState — API keys, ACL)
- VoiceTab (15 useState — already has SaveBar; add the
  beforeunload guard as a complement)

**Tests** (`hooks/useDirtyGuard.test.ts`, NEW ~120 LoC, 5-6 tests):
1. `when=false` → no listener attached
2. `when=true` → calls `event.preventDefault()` on `popstate`
3. `confirm()` returns true → navigation proceeds
4. `confirm()` returns false → navigation blocked
5. unmount → listener detached
6. message override → custom string passed to `confirm()`

**Edge case**: the hook uses `window.confirm()` (native blocking
dialog). Some apps prefer a custom modal. We start with native —
the Sprint 62 design-decision deferred-list notes that a custom
modal could replace this. Native is fine for a single-user
desktop app.

### S-A2 — `SecretsTab` section-split (~280 LoC → 5 files of ~60 LoC)

**The problem**: SecretsTab 282 LoC follows the same anti-pattern
that VoiceTab had pre-Sprint-56.7. Multiple unrelated concerns
(API keys, Tailnet, Tailscale ACL, encrypted-at-rest, audit log)
jammed into a single function with shared state.

**Solution**: mirror Sprint 56.7's VoiceTab refactor pattern:

- `routes/settings/tabs/secrets/sections/ApiKeysSection.tsx` (~70 LoC)
- `routes/settings/tabs/secrets/sections/TailnetSection.tsx` (~50 LoC)
- `routes/settings/tabs/secrets/sections/AclSection.tsx` (~50 LoC)
- `routes/settings/tabs/secrets/sections/EncryptionSection.tsx` (~40 LoC)
- `routes/settings/tabs/secrets/sections/AuditSection.tsx` (~40 LoC)
- `routes/settings/tabs/SecretsTab.tsx` (orchestrator, ~30 LoC)

**Tests** (per-section, 2 tests each, 10 total):
- Each section renders with mock store
- Each section's primary action fires the right callback

**Net effect**: SecretsTab drops from 282 → ~30 LoC orchestrator
+ 5 small files. Easier to test + extend. 10 new tests.

### R-A1 — `audit.tsx` section-split (~480 LoC → 1 orchestrator + 5 sub-components + 1 hooks file)

**The problem**: `routes/audit.tsx` 482 LoC has:
- 1 main component (AuditDashboardPage) with 6 useState + 3 useMemo
- 4 inline components (AuditNode, DataTable, Header, StatCard)
- 4 format helpers (groupByDate, formatTime, formatBytes, formatMs)

**Solution**: section-split:

- `routes/audit/AuditHeader.tsx` (~50 LoC) — the page title +
  filter chips + stat cards
- `routes/audit/AuditFilters.tsx` (~60 LoC) — type + target filter
- `routes/audit/AuditNode.tsx` (~80 LoC) — single audit entry
  expand/collapse (the existing AuditNode lifted to its own file)
- `routes/audit/AuditList.tsx` (~60 LoC) — the list container +
  loading / empty / error states
- `routes/audit/format.ts` (~40 LoC) — `groupByDate`, `formatTime`,
  `formatBytes`, `formatMs` (the 4 format helpers, pure functions)
- `routes/audit.tsx` (orchestrator, ~120 LoC) — query state +
  filter state + composition

**Tests** (NEW, 8-10 tests):
- `format.test.ts` (4 tests pinning each format helper)
- `AuditNode.test.tsx` (3 tests: renders entry, expands, hides detail)
- `AuditFilters.test.tsx` (2 tests: emits filter change events)

**Net effect**: audit.tsx drops from 482 → ~120 LoC. The 4
format helpers + 4 inline components become individually
testable. 10 new tests.

### R-A4 — TanStack Query for /audit (~50 LoC + dep install)

**The problem**: every mount of `/audit` re-fetches the entire
500-entry log via `api.getAuditLog(500)`. Tab switches / window
focus / other navigation patterns re-trigger the same fetch.

**Solution**: install `@tanstack/react-query` and wrap the audit
fetch in `useQuery`:

```ts
const { data, isLoading, error, refetch } = useQuery({
  queryKey: ['audit', 'log', { limit: 500 }],
  queryFn: () => api.getAuditLog(500),
  refetchOnWindowFocus: true,
  staleTime: 30_000,  // 30s — don't refetch on every tick
});
```

**Why TanStack Query** (vs. SWR or hand-rolled):
- Already a well-known pattern in the React ecosystem
- Built-in cache invalidation, refetch-on-focus, dedup
- Smaller bundle (~10KB gzipped) than alternatives
- Single dep, no extra config needed for a one-screen use

**Dep addition** (`package.json`):
- `"@tanstack/react-query": "^5.0.0"` (latest 5.x)

**Test**: existing audit test (if any) still passes; no new
test required (the integration test is "does /audit load
faster?" — Sprint 62 perf benchmark).

**Adopters** (1 only — `/audit`):
- Sprint 61 only swaps audit.tsx
- Sprint 62 can adopt for /projects, /dashboard if the
  pattern proves out (deferred to next sprint per
  standing rule: "no premature dep sprawl")

---

## 3. Out of scope (deferred)

- **W-A4 — Zod schema validation** in wizard steps: Sprint 62
- **Card primitive** (U-A2): Sprint 62 (per U-A1 already
  done, Card is the natural follow-up)
- **Per-USER EQ** (A-A2): Sprint 62
- **A/B EQ compare** (A-A3): Sprint 62 (depends on per-USER EQ)
- **Lighthouse + axe CI** (X-A3): Sprint 62+
- **Coverage CI gate** (X-A1): Sprint 61 (config-only if time
  permits; otherwise Sprint 62)
- **ChannelsTab / MacTab** rewrites: out of scope (low user
  engagement per profile memory)
- **Per-USER EQ store + EQ snapshot test** (A-A2/A-A4): Sprint 62

---

## 4. Definition of done

- [ ] `hooks/useDirtyGuard.ts` extracted with `useDirtyGuard()`
  hook + 5-6 unit tests
- [ ] 4 tabs (GeneralTab / MemoryTab / SecretsTab / VoiceTab)
  adopt `useDirtyGuard`
- [ ] SecretsTab section-split: 5 new files, 10 new tests,
  orchestrator ≤30 LoC
- [ ] audit.tsx section-split: 5 new files, 10 new tests,
  orchestrator ≤150 LoC
- [ ] `@tanstack/react-query` installed + `useQuery` adopted
  in audit.tsx
- [ ] **280+/280+ vitest pass in 56+ test files** (was 256/256
  in 53 files; +3 for hooks + secrets + audit sections, +24 tests)
- [ ] **0 new tsc errors** (4 pre-existing `auth-bootstrap.test.ts`
  from Sprint 48 still allowed)
- [ ] CHANGELOG entry above Sprint 60
- [ ] `__version__` bumped 0.2.9 → 0.3.0 (**MINOR** — new
  `@tanstack/react-query` dep = a new runtime requirement;
  per SemVer, that's a minor-bump trigger. Pure refactor work
  would be PATCH; the new dep elevates it to MINOR.)
- [ ] All 4 version surfaces synced
- [ ] Senior-engineer audit findings resolved (or documented
  as deferred)
- [ ] 1 single commit (or 2 if diff > 1500 LoC; expect 2 given
  TanStack dep changes + 4 new section dirs)

---

## 5. Senior-engineer audit checklist

1. **`useDirtyGuard` SSR safety** — `confirm()` is a browser
   global; must be guarded with `typeof window !== "undefined"`.
   The hook's effect should not run during SSR (use
   `useEffect` not `useLayoutEffect`).
2. **`useDirtyGuard` Link interception** — react-router v6+
   doesn't expose `useBlocker` in stable; the workaround is
   to listen to `popstate` + show a confirm. **Test scope
   explicit**: back/forward only, NOT in-app `<Link>` clicks
   (which would require `useBlocker` and is out of scope).
3. **TanStack Query staleTime** — pick a value that's long
   enough to dedupe rapid re-mounts (30s is a reasonable
   default for an audit log that doesn't change mid-session)
   but short enough that a Settings-driven restart shows up
   within a user session.
4. **TanStack Query provider scope** — the `<QueryClientProvider>`
   should live in `App.tsx` next to the existing
   `HaloLive2DProvider`. Single client instance.
5. **SecretsTab section-split state ownership** — 5 sections
   sharing 15 useState means we need a `useSecretsStore`
   custom hook (mirroring the VoiceTab pattern from
   Sprint 56.7). Otherwise the orchestrator would re-render
   all 5 sections on every keystroke.
6. **audit.tsx split: orchestrator testability** — the
   orchestrator holds the `useQuery` hook + filter state;
   the 4 sub-components are pure. Each sub-component test
   mocks its props (no react-query needed in unit tests).
7. **TanStack Query bundle size** — verify the dep doesn't
   blow past 50KB gzipped for the audit page. Use
   `vite-bundle-visualizer` or manual `du -sh node_modules/@tanstack`.
8. **Route smoke guard** — `routes/audit.tsx` and the new
   `routes/audit/*` files must be in `ROUTE_ENTRIES` (or
   `HELPER_INFERENCE_ROOT`); the guard auto-catches on commit.

---

## 6. Commit plan (likely 2 commits)

```
[main]
  e7e9d8a Sprint 60 (in-session) — Version bump 0.2.8→0.2.9 + sprint docs
  xxxxxx  Sprint 61 (in-session) — Refactor + UX: useDirtyGuard +
          SecretsTab split + audit split + TanStack Query
          (refactor + 1 new dep, 0.2.9→0.3.0)
  xxxxxx  Sprint 61 (in-session) — Tests + CHANGELOG + version bump
```

(Split if the refactor commit is > 1500 LoC; otherwise single.)

---

## 7. Standing rules (carry-over + new)

- New shared components MUST have ≥3 tests (Sprint 60 rule)
- New utility classes use `attach-on-first-use` + testable
  without real audio (Sprint 60 rule)
- New routes MUST register in `ROUTE_ENTRIES` (Sprint 60 rule)
- **NEW (this sprint)**: any new custom hook (e.g.
  `useDirtyGuard`, `useSecretsStore`) MUST have ≥4 tests:
  hook contract + SSR safety + unmount cleanup + edge case.
  Hooks are easier to test than components but also easier
  to leak listeners, so the test bar is higher.
- **NEW (this sprint)**: any new dep addition MUST:
  1. Be reviewed for bundle size impact (the audit page
     shouldn't blow past 50KB gzipped)
  2. Have a stated "rollback plan" — if the dep is
     abandoned, can we replace it with hand-rolled code
     in <1 day?
  3. Be added to `docs/CHANGELOG.md` in the same commit

---

## 8. Effort estimate

| Item | LoC +/- | Time |
| ---- | --- | --- |
| S-A3: useDirtyGuard + 4 tab adoptions | +130 / -50 | 1.5h |
| S-A2: SecretsTab split (5 files + 10 tests) | +500 / -250 | 2.5h |
| R-A1: audit.tsx split (5 files + 10 tests) | +500 / -350 | 2.5h |
| R-A4: TanStack Query + audit adopt | +50 / -20 | 1h |
| Audit + commit + push + CHANGELOG + version | +100 / -3 | 30min |
| **Total** | **+1180 / -670** | **~8-9h** |

Result: 256 → ~280 tests passing (~3 net new files; +24 tests
across hook + secrets sections + audit sections). 1 new dep.
Net: -40% in audit.tsx LoC, -89% in SecretsTab LoC.
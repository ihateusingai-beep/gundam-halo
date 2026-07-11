# Sprint 65 — Coverage CI gate + axe-core smoke + Zod migration (2 more)

> **Status**: Planned · 2026-07-12
> **Comes after**: Sprint 64 (`9afa950`)
> **Goal**: Land the first CI gates (coverage threshold +
> axe-core a11y smoke) + continue Zod migration to 5/7
> wizard steps.

---

## 1. Why this sprint exists

Sprint 64 landed the audio half of the EQ editor + 2 more
Zod steps. This sprint covers:

1. **X-A1** — coverage CI gate. We have 312 tests; no
   coverage gate exists. Without a threshold, the test
   count can grow while coverage drops. A simple
   `vitest --coverage` with a threshold check fixes that.
2. **X-A3a** — axe-core smoke test. We have 0 a11y tests.
   A single test that renders 3 key routes (cockpit,
   settings, audit) and runs `axe-core` against them
   catches the most common a11y bugs (missing labels,
   wrong roles, color contrast).
3. **W-A4 (migrate 2 more)** — StepVoiceTTS + StepTailscale.
   These are the last 2 of the 5 form steps. StepSmoke +
   StepWelcome are non-form (no Zod migration needed).

This is a **CI + migration** sprint. Coverage + a11y are
new concerns; the Zod migration is mechanical.

---

## 2. Scope — 3 items

### X-A1 — coverage CI gate (config only)

**The current state**: `vitest.config.ts` has
`coverage.enabled: false`. There's no coverage threshold
check. Sprint 50+ standing-rule review #2 noted: "test
count can grow while coverage drops; need a coverage
gate".

**The change** (this sprint):
- Add `coverage.enabled: true` + `coverage.thresholds.lines: 60`
  (loose — we have ~70% line coverage; 60% is a floor
  that catches catastrophic drops without blocking
  incremental growth)
- Add a `pnpm test:coverage` script
- The threshold FAILs the test run if line coverage
  drops below 60%. Sprint 66+ can ratchet the threshold
  up as coverage improves.

**API** (config-only):
```ts
// vitest.config.ts
coverage: {
  enabled: false,  // opt-in via `pnpm test:coverage`
  provider: "v8",
  reporter: ["text", "html"],
  thresholds: {
    lines: 60,
    functions: 60,
    branches: 50,
    statements: 60,
  },
}
```

**Tests**: 0 new. The threshold is enforced by vitest's
built-in coverage check.

**Cost**: `--coverage` adds ~10-15s to the test run (v8
rebuild + lcov generation). Acceptable for a CI gate.

### X-A3a — axe-core smoke test on 3 routes

**The current state**: 0 a11y tests. axe-core is a
de-facto industry-standard a11y scanner; jsdom is
sufficient for the static analysis (color contrast is
the only thing that requires a real browser).

**The change** (this sprint):
- Install `@axe-core/react` (or `@axe-core/playwright` —
  we don't have Playwright; use `@axe-core/react`)
- NEW `routes/__a11y-smoke.test.tsx` (1 file) — renders
  3 key routes (cockpit, settings, audit) and runs
  `axe()` against each
- 3 tests total (one per route); each asserts no
  `serious` or `critical` violations

**Adopters** (3 routes):
- `routes/audit.tsx` — security log
- `routes/settings/index.tsx` — settings tabs
- `routes/NotFound.tsx` — 404 (Sprint 60 R-A3)

**Tests** (`routes/__a11y-smoke.test.tsx`, NEW ~120 LoC, 3 tests):
1. `routes/audit` page has no serious/critical axe violations
2. `routes/settings` page has no serious/critical axe violations
3. `routes/NotFound` page has no serious/critical axe violations

**Cost**: `@axe-core/react@4.x` is ~300KB gzipped (heavy).
Per Sprint 61's "new dep bundle size review" rule: heavy
but acceptable for a CI test (not in the production
bundle — `vitest` runs it once and disposes).

### W-A4 (migrate 2 more) — StepVoiceTTS + StepTailscale

**The current state** (Sprint 64):
- 3 of 7 steps on Zod (StepLLM, StepVoiceASR, StepTheme)
- 4 left: StepVoiceTTS, StepTailscale, StepSmoke,
  StepWelcome

**The change** (this sprint):
- Migrate `StepVoiceTTS` (212 LoC) + `StepTailscale`
  (101 LoC) to Zod
- StepVoiceTTS has backend + voice + model_name fields
  (3-4 field schema)
- StepTailscale has enabled + tailnet + api_key fields
  (3-4 field schema)
- Same pattern as before: schema declaration +
  useStepValidation hook + error merge

**Why these 2 specifically** (not the other 2):
- StepSmoke and StepWelcome are non-form steps. They
  don't have a draft to validate. Defer indefinitely.
- StepVoiceTTS and StepTailscale are the last 2 form
  steps. After this sprint, 5/5 form steps are on Zod.

**Tests**: +2 tests (1 per step, similar to Sprint 64).

---

## 3. Out of scope (deferred to Sprint 66+)

- **X-A3b** — Lighthouse CI (perf budget). Sprint 66+
  (needs product sign-off on the perf budget).
- **X-A1b** — ratchet the coverage threshold up
  (currently 60%; target 80% by Sprint 70).
- **Per-USER EQ persistence** to localStorage: Sprint 66+
  (UX review needed first).
- **Card primitive adoption in 8 settings tabs**: Sprint
  66+ (mechanical work, low risk).

---

## 4. Definition of done

- [ ] `vitest.config.ts` enables coverage with a 60% line
  threshold
- [ ] `package.json` adds `test:coverage` script
- [ ] `@axe-core/react` installed
- [ ] `routes/__a11y-smoke.test.tsx` with 3 tests
- [ ] `StepVoiceTTS` migrates to Zod (+1 test)
- [ ] `StepTailscale` migrates to Zod (+1 test)
- [ ] **320+/320+ vitest pass in 63+ test files** (was 312/312
  in 61 files; +1 file for a11y smoke, +5-6 tests)
- [ ] **0 new tsc errors** (4 pre-existing `auth-bootstrap.test.ts`
  from Sprint 48 still allowed)
- [ ] **0 axe violations of `serious` or `critical` severity**
  (the gate fails if any)
- [ ] CHANGELOG entry above Sprint 64
- [ ] `__version__` bumped 0.3.3 → **0.3.4** (PATCH — CI gates
  + 2 Zod migrations; no breaking change)
- [ ] All 4 version surfaces synced
- [ ] Senior-engineer audit findings resolved (or
  documented as deferred)
- [ ] 1 single commit (or 2 if diff > 1500 LoC; estimate
  ~500 LoC net so single commit is fine)

---

## 5. Senior-engineer audit checklist

1. **Coverage threshold** — 60% is a FLOOR, not a target.
   Catches catastrophic drops; doesn't block incremental
   growth. Sprint 66+ can ratchet up.
2. **Coverage provider** — `v8` is the default. Fast
   (~10-15s overhead). Acceptable for CI.
3. **`@axe-core/react` bundle size** — ~300KB gzipped
   for the test-only dep. Per Sprint 61's "new dep
   bundle size review" rule: heavy but acceptable for
   CI (not in production bundle). Rollback: remove
   the file + the dep.
4. **axe-core false positives** — jsdom can't fully
   render the cockpit shell. The 3 routes we scan
   (audit, settings, NotFound) DON'T mount
   CockpitLayout; they're test-isolated. Should be
   clean.
5. **axe-core severity** — we filter to `serious` and
   `critical` (skipping `moderate` and `minor`). This
   matches the convention from axe-core's CLI. Sprint
   66+ can lower the threshold if the team wants more
   coverage.
6. **Zod schema for StepVoiceTTS** — the form has a
   `backend` field with 3 enum values (piper, edge_tts,
   coqui). The schema must mirror the existing
   `VoiceTTSConfig` type in `types/api.ts`.
7. **Zod schema for StepTailscale** — the form has an
   optional `api_key` field. The schema should make
   `api_key` required ONLY when `enabled: true`. Use
   `z.discriminatedUnion('enabled', ...)` for this
   conditional rule.
8. **Carry-over rules** — new dep (`@axe-core/react`)
   MUST have CHANGELOG entry + bundle size review +
   rollback plan; new hook tests ≥4 (no new hooks
   this sprint; using `useStepValidation` from Sprint 63).

---

## 6. Commit plan (single commit, ~500 LoC net)

```
[main]
  9afa950 Sprint 64 (in-session) — EQ editor audio wire + Zod migration (2 steps)
  xxxxxx  Sprint 65 (in-session) — Coverage CI gate + axe-core smoke +
          Zod migration (2 more)
          (vitest coverage + @axe-core/react + StepVoiceTTS + StepTailscale,
          CI gates + refactor, 0.3.3→0.3.4)
```

---

## 7. Standing rules (carry-over + new)

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
- **NEW (this sprint)**: a11y tests run on route-level
  smoke only (3 routes). Component-level a11y tests
  are out of scope (would require deeper integration).
- **NEW (this sprint)**: coverage threshold is a FLOOR
  (60% line, 50% branch, 60% function/statement). Sprint
  66+ can ratchet up; never down.

---

## 8. Effort estimate

| Item | LoC +/- | Time |
| ---- | --- | --- |
| X-A1: vitest coverage config | +20 / 0 | 30min |
| X-A3a: @axe-core/react install + smoke tests | +180 / 0 | 1h |
| W-A4 migrate 2: StepVoiceTTS + StepTailscale | +80 / -20 | 1h |
| Audit + commit + push + CHANGELOG + version | +60 / -3 | 30min |
| **Total** | **+340 / -23** | **~3h** |

Result: 312 → ~318 tests passing (+6 tests, +1 file). 1
new dep (`@axe-core/react@4.x`). Coverage gate in
place.
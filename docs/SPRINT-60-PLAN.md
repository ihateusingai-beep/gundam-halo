# Sprint 60 — Quality-of-life + coverage gaps

> **Status**: Planned · 2026-07-09
> **Comes after**: Sprint 59 (`52996d5` + `a9dd1be`)
> **Comes from**: `docs/REVIEW-2026-07-09.md` top-5 picks + 2 additions from the gaps table
> **Goal**: Tighten the codebase's biggest gaps — 1 large component split, 1 shared component extraction, 3 untested steps, 7 untested primitives, 1 missing 404 page.

---

## 1. Why this sprint exists

The Sprint 59 review pass (`docs/REVIEW-2026-07-09.md`) identified the
top-5 highest-ROI items from the 7 reviewed scopes. Sprint 60 ships
all 5 plus 2 closely-related additions from the gaps table.

This is a **quality + coverage** sprint — no new user-facing features,
no new dependencies. Every item either reduces technical debt or
raises test coverage. End state: 213 → ~250 tests passing, 0 new
tech debt, no new UX paths.

### Sprint 59 review picks (5)

| Rank | Item | Source review |
| :--: | ---- | ------------- |
| 1 | A-A1: extract TTS playback queue from VoicePanel → `lib/tts-player.ts` | Review §2 |
| 2 | S-A4: extract SaveBar from VoiceTab → shared component | Review §4 |
| 3 | W-A1: tests for 3 untested wizard steps + wizard hook | Review §1 (corrected — see §3 below) |
| 4 | U-A1: smoke tests for 7 UI primitives | Review §3 |
| 5 | R-A3: proper NotFound route (replace silent `<Navigate to="/">`) | Review §5 |

### Sprint 59 review additions (2)

| # | Item | Why added |
| - | ---- | --------- |
| 6 | **R-A1a**: pre-existing bug — `path="*"` in App.tsx silently redirects to `/` with no user feedback. R-A3 fix overlaps. | Caught during recon |
| 7 | **CHANGELOG + version bump 0.2.8 → 0.2.9** (PATCH — refactor + tests only, no new feature) | Per `__version__` standing rule |

---

## 2. Sprint 59 review correction: W-A1 scope

The review said "4/9 wizard steps uncovered". Recon found 6/9 step
tests exist:

```
components/wizard/StepLLM.test.tsx        ✓
components/wizard/StepSmoke.test.tsx      ✓
components/wizard/StepTailscale.test.tsx  ✓
components/wizard/StepTheme.test.tsx      ✓
components/wizard/StepVoiceASR.test.tsx   ✓
components/wizard/StepVoiceTTS.test.tsx   ✓
components/wizard/StepWelcome.test.tsx    ✗ MISSING
components/wizard/StepFinish.test.tsx     ✗ MISSING
hooks/useSetupWizard.test.ts              ✗ MISSING  (the wizard hook driving all 7 steps)
```

**Real scope**: 3 files (not 4) — StepWelcome (trivial),
StepFinish (small), useSetupWizard (the integration test that
catches regressions in the state machine). Estimated +300-400
LoC of tests.

---

## 3. Scope — 5 files created / modified, 7 files touched

### A-A1 — `lib/tts-player.ts` (NEW, ~200 LoC) + `VoicePanel.tsx` (−150 LoC)

**What's moving out of VoicePanel**:
- `audioQueueRef` (line 103)
- `playSeqRef` (line 108)
- `drainingRef` (line 109)
- `drainAudioQueue()` closure (line 177)
- `playChunk()` function (line 203)

**API surface** (`TtsPlayer` class):
```ts
class TtsPlayer {
  constructor(opts: { audioRef: RefObject<HTMLAudioElement> })
  attach(audioEl: HTMLAudioElement): void  // first-call patches MediaElementSource
  enqueue(chunk: ArrayBuffer): void          // push + drain
  reset(): void                              // bump seq + clear queue (turn boundary)
  dispose(): void                            // cleanup, idempotent
}
```

**Tests** (`lib/tts-player.test.ts`, NEW ~150 LoC, 6-8 tests):
1. enqueue pushes + drains in order
2. reset() aborts in-flight drain chain (sequence bump)
3. dispose() is idempotent
4. attach() is lazy (first-call only) — prevents double-patch crash
5. theme change during play doesn't interrupt the current frame
6. empty enqueue is a no-op (not a crash)

**Net effect**: VoicePanel drops from 548 → ~400 LoC. Tests
move from integration-only to unit-testable.

### S-A4 — `routes/settings/shared/SaveBar.tsx` (NEW, ~60 LoC) + 8 tab files

**Source**: `routes/settings/tabs/voice/sections/SaveBar.tsx`
(47 LoC, currently only used by VoiceTab).

**API surface**:
```ts
interface SaveBarProps {
  dirty: boolean
  saving: boolean
  onSave: () => void | Promise<void>
  onReset?: () => void
  saveLabel?: string         // default "Save"
  resetLabel?: string        // default "Reset"
}
```

**Adopters** (8 tabs):
- GeneralTab
- MacTab
- ChannelsTab
- MemoryTab
- SecretsTab
- SecurityTab
- ThemesTab (no save, just skip)
- VoiceTab (already has it — replace inline with shared)

**Tests** (`routes/settings/shared/SaveBar.test.tsx`, NEW ~120 LoC, 5-7 tests):
1. dirty=false → save button disabled
2. dirty=true → save button enabled, click fires onSave
3. saving=true → button shows "Saving…" + disabled
4. reset button only renders when onReset provided
5. keyboard: Enter on save button fires click
6. a11y: button has aria-disabled when dirty=false

**Net effect**: 8 tabs benefit; ~50 LoC dedup per tab.

### W-A1 — 3 new test files (~350 LoC total)

- `components/wizard/StepWelcome.test.tsx` (~80 LoC, 3 tests)
- `components/wizard/StepFinish.test.tsx` (~120 LoC, 4 tests)
- `hooks/useSetupWizard.test.ts` (~250 LoC, 6 tests)

**Coverage targets**:
- StepWelcome: renders CTA, fires onNext on click, doesn't render error state when errors=[]
- StepFinish: shows "Setup Complete" success state, copy to clipboard works, "Restart" button fires onRestart
- useSetupWizard: state machine transitions (idle → loading → ready → saving → saved → error), persistence round-trip, skip-step behavior

### U-A1 — 7 new test files (~400 LoC total, 1 file per primitive)

- `components/ui/button.test.tsx` (~80 LoC, 4 tests: variant render, size render, click, disabled)
- `components/ui/dialog.test.tsx` (~100 LoC, 5 tests: open/close, Escape, backdrop, focus trap, portal)
- `components/ui/command.test.tsx` (~80 LoC, 4 tests: render, search, selection, empty state)
- `components/ui/dropdown-menu.test.tsx` (~60 LoC, 3 tests: open/close, item click, submenu)
- `components/ui/input.test.tsx` (~30 LoC, 2 tests: value + onChange)
- `components/ui/textarea.test.tsx` (~30 LoC, 2 tests: value + onChange)
- `components/ui/input-group.test.tsx` (~30 LoC, 2 tests: addon rendering)

**Coverage targets**: each test renders the component + asserts
one behaviour. No exhaustive variants testing (CVA snapshots
already cover visual variants via the dev styleguide).

### R-A3 — `routes/NotFound.tsx` (NEW, ~60 LoC) + `App.tsx` (1-line fix)

**API**:
```tsx
export function NotFoundPage() {
  // Renders a HudCard with "404" headline + "this URL doesn't exist"
  // body + "← Back to Cockpit" button (Link to="/").
}
```

**Wire-up** (`App.tsx` line 39):
```tsx
- <Route path="*" element={<Navigate to="/" replace />} />
+ <Route path="*" element={<NotFoundPage />} />
```

**Tests** (`routes/NotFound.test.tsx`, NEW ~50 LoC, 3 tests):
1. Renders "404" + URL echo
2. "Back to Cockpit" link is present with `href="/"`
3. Renders inside CockpitLayout shell (not naked)

---

## 4. Out of scope (deferred)

- **Per-tab dirty-state guard** (S-A3): Sprint 61
- **Section-split SecretsTab** (S-A2): Sprint 61
- **Zod schema validation** (W-A4): Sprint 61
- **A/B EQ compare** (A-A3): Sprint 62 (after per-USER EQ store)
- **Per-USER EQ independent of theme** (A-A2): Sprint 62
- **TanStack Query for /audit** (R-A4): Sprint 61
- **Section-split audit.tsx** (R-A1): Sprint 61
- **Card primitive** (U-A2): Sprint 61
- **Lighthouse CI + axe-core gate** (X-A3): Sprint 62+
- **Coverage CI gate** (X-A1): Sprint 61 (config-only, no new tests)
- **Feature flag system** (X-A2): Sprint 62+ (needs design discussion)

---

## 5. Definition of done

- [ ] `lib/tts-player.ts` extracted with `TtsPlayer` class + 6-8 unit tests
- [ ] `VoicePanel.tsx` ≤ 400 LoC (was 548)
- [ ] `routes/settings/shared/SaveBar.tsx` shared component + 5-7 tests
- [ ] 8 tabs (including VoiceTab) use the shared SaveBar
- [ ] `StepWelcome.test.tsx` / `StepFinish.test.tsx` / `useSetupWizard.test.ts` added
- [ ] 7 UI primitive smoke tests
- [ ] `routes/NotFound.tsx` + `App.tsx` fix + 3 tests
- [ ] **253+/253+ vitest pass in 47+ test files** (was 213/213 in 47 files; +3 files for hooks + routes + shared, +40 tests)
- [ ] **0 new tsc errors** (4 pre-existing `auth-bootstrap.test.ts` from Sprint 48 still allowed)
- [ ] CHANGELOG entry above Sprint 59
- [ ] `__version__` bumped 0.2.8 → 0.2.9 (PATCH — refactor + tests only)
- [ ] All 4 version surfaces synced
- [ ] Senior-engineer audit findings resolved (or documented as deferred)
- [ ] 1 single commit "Sprint 60 (in-session) — Quality-of-life + coverage gaps"
      OR split into 2 commits if the diff exceeds 1500 LoC

---

## 6. Senior-engineer audit checklist (per Sprint 56.6 standing rule)

Pre-commit, verify:

1. **TtsPlayer attach lifecycle** — calling `attach()` twice MUST
   not double-patch (would throw `InvalidStateError`). Audit:
   grep `new MediaElementAudioSourceNode` to confirm single call
   per audio element.
2. **SaveBar a11y** — buttons have `aria-disabled` (not just
   `disabled`) when dirty=false. Disabled buttons don't fire
   focus events on some screen readers; aria-disabled keeps the
   button in the tab order.
3. **NotFoundRoute test isolation** — `routes/NotFound.test.tsx`
   MUST render inside a Router (MemoryRouter); otherwise
   `<Link to="/">` throws.
4. **useSetupWizard persistence** — the hook calls
   `setTimeout`-debounced save (per Sprint 56.5 audit pattern).
   Test must NOT use real timers (vi.useFakeTimers required).
5. **UI primitive tests** — button.tsx wraps `@base-ui/react/button`,
   which has its own internal `act()` warnings. Wrap renders in
   `act()` to avoid spurious "not wrapped in act" failures.
6. **Test count budget** — Sprint 60 adds ~40 tests. Plan budget:
   50-test headroom above 213 → 263 maximum. Sprint 60 ships
   253 ± 5. Anything above this triggers a coverage-ratio review.

---

## 7. Commit plan (single commit)

```
[main]
  a9dd1be Sprint 59 (in-session) — Layout review: function-level JSDoc on 5 files
  xxxxxx  Sprint 60 (in-session) — Quality-of-life + coverage gaps
          (1 new lib, 1 new shared component, 10 new test files,
          1 NotFound route, 0.2.8→0.2.9 version bump)
```

If the diff exceeds 1500 LoC, split into:
- `xxxxxx` Sprint 60 (in-session) — lib/tts-player + SaveBar extraction (refactor)
- `xxxxxx` Sprint 60 (in-session) — Tests + NotFound (coverage + UX) — version bump

---

## 8. Standing rules (carry-over from Sprint 59)

- Every `themeId` field string-keyed against the 9-theme union
- Per-theme asset paths use `gundam-<slug>` strip + NT-D bare fallback
- Asset commits separate from wire-up commits (binary diff bloat)
- **NEW (this sprint)**: any new shared component MUST have ≥3 tests
  (smoke + variant + a11y). Saves re-deriving the test contract.
- **NEW (this sprint)**: any new extractable utility class (like
  TtsPlayer) MUST use the `attach-on-first-use` pattern + be
  testable WITHOUT real `AudioContext`. Use `vi.fn()` for any
  audio-graph methods called by the player.

---

## 9. Effort estimate

| Item | LoC +/- | Time |
| ---- | --- | --- |
| A-A1: TtsPlayer + tests | +200 / -150 | 1.5h |
| S-A4: SaveBar shared + 8 tab adopters | +60 / -50×8 = -340 | 2h |
| W-A1: 3 wizard tests | +350 / 0 | 2h |
| U-A1: 7 primitive tests | +400 / 0 | 1h |
| R-A3: NotFound + App.tsx fix + tests | +60 / -1 | 30min |
| Audit + commit + push + CHANGELOG | +60 / -3 | 30min |
| **Total** | **+580 / -494** | **~7-8h** |

Result: 213 → ~253 tests passing, ~5 new files, 1 file deleted
(`voice/sections/SaveBar.tsx` becomes a re-export shim or is
removed if not used elsewhere).
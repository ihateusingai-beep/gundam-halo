# Sprint 64 — EQ editor audio wire + Zod migration (2 steps)

> **Status**: Planned · 2026-07-12
> **Comes after**: Sprint 63 (`91cca37`)
> **Goal**: Land the audio half of the EQ editor (Sprint 63
> was UI-only) + migrate 2 more wizard steps to Zod.

---

## 1. Why this sprint exists

Sprint 63 shipped the EQ editor **UI skeleton** (5 sliders,
local state, no audio change). The plan doc explicitly
deferred the audio wire-up to "Sprint 64 (MUST be reviewed
by a senior-engineer before any audio change lands)".

This sprint ships:
1. **A-A4 (audio)** — wire the sliders to `TtsAudioGraph`
   via a new `setBandGain(band, gainDb)` method. The
   visualizer's bars should reflect the user's edits in
   real time.
2. **W-A4 (migrate 2)** — continue the Zod migration
   pilot. StepVoiceASR + StepTheme (the 2 simplest
   non-LLM steps).

This is a **wire-up + migration** sprint. The audio change
is the riskier half; the Zod migration is mechanical.

---

## 2. Scope — 2 items

### A-A4 (audio) — wire EQ editor sliders to TtsAudioGraph

**The current state** (Sprint 63):
- `CockpitEqCard` has 5 sliders that update
  `localGains` (local state)
- The audio graph's `setPreset(preset)` overwrites ALL 5
  band gains at once
- There's no per-band API on `TtsAudioGraph` — only
  setTheme (whole preset) and setPreset (whole preset)

**The change** (this sprint):
- NEW `TtsAudioGraph.setBandGain(band, gainDb)` method
  that sets `filter.gain.value` on a single band
  (0-4, mapping to the 5 BiquadFilterNodes created at init)
- `CockpitEqCard`'s slider `onChange` calls
  `graph.setBandGain(band, gain)` for the active graph
  AND updates `localGains`
- A new "Apply" button promotes `localGains` to a
  permanent override (writes to `useEqStore`)
- A "Reset" button restores the preset's default gains

**Why the per-band API is needed**:
- Per-band changes are the user's intent: "I like SEED's
  defaults but want 2dB more bass"
- The whole-preset API doesn't support this — the user
  would have to re-pick a theme every time they tweak
  one band

**API**:
```ts
class TtsAudioGraph {
  // ...existing methods...
  /** Set a single band's gain in dB. band 0-4 maps to the
   *  5 BiquadFilterNodes created at init. Sets
   *  `setValueAtTime(gain, ctx.currentTime)` for snap
   *  (no ramp, matching the visual theme switch).
   *  No-op if the graph hasn't been initialised. */
  setBandGain(band: 0 | 1 | 2 | 3 | 4, gainDb: number): void;
}
```

**Tests** (`lib/audio-graph.test.ts`, extend existing, +3-4 tests):
1. `setBandGain(0, 5)` sets the first filter's `gain.value` to 5
2. `setBandGain` before init is a no-op
3. `setBandGain(99, 5)` is out-of-bounds (no-op + warn)
4. `setBandGain` after `dispose` is a no-op

**Adopter**: `CockpitEqCard`:
- The `localGains` useEffect now also calls
  `graph.setBandGain(band, gain)` for each band when
  editMode is on
- Add `data-testid="eq-editor-apply"` + Apply button
- Add `data-testid="eq-editor-reset"` + Reset button

### W-A4 (migrate 2 steps) — StepVoiceASR + StepTheme

**The current state** (Sprint 63):
- Only `StepLLM` uses Zod
- 6 other steps still have hand-rolled validation

**The change** (this sprint):
- Migrate `StepVoiceASR` (139 LoC) + `StepTheme` (115 LoC)
  to use `useStepValidation` with their own Zod schemas
- The pattern is identical to `StepLLM`'s:
  - Declare a Zod schema at the top
  - Call `useStepValidation(schema, draft)` inside the component
  - Merge the result with the parent-supplied `errors`
- Both steps have ~5 fields each, simple schemas

**Why these 2 specifically** (not the other 4):
- `StepVoiceASR` and `StepTheme` are the simplest non-LLM
  steps. Migrating them gives us 3 of 7 steps on Zod,
  which is a meaningful pilot.
- `StepVoiceTTS` and `StepTailscale` have more complex
  shapes (multi-field forms, optional paths). Defer to
  Sprint 65 to keep the migration mechanical.
- `StepSmoke` and `StepWelcome` aren't form steps; they
  don't have validation. Defer indefinitely.

**Tests**:
- Extend `StepVoiceASR.test.tsx` with 1 test asserting
  `useStepValidation` is wired (e.g. an empty
  `wake_phrase` field shows a Zod error)
- Extend `StepTheme.test.tsx` similarly
- 0 NEW test files; +2 tests

---

## 3. Out of scope (deferred to Sprint 65+)

- **W-A4 (migrate 4 more)** — StepVoiceTTS + StepTailscale
  + StepSmoke + StepWelcome. Sprint 65+ continues.
- **X-A1 — Coverage CI gate**: Sprint 65.
- **X-A3 — Lighthouse + axe CI gate**: Sprint 65+.
- **Per-USER EQ persistence** to localStorage: Sprint 66+
  (UX review needed first).
- **Card primitive adoption in 8 settings tabs**: Sprint
  66+ (mechanical work, low risk).

---

## 4. Definition of done

- [ ] `TtsAudioGraph.setBandGain(band, gainDb)` method
  + 3-4 unit tests
- [ ] `CockpitEqCard` sliders wire to `setBandGain` +
  Apply + Reset buttons
- [ ] `StepVoiceASR` migrates to Zod (+1 test)
- [ ] `StepTheme` migrates to Zod (+1 test)
- [ ] **320+/320+ vitest pass in 62+ test files** (was 305/305
  in 61 files; +1 file for audio-graph extension, +5-6 tests)
- [ ] **0 new tsc errors** (4 pre-existing `auth-bootstrap.test.ts`
  from Sprint 48 still allowed)
- [ ] CHANGELOG entry above Sprint 63
- [ ] `__version__` bumped 0.3.2 → **0.3.3** (PATCH — audio
  wire-up + 2 Zod migrations; no breaking change)
- [ ] All 4 version surfaces synced
- [ ] Senior-engineer audit findings resolved (or
  documented as deferred)
- [ ] 1 single commit (or 2 if diff > 1500 LoC; estimate
  ~500 LoC net so single commit is fine)

---

## 5. Senior-engineer audit checklist

1. **`setBandGain` snap vs. ramp** — uses `setValueAtTime`
   (instant, matching `setTheme`/`setPreset` in Sprint 57).
   No `linearRampToValueAtTime` (would add 50ms ramp; out
   of scope for "instant snap" per the standing rule).
2. **`setBandGain` out-of-bounds** — band 5+ throws or
   no-ops? Plan: no-op + console.warn (callers can pass
   a TS-narrowed `0 | 1 | 2 | 3 | 4`, so this is defensive
   only).
3. **Audio graph lifecycle** — the slider's effect MUST
   cleanup the subscription on unmount. The graph is
   already disposed in the existing useEffect; no new
   cleanup needed.
4. **Sliders vs. performance** — every onChange triggers
   a `setBandGain` + a state update. The cost is ~1
   BiquadFilterNode.setValueAtTime + 1 React render. This
   is the same cost as the per-theme `setTheme` call. Safe.
5. **Zod schema + parent errors merge** — StepVoiceASR
   and StepTheme must merge the Zod errors with the
   parent-supplied `errors` (same pattern as StepLLM).
   `data-testid` for the per-field error display MUST
   be preserved.
6. **Carry-over rules** — new tests ≥4 for new hook /
  utility; ≥3 for new component; bundle size + rollback
  for new dep. No new deps this sprint.

---

## 6. Commit plan (single commit, ~500 LoC net)

```
[main]
  91cca37 Sprint 63 (in-session) — Zod pilot + Card adoption + EQ editor skeleton
  xxxxxx  Sprint 64 (in-session) — EQ editor audio wire + Zod migration (2 steps)
          (TtsAudioGraph.setBandGain + CockpitEqCard Apply/Reset +
          StepVoiceASR + StepTheme Zod, refactor + small UX, 0.3.2→0.3.3)
```

---

## 7. Standing rules (carry-over)

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
- EQ editor UI changes MUST be senior-engineer reviewed
  before any audio change lands (Sprint 63 rule)

---

## 8. Effort estimate

| Item | LoC +/- | Time |
| ---- | --- | --- |
| A-A4 audio: setBandGain + CockpitEqCard wire | +120 / -30 | 1.5h |
| W-A4 migrate 2: StepVoiceASR + StepTheme | +80 / -20 | 1h |
| Audit + commit + push + CHANGELOG + version | +60 / -3 | 30min |
| **Total** | **+260 / -53** | **~3h** |

Result: 305 → ~313 tests passing (+8 tests, +1 file).
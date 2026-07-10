# Sprint 63 — Zod validation + Card adoption + EQ editor skeleton

> **Status**: Planned · 2026-07-11
> **Comes after**: Sprint 62 (`fcc58ba`)
> **Comes from**: `docs/REVIEW-2026-07-09.md` deferred list (§4) +
>  `docs/SPRINT-61-PLAN.md` + `docs/SPRINT-62-PLAN.md` out-of-scope
> **Goal**: Ship 3 more deferred items. Zod is the highest-risk
> item (new dep + migration scope), so this sprint is a
> **pilot**: Zod for ONE step, then assess.

---

## 1. Why this sprint exists

Sprint 62 shipped per-USER EQ + A/B compare + Card. This
sprint covers:

| # | Item | Why it's still in |
| - | ---- | ----------------- |
| 1 | **W-A4 (pilot)** — Zod for ONE wizard step | The wizard steps have hand-rolled validation. Zod would centralize it. |
| 2 | **U-A2 cont.** — Card adoption in audit | Card primitive was added but only 1 site adopted. |
| 3 | **A-A4** — EQ editor UI skeleton | Per-USER override (Sprint 62) is "all or nothing" (whole preset). Per-band sliders = the next affordance. |

This is a **feature + refactor** sprint:
- W-A4 (pilot) is a new dep + a feature gate for future steps
- U-A2 cont. is refactor
- A-A4 is a small UX enhancement (skeleton — no audio change)

---

## 2. Scope — 3 items

### W-A4 (pilot) — Zod schema for `StepLLM` only (~120 LoC + tests)

**The problem**: the wizard's hand-rolled validation (e.g.
"non-empty API key", "valid base URL") is scattered across
each step. Sprint 60+ has 4 different `WizardError[]` patterns;
inconsistencies are common. Zod would centralize it.

**Solution**: install `zod` + a new `useStepValidation` hook
that:
- Takes a Zod schema + the form draft
- Returns `{ ok, errors: { field, message }[] }` — same
  shape as the existing `WizardError[]`
- 4-step migration pattern documented for future steps

**Pilot scope**: ONLY `StepLLM` is migrated. The 6 other
wizard steps keep their hand-rolled validation. Sprint 64+
can migrate the rest if the pilot succeeds.

**API**:
```ts
import { z } from "zod";
import { useStepValidation } from "@/hooks/useStepValidation";

const llmSchema = z.object({
  provider: z.enum(["minimax", "openai", "anthropic", "ollama"]),
  api_key: z.string().min(1, "API key is required"),
  base_url: z.string().url("Base URL must be a valid URL"),
  default_model: z.string().min(1, "Default model is required"),
  fallback_model: z.string().optional(),
});

function useStepValidation<T>(
  schema: z.ZodType<T>,
  draft: T,
): { ok: boolean; errors: { field: string; message: string }[] } { ... }
```

**Tests** (`hooks/useStepValidation.test.ts`, NEW ~150 LoC,
6-7 tests):
1. Valid draft → `ok=true`, `errors=[]`
2. Empty API key → `ok=false`, `errors=[{field:"api_key", message:"API key is required"}]`
3. Invalid URL → `ok=false`, `errors=[{field:"base_url", ...}]`
4. Multiple errors → all reported
5. Re-validates on draft change (memoised via the hook)
6. Schema is type-safe (TS error if schema doesn't match T)

**Adopter**: `StepLLM` — refactor to call `useStepValidation`
+ merge the result into the existing `errors` prop. Other
wizard steps unchanged in Sprint 63.

### U-A2 (cont.) — Card in audit route (~10 LoC adoption)

**The problem**: Sprint 62 added `Card` but only 1 site
adopted (`routes/setup/index.tsx`). The audit route still
uses the gundam-specific `HudCard` (from the Sprint 61
audit split). The audit page sits inside the cockpit shell
on desktop, so the gundam accent is acceptable — but the
`data-testid="audit-filters"` card would benefit from the
generic Card's clean structure (no `!border-[var(--accent)]`
hacks).

**Solution**: 1-line swap in `routes/audit/AuditFilters.tsx`
+ 1 in `routes/audit/AuditList.tsx` + 1 in
`routes/audit/AuditHeader.tsx`. Replace `HudCard` with `Card`
in the 3 audit sub-components.

**Why this matters**: each HudCard adoption in the audit
route adds the gundam accent border + glow that doesn't
fit the "audit" aesthetic. The Card primitive's neutral
border is cleaner for a security/audit log.

**Tests**: 0 new — the existing audit tests still pass (the
data-testids don't change).

### A-A4 — EQ editor UI skeleton (~80 LoC + tests)

**The problem**: the per-USER override (Sprint 62) is
"all or nothing" — the user picks one of the 8 theme presets
and applies it wholesale. Per-band sliders would let the user
fine-tune (e.g. "NT-D's look, but with +2dB more bass").
This is the first step of a 2-sprint feature:
- Sprint 63: UI skeleton (5 sliders, no audio changes)
- Sprint 64: wire to a new `useEqEditor` store + audio
  feedback (the actual editing)

**Solution**: extend `CockpitEqCard` with a "Edit" button
that toggles between read-only and edit mode. In edit
mode, 5 sliders (one per band) appear. Slider values
display in dB (-12 to +12 range). Sprint 63 wires the
sliders to local state; Sprint 64 wires them to the
audio graph.

**State** (Sprint 63, local-only):
- `editMode: boolean` — toggled by the Edit button
- `localGains: [number, number, number, number, number]` —
  per-band gain values (dB)

**UI**:
- 5 vertical sliders OR 5 horizontal sliders with dB labels
- Band 1: 100Hz (low shelf)
- Band 2: 250Hz (peaking)
- Band 3: 1kHz (peaking)
- Band 4: 2.5kHz (peaking)
- Band 5: 6kHz (high shelf)
- Each: -12dB to +12dB, step 0.5dB
- "Apply" + "Reset" buttons (no-op in Sprint 63; Sprint 64
  wires them to `useEqStore`)

**Tests** (`components/gundam/CockpitEqCard.test.tsx`,
extend existing, +3-4 tests):
1. Edit button toggles `editMode`
2. Edit mode renders 5 sliders
3. Slider change updates `localGains`
4. Cancel button resets `localGains` to current preset

**Note**: The audio graph does NOT change in Sprint 63. The
sliders update local state only. Sprint 64 wires the sliders
to `TtsAudioGraph.setBandGain(band, gainDb)`.

---

## 3. Out of scope (deferred to Sprint 64+)

- **W-A4 (full)** — migrate the other 6 wizard steps to
  Zod (Sprint 64+).
- **X-A3 — Lighthouse + axe CI gate**: Sprint 64+ (needs
  product sign-off on the perf budget + a11y score).
- **X-A1 — Coverage CI gate**: Sprint 64+.
- **A-A4 (full)** — wire EQ editor sliders to audio graph
  (Sprint 64). This sprint is the UI skeleton only.
- **Per-USER EQ persistence** to localStorage: Sprint 64+
  (UX review needed first).
- **Card primitive adoption in 8 settings tabs**: Sprint
  64+ (mechanical work, low risk).

---

## 4. Definition of done

- [ ] `zod` installed + a new `hooks/useStepValidation.ts`
  with 6-7 unit tests
- [ ] `StepLLM` migrates to the new hook (no behavior change
  for the user; tests still pass)
- [ ] `routes/audit/AuditFilters.tsx` / `AuditList.tsx` /
  `AuditHeader.tsx` swap `HudCard` → `Card` (3 sites)
- [ ] `CockpitEqCard` Edit button + 5 sliders + Apply/Reset
  (UI only, no audio change)
- [ ] **310+/310+ vitest pass in 62+ test files** (was 295/295
  in 61 files; +1 file for useStepValidation, +13 tests
  across hook + CockpitEqCard)
- [ ] **0 new tsc errors** (4 pre-existing `auth-bootstrap.test.ts`
  from Sprint 48 still allowed)
- [ ] CHANGELOG entry above Sprint 62
- [ ] `__version__` bumped 0.3.1 → **0.3.2** (PATCH — pilot +
  adoption + skeleton; no breaking change)
- [ ] All 4 version surfaces synced
- [ ] Senior-engineer audit findings resolved (or documented
  as deferred)
- [ ] 1 single commit (or 2 if diff > 1500 LoC; estimate ~700
  LoC net so single commit is fine)

---

## 5. Senior-engineer audit checklist

1. **`zod` bundle size** — verify the dep doesn't blow past
   50KB gzipped (audit page is the only consumer in this
   sprint). Use `du -sh node_modules/zod` after install.
2. **Zod schema drift** — the `LLMConfig` type already exists
   in `types/api.ts`. The Zod schema in `useStepValidation`
   must derive from (or match) the existing TS type. A drift
   would surface as a runtime error. Test: the schema
   accepts a valid LLMConfig and rejects malformed input.
3. **useStepValidation memoisation** — the hook MUST memo
   the result on `draft` change. Without memo, every
   keystroke re-validates 100+ fields.
4. **`zod` version** — pin to a stable 3.x release (4.x is
   in beta as of 2026-07; 3.x is production-safe).
5. **Card adoption visual diff** — `HudCard` and `Card`
   look slightly different (border, padding). Run a manual
   smoke test in the audit page after adoption to confirm
   the visual is acceptable.
6. **EQ editor slider a11y** — sliders MUST have
   `aria-label` (e.g. "100 Hz low shelf gain in dB") + a
   visible numeric readout. Sprint 64 may also add keyboard
   support (arrow keys, +/-). The Sprint 63 skeleton just
   needs `<input type="range" aria-label="...">`.
7. **Edit button visibility** — the Edit button is the
   FIRST "EQ EDITOR" affordance in the cockpit. It MUST
   be discoverable. Place it next to the existing
   "Compare:" row.
8. **Carry-over rules** — Card adoptions MUST preserve
   `data-testid` for downstream consumers; new hook tests
   follow Sprint 61's "≥4 tests" rule; new deps follow
   Sprint 61's "review bundle size + rollback + CHANGELOG"
   rule (zod is a known-stable dep, low risk).

---

## 6. Commit plan (single commit, ~700 LoC net)

```
[main]
  fcc58ba Sprint 62 (in-session) — Per-USER EQ + A/B compare + Card primitive
  xxxxxx  Sprint 63 (in-session) — Zod pilot + Card adoption + EQ editor skeleton
          (useStepValidation + StepLLM pilot + audit Card swap + EQ sliders,
          refactor + 1 new dep, 0.3.1→0.3.2)
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
- **NEW (this sprint)**: Zod schema migration is a
  one-step-at-a-time pilot. Migrations of >1 step per
  sprint are forbidden (each step has its own quirks;
  bulk migration would obscure the lessons learned).
- **NEW (this sprint)**: EQ editor UI changes (Sprint 63
  + 64) MUST be reviewed by a senior-engineer before any
  audio change lands. The Sprint 63 skeleton is UI-only
  on purpose.

---

## 8. Effort estimate

| Item | LoC +/- | Time |
| ---- | --- | --- |
| W-A4: zod install + useStepValidation + StepLLM pilot | +200 / -30 | 1.5h |
| U-A2 cont: Card adoption in 3 audit sub-components | +5 / -5 | 30min |
| A-A4: EQ editor UI skeleton | +120 / -10 | 1.5h |
| Audit + commit + push + CHANGELOG + version | +80 / -3 | 30min |
| **Total** | **+405 / -48** | **~4h** |

Result: 295 → ~310 tests passing (+15 tests, +1 file). 1 new
dep (`zod@3`).
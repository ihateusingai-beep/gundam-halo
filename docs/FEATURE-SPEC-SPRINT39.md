# Sprint 39 — Dashboard polish: 4 cards + voice eval results endpoint

**Date**: 2026-06-25
**Status**: Draft
**Author**: Mavis
**Priority**: Medium (UX gap — backend has been feature-complete since Sprint 42)

## Goal

Now that the backend is feature-complete (Sprint 37 voice cold-start, Sprint 38 held-out
eval plumbing, Sprint 42 security hardening), the **frontend dashboard is the gap**.
Pilots still see the same 2018-era grid of cards that the 2026-06-04 launch shipped,
and the new backend capabilities (held-out eval, setup wizard, model swap) are
invisible unless the user digs through `~/.gundam-halo/logs/`.

Sprint 39 ships **4 new cockpit cards** + **1 new backend endpoint** that turn the
hidden backend into a one-glance cockpit:

1. **`SetupWizard` card** — render the M13 first-run wizard's current step on the
   home page, with a "resume" link to `/setup`. The wizard already exists in
   `backend/app/api/setup.py` and `setup_state.py` (Sprint 30); Sprint 39 just
   surfaces its state. (Backend status: **the wizard is implemented, but users
   don't know it's running.**)
2. **`HeldOutEvalCard` card** — read the latest WER from the new
   `GET /voice/eval-results` endpoint, show pass/fail vs the
   `~/.gundam-halo/test-config.toml` threshold, and render a tiny SVG sparkline of
   the last 7 runs from the trend JSON. (Backend status: **plumbing ships in
   Sprint 38; UI gate ships in Sprint 39.**)
3. **`VoiceWsIndicator` card** — surface the live `/ws/voice` connection state
   (`idle|ready|listening|thinking|speaking|reconnecting|error`) with a colored
   pill + auto-reconnect countdown. (Backend status: **already exposed via
   `getVoiceStatus()` in `services/halo-voice-ws.ts`**; we just plumb it into the
   home grid.)
4. **`ModelSwapDialog` card** — confirm modal for the Sprint 33b
   `invoke('activate_model')` IPC. Show a `toml_edit` diff preview of which
   config.toml fields will change before the user clicks "Activate". (Backend
   status: **IPC exists, but the activation has no preview / confirm dialog**.)

Plus the **1 new backend endpoint** `GET /voice/eval-results` that reads the
Sprint 38 trend JSONs from `tests/voice/held_out_results/*.json` and returns the
latest run + last 7 entries for the sparkline.

## Scope

### In scope

**Backend** (`~/workspace/working/gundam-halo/backend/`):
- New endpoint `GET /voice/eval-results` in `app/api/voice_config_api.py`
  — returns `{ latest: EvalRunSummary | null, history: EvalRunSummary[] }`
  where history is the last 7 runs (most recent first).
- New helper `app/voice/held_out_eval.py::load_eval_history(home, limit=7)` —
  reads `tests/voice/held_out_results/*.json`, sorted by `timestamp_ms` desc.
- 3 pytest tests for the new endpoint:
  - Empty directory → `{ latest: null, history: [] }`
  - 10 trend JSONs → `latest` is the newest, `history` is 7 most recent
  - Corrupted JSON (missing fields) → endpoint skips + continues (graceful)
- Update `app/__init__.py` `__version__` 0.1.12 → **0.1.13** (frontend-side
  feature, but backend surface sync per Mavis memory rule)

**Frontend** (`~/workspace/working/gundam-halo/frontend/`):
- New `components/dashboard/SetupWizard.tsx` — reads `/api/setup/state` on
  mount; if `status === "in_progress"` or `current_step < 8`, renders the
  yellow "Setup incomplete (step N/8)" HudCard with a `<Link to="/setup">`
  "Resume setup" button.
- New `components/dashboard/HeldOutEvalCard.tsx` — fetches
  `/voice/eval-results`, renders HudCard with: latest WER (big number),
  pass/fail badge (cyan=pass / pink=fail / grey=no data), and a 60×24 SVG
  sparkline showing WER over last 7 runs.
- New `components/dashboard/VoiceWsIndicator.tsx` — subscribes to
  `getVoiceStatus()` on a 2s interval (matches existing pattern in
  `routes/settings/VoiceTab.tsx:127`); renders a small HudCard with colored
  pill: cyan=ready / blue=listening / magenta=thinking / orange=speaking /
  pink=reconnecting / red=error.
- New `components/dashboard/ModelSwapDialog.tsx` — `<button>` that opens
  shadcn `<Dialog>` from `components/ui/dialog.tsx`; the dialog body shows a
  diff preview (active backend `whisper_local` → proposed `whisper_hf` +
  model path), then a yellow "Activate" button that fires
  `invoke('activate_model', { checkpointPath })` via `__TAURI__`.
- Update `routes/index.tsx` — add a new section below the existing "Mission
  Roster" grid: "System Status" 2×2 grid of the 4 cards.
- Update `routes/setup/index.tsx` — if it exists, link the new SetupWizard
  card to it. If not, create a minimal one (it'll be filled in Sprint 40).
- 4 vitest tests (one per component) — render with mocked fetches /
  `getVoiceStatus()` / `invoke`; assert the right HUD state per input.
- Bump `frontend/package.json`, `frontend/src-tauri/Cargo.toml`,
  `frontend/src-tauri/tauri.conf.json` from `0.1.7` → **`0.1.13`**
  (per Mavis memory rule: 4-surface sync)

**Docs**:
- Update `docs/CHANGELOG.md` [Unreleased] section with Sprint 39 entry
- Update `docs/tickets/M9-E.md` — add Sprint 39 row to acceptance table
- Update `docs/DASHBOARD.md` — add the 4 cards to the home page mockup
- This spec (`docs/FEATURE-SPEC-SPRINT39.md`)

### Out of scope

- **Sprint 40** (live held-out eval run): user records 30s, runs
  `scripts/run_held_out_eval.py`, sees real WER. Plumbing ships Sprint 38;
  UI ships Sprint 39; **live run is the user's next step**.
- **Sprint 41** (Tailscale auth + live MINIMAX_API_KEY + hermes bridge):
  the wizard already supports all 3 (Sprint 30); what Sprint 39 ships is
  just the dashboard card that links to the wizard. The actual Tailscale
  login flow is a separate sprint (involves OAuth + browser tab).
- **Sprint 43** (personalised fine-tune end-to-end): the Sprint 33b Tauri
  commands are wired; the ModelSwapDialog is the final UI gate. But the
  actual training run (30-min self-record corpus → LoRA fine-tune →
  checkpoint swap) is out of scope here — that's a separate user-driven
  step.
- **iOS / Android mobile cards**: the 4 cards are desktop-only in Sprint 39.
  The mobile layout (existing per profile memory "vertical stack on phone")
  will rearrange automatically via the existing Tailwind grid; we don't
  touch mobile breakpoints in Sprint 39.
- **Push notifications / Sonner toasts**: no toasts added in Sprint 39. The
  cards update silently on poll; the user sees them when they look at the
  dashboard. Adding toast spam on every WS state change would be
  counterproductive.
- **Internationalisation (i18n)**: all copy is English. The cockpit already
  has no i18n framework (per Sprint 19c lock), and adding one for 4 cards
  is overkill.

## Why now

Sprint 37 (voice cold-start) + Sprint 38 (held-out eval plumbing) + Sprint 42
(`/api/health` + Tailscale ACL docs + TOML fail-loud) are all backend-only.
The cockpit's home page (`routes/index.tsx`) still renders the same Mission
Select + Mission Roster it shipped with on 2026-06-04. Users can:
- Run the setup wizard manually, but don't see a "step N/8" reminder on the
  home page.
- Run `scripts/run_held_out_eval.py` manually, but the WER trend isn't
  visible from the cockpit.
- See the voice WS state in `/settings/voice`, but not from the home page.
- Trigger model swap via `/settings/voice`, but without a diff preview of
  what `config.toml` will look like after the swap.

All four capabilities are now hidden in settings tabs and CLI scripts. Sprint
39 fixes that by surfacing them on the home page where the pilot lands by
default.

## Implementation

### Backend: `GET /voice/eval-results`

Add to `app/api/voice_config_api.py`:

```python
@router.get("/voice/eval-results")
def get_voice_eval_results(home: Path = Depends(get_halo_home)) -> dict:
    """Latest held-out eval results (Sprint 38 trend JSONs).

    Reads from `tests/voice/held_out_results/*.json` (under HALO_HOME),
    returns the most recent run + last 7 entries for the dashboard
    sparkline. Graceful: skips corrupted JSONs (missing fields, bad
    timestamp); if directory is empty or missing, returns empty list.

    Returns:
        {
            "latest": EvalRunSummary | null,
            "history": list[EvalRunSummary],   # most recent first, max 7
            "threshold_pct": float,              # from test-config.toml or default 15.0
        }
    """
    from app.voice.held_out_eval import load_eval_history
    history = load_eval_history(home / "tests" / "voice" / "held_out_results", limit=7)
    latest = history[0] if history else None
    threshold = load_wer_threshold(home / "test-config.toml")  # default 15.0
    return {"latest": latest, "history": history, "threshold_pct": threshold}
```

`load_eval_history(home_results_dir, limit)` (added to `held_out_eval.py`):

- Globs `*.json` in `tests/voice/held_out_results/` (already gitignored except
  `.gitkeep` per Sprint 42).
- Parses each as `EvalRunSummary` (existing dataclass from Sprint 38).
- Sorts by `timestamp_ms` desc; takes the top `limit`.
- Catches `(json.JSONDecodeError, KeyError, ValueError)` per file, logs a
  warning, continues. Never crashes the whole endpoint on one bad file.

### Frontend: `routes/index.tsx` new section

Add below the existing Mission Roster:

```tsx
{/* Sprint 39 — System Status (2x2 grid of dashboard cards) */}
<section aria-label="System Status" className="space-y-4">
  <h2 className="text-xs font-[Orbitron] uppercase tracking-widest
                 text-[var(--text-muted)]">
    System Status
  </h2>
  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
    <SetupWizard />
    <VoiceWsIndicator />
    <HeldOutEvalCard />
    <ModelSwapDialog />
  </div>
</section>
```

The 4 cards are desktop-side 2×2; on mobile they stack vertically (existing
Tailwind grid handles this — no media query changes).

### `HeldOutEvalCard` data shape

```ts
type EvalRunSummary = {
  timestamp_ms: number;
  wer_pct: number;
  passed: boolean;
  wav_path: string;     // absolute path on pilot's Mac
  asr_backend: string;  // "whisper_local" | "whisper_hf"
  duration_sec: number;
};

type EvalResultsResponse = {
  latest: EvalRunSummary | null;
  history: EvalRunSummary[];     // most recent first, max 7
  threshold_pct: number;         // e.g. 15.0
};
```

### Sparkline (zero-dep SVG)

60×24 px, 7 points max. Polyline `points="x1,y1 x2,y2 ..."` with `stroke="cyan"`,
no axis labels. Renders `<empty state>` if `history.length === 0`. Implementation
follows the existing zero-dep SVG pattern from Sprint 22 (per Mavis memory
"web-frontend-patterns.md — zero-dep SVG chart").

### Card component shapes

Each card is a thin wrapper around the existing `<HudCard>` from
`components/gundam/HudCard.tsx` (26 LoC, no changes needed):

```tsx
// SetupWizard
<HudCard pulse={state.status === "in_progress"}>
  <div data-testid="setup-wizard-card">
    <span className="text-xs uppercase">Setup</span>
    <h3 className="text-lg">{label}</h3>  // e.g. "Step 3 of 8" or "Complete"
    <Link to="/setup">{cta}</Link>          // "Resume" or "Review"
  </div>
</HudCard>
```

```tsx
// HeldOutEvalCard
<HudCard>
  <div data-testid="held-out-eval-card">
    <span className="text-xs uppercase">Voice Eval</span>
    {latest ? (
      <>
        <h3>{latest.wer_pct.toFixed(1)}% WER</h3>
        <span data-passed={latest.passed}>{latest.passed ? "PASS" : "FAIL"}</span>
        <svg data-testid="wer-sparkline" ...>...</svg>
      </>
    ) : (
      <p>No evals yet. Run scripts/record-held-out.sh to start.</p>
    )}
  </div>
</HudCard>
```

```tsx
// VoiceWsIndicator
<HudCard>
  <div data-testid="voice-ws-indicator">
    <span className="text-xs uppercase">Voice Link</span>
    <h3>{voiceStatus.state}</h3>
    <div data-state={voiceStatus.state} className="w-2 h-2 rounded-full" />
    {voiceStatus.lastAsr && <p>Last: "{voiceStatus.lastAsr}"</p>}
  </div>
</HudCard>
```

```tsx
// ModelSwapDialog
<HudCard>
  <div data-testid="model-swap-card">
    <span className="text-xs uppercase">Voice Model</span>
    <h3>{currentModel ?? "default (whisper_local)"}</h3>
    <Dialog>
      <DialogTrigger asChild>
        <button>Activate personalised model...</button>
      </DialogTrigger>
      <DialogContent>
        {/* diff preview, Activate button */}
      </DialogContent>
    </Dialog>
  </div>
</HudCard>
```

## Test plan

### Backend (pytest)

`tests/api/test_voice_eval_results.py` — 3 new tests:

1. **Empty directory**: `home/tests/voice/held_out_results/` exists but has
   no JSONs (or doesn't exist at all) → response `{ latest: null, history: [],
   threshold_pct: 15.0 }`.
2. **10 trend JSONs**: write 10 fake `EvalRunSummary` JSONs with
   `timestamp_ms` from 1..10; assert `latest.timestamp_ms == 10`,
   `history.length == 7`, `history[0].timestamp_ms == 10`,
   `history[6].timestamp_ms == 4`.
3. **Corrupted JSON**: write 5 valid + 1 with `"wer_pct": "not-a-number"` +
   1 with missing `timestamp_ms`; assert response has 5 entries (the
   corrupted ones silently dropped), `latest` is the newest valid one.

Plus a smoke test on `load_eval_history()` directly (no FastAPI):
`tests/voice/test_load_eval_history.py` — 4 tests covering sort order,
limit, empty dir, corrupted file skipping.

### Frontend (vitest)

`src/components/dashboard/SetupWizard.test.tsx` — 1 test:
- Mocks `fetch('/api/setup/state')` to return `{ status: 'in_progress',
  current_step: 3, completed_steps: [1, 2] }`; asserts HudCard renders
  "Step 3 of 8" + "Resume setup" link to `/setup`.

`src/components/dashboard/HeldOutEvalCard.test.tsx` — 1 test:
- Mocks `fetch('/voice/eval-results')` to return 3 valid runs (WERS
  18%, 14%, 12%, threshold 15); asserts latest shows "12.0% WER" + "PASS"
  + sparkline has 3 polyline points.

`src/components/dashboard/VoiceWsIndicator.test.tsx` — 1 test:
- Mocks `getVoiceStatus()` to return `state: "reconnecting"`; asserts
  the colored pill has `data-state="reconnecting"` + label "RECONNECTING".

`src/components/dashboard/ModelSwapDialog.test.tsx` — 1 test:
- Renders with `currentModel="default"`; clicks "Activate" button; asserts
  the `<Dialog>` opens + diff preview shows `whisper_local → whisper_hf`
  + does NOT fire `invoke()` until the "Confirm" button is clicked.

### Manual smoke

- Start the backend (`./run.sh`), open `http://localhost:8765/` (or
  whatever the user has set), confirm the 4 new cards appear below the
  Mission Roster.
- Click "Resume setup" → confirm `/setup` page loads (or stub message if
  not yet implemented).
- Open VoiceTab in another tab → return to home; confirm the
  VoiceWsIndicator pill reflects the current state.
- Click "Activate personalised model" → confirm the dialog opens with
  diff preview; click "Cancel" (no invoke); click "Activate" again +
  "Confirm" → confirm `invoke('activate_model')` fires (check via
  `window.__haloTauri`).

## Acceptance criteria

1. **Backend**: `pytest tests/api/test_voice_eval_results.py
   tests/voice/test_load_eval_history.py -v` → all green.
2. **Frontend**: `cd frontend && pnpm test:run
   src/components/dashboard/` → 4 test files green.
3. **TypeScript**: `cd frontend && pnpm tsc --noEmit` → 0 errors.
4. **Rust**: `cd frontend/src-tauri && cargo check` → 0 errors.
5. **Full backend tests**: `cd backend && .venv/bin/python -m pytest -x -q`
   → all green (target: 1245+3+4 = **1252 passed, 0 failed**).
6. **Home page renders 4 cards**: open cockpit, see SetupWizard,
   HeldOutEvalCard, VoiceWsIndicator, ModelSwapDialog below the Mission
   Roster; mobile view stacks them vertically.
7. **`/voice/eval-results` works**: `curl localhost:8765/voice/eval-results`
   returns valid JSON with `latest` + `history` + `threshold_pct`.
8. **No live eval data needed**: the 4 cards render gracefully when the
   trend JSON dir is empty (no crashes, no empty sparklines).

## Risks & mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| `getVoiceStatus()` polling causes perf issues on home page | Low | 2s interval matches VoiceTab; HudCard is memoized; polling only happens when the card is mounted (page is open). |
| `/api/setup/state` doesn't exist yet | **Confirmed** (no UI consumer) | Card handles `fetch` error → shows "Setup unavailable" instead of crashing |
| `/voice/eval-results` returns 404 if user hasn't run setup | Low | Backend endpoint always returns 200 (empty list if dir missing); FE handles `latest === null` with empty state |
| Sparkline SVG looks bad on retina | Low | Use `viewBox="0 0 60 24"` + no `width`/`height` attrs → scales with CSS |
| `Dialog` component crashes on SSR | **N/A** | Tauri app only, no SSR |
| VoiceWsIndicator shows stale state if WS dies silently | Medium | 2s poll catches up within 2s; `state === "reconnecting"` is the explicit signal that the base client is auto-reconnecting (Sprint 32 P1.2) |
| ModelSwapDialog fires `invoke` on `__TAURI__` undefined (web mode) | Medium | Guard: `if (typeof window !== "undefined" && "__TAURI_INTERNALS__" in window) { invoke(...) }` else show "Tauri only" error |

## Success metrics

- Home page load time stays under 500 ms (4 new cards each make one
  `fetch`; total < 50 ms with FastAPI localhost).
- All 4 cards are keyboard-accessible (tab order matches visual order).
- Mobile (375 px width) layout stacks the 4 cards vertically with no
  horizontal scroll.
- Card copy fits on one line on desktop (no truncation) and wraps
  gracefully on mobile.

## Post-merge

- Update `docs/tickets/M9-E.md` — mark Sprint 39 done; move on to
  Sprint 40 (live eval run).
- Add a "Dashboard cards" section to `docs/DASHBOARD.md` with a
  screenshot of the new home page layout.
- Bump `backend/app/__init__.py` and the 3 frontend surfaces to
  `0.1.13` per Mavis memory rule.
- Single commit: `feat(dashboard): Sprint 39 — 4 dashboard polish cards
  (SetupWizard/HeldOutEvalCard/VoiceWsIndicator/ModelSwapDialog) +
  /voice/eval-results endpoint`.
- Run `git status` after the commit (per memory rule "git add -A safety
  check") to confirm only the expected files are staged.

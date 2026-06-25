# Sprint 44 — 8-Step Setup Wizard UI (F from 2026-06-26 design review)

**Date**: 2026-06-26
**Status**: Draft
**Author**: Mavis
**Priority**: P0 (user-confirmed pain: 10-15min first-run; goal < 90s)
**Depends on**: Sprint 39 (SetupWizard card + `/setup` route stub + `api.getSetupState`), Sprint 43 (BackendHealthBanner for step 0 health check)

## Goal

The M13 setup wizard **backend is complete** (11 endpoints, 979 LoC of
`app/api/setup.py`, 38 tests in `tests/api/test_setup.py`, atomic write,
secrets_store integration for API keys, Tailscale reachability probe).
**The frontend is a 40-LoC stub** at `routes/setup/index.tsx` that just
shows a "coming soon" message.

Sprint 44 builds the **UI for the 7-step wizard** (steps 1-7, with
optional pre-step 0 health gate + post-step finish screen):

1. **Step 1 — Welcome** (intro screen + "Let's go" CTA)
2. **Step 2 — LLM Provider** (paste MiniMax / OpenAI / Anthropic / Ollama API key; inline validation)
3. **Step 3 — Voice ASR** (pick backend: `whisper_local` / `sherpa` / `yuesub`)
4. **Step 4 — Voice TTS** (pick backend + voice; live preview TTS button)
5. **Step 5 — Theme** (pick 1 of 8 themes with live preview swatch)
6. **Step 6 — Tailscale** (optional; hostname + reachability test)
7. **Step 7 — Smoke test** (auto-runs text + voice round-trip; auto-advances on pass)
8. **Finish** — success screen + "Open cockpit" CTA

Pre-step gate (Sprint 43 dependency): if `BackendHealthBanner` shows
unhealthy, the wizard blocks with "Backend is restarting — try again
in 30s" rather than letting the user fill 7 steps against a dying
backend.

**Why now**: Per the 2026-06-26 design review, **F is P0** because
onboarding time is user-confirmed painful (10-15min, per Sprint 37
records). Goal: **< 90s from app open to first voice turn**. The
backend is ready — only the UI is missing.

## Scope

### In scope

**Frontend only** — backend wizard is complete:

- Replace `frontend/src/routes/setup/index.tsx` (~40 LoC stub) with
  full wizard (~700 LoC).
- New `frontend/src/components/wizard/` directory:
  - `WizardShell.tsx` (~80 LoC) — step indicator dots + nav (Back / Next /
    Skip) + error display
  - `StepWelcome.tsx` (~60 LoC) — step 1
  - `StepLLM.tsx` (~180 LoC) — step 2; the most complex (inline API key
    validation, 4 providers, model pickers)
  - `StepVoiceASR.tsx` (~120 LoC) — step 3
  - `StepVoiceTTS.tsx` (~150 LoC) — step 4; live TTS preview button
  - `StepTheme.tsx` (~100 LoC) — step 5; 8 themes with preview swatch
  - `StepTailscale.tsx` (~80 LoC) — step 6; optional
  - `StepSmoke.tsx` (~120 LoC) — step 7; auto-runs + auto-advances
  - `StepFinish.tsx` (~60 LoC) — success screen
  - `hooks/useSetupWizard.ts` (~150 LoC) — state machine: current step,
    completed steps, error retry, skip semantics
  - `lib/setup-api.ts` (~100 LoC) — typed wrapper around the 11
    `/api/setup/*` endpoints (mirrors `lib/api.ts` pattern)
- `frontend/src/types/api.ts` — add `SetupStep`, `SetupStepPayload`,
  `LLMConfig`, `VoiceASRConfig`, `VoiceTTSConfig`, `ThemeConfig`,
  `TailscaleConfig` types (~80 LoC)
- 7 vitest tests (one per step component + one for the state machine
  hook) — ~350 LoC
- 2 backend pytest tests added to `tests/api/test_setup.py`:
  - `test_setup_state_returns_partial_after_step_2_only` — confirms
    state survives mid-wizard crash (the e2e we'll do manually)
  - `test_setup_finish_blocked_when_smoke_not_run` — confirms step 7
    gate works

**Docs**:
- `docs/SETUP-WIZARD.md` NEW (~150 LoC) — user-facing walkthrough:
  - The 7 steps in plain language with screenshots
  - "Why each step exists" (so user doesn't skip by reflex)
  - "What to do if a step fails" (the 4 common error cases)
  - "Skip the wizard" — when + how
- Update `docs/FEATURE-SPEC-SPRINT44.md` (this file)
- Update `docs/CHANGELOG.md` [Unreleased]
- Update `docs/DASHBOARD.md` — link to `/setup` walkthrough
- Update `docs/tickets/M13.md` if it exists (else create stub)

### Out of scope

- **Backend wizard changes** — already complete + tested. No
  `/api/setup/*` endpoint will change.
- **Multi-user wizard** — single-user assumption holds (per project
  convention; tracked in M12 hardening backlog).
- **Wizard i18n** — English-only v1; bilingual comes if Sprint 45+
  proves the demand.
- **Wizard dark/light theme variants** — uses existing `data-theme`
  system; no new CSS.
- **Voice preview on Step 4** uses the existing TTS pipeline (no
  preview-specific TTS call). If the user picks a voice and the
  backend hasn't booted voice yet, the preview button gracefully
  shows "Voice not configured yet — try after step 7".
- **Step 0 health gate** is a render-only check (it uses
  `BackendHealthBanner`'s IPC); no new wizard state.
- **"Reset wizard" UI button** — exists at backend (`POST /api/setup/reset`)
  but not surfaced in Sprint 44. The Settings page will get this in
  Sprint 45.
- **Auto-fill from existing config.toml** — if the user has already
  filled `~/.gundam-halo/config.toml` manually before opening the
  wizard (e.g. via README install instructions), the wizard still
  walks them through all 7 steps. **No "skip to step N if your
  config is already complete" auto-detection** — that would add
  UI complexity for a rare case. Tracked as future enhancement.

## Why now

Per Sprint 37 records, the cold-start path was:

1. Install deps (3-5 min via `uv sync --all-extras`)
2. Edit `~/.gundam-halo/.env` with API key (30s, but **risky** —
   user often pastes into chat instead — see memory rule "永遠唔
   接受 raw secret")
3. Edit `~/.gundam-halo/config.toml` (~5 min; user has to read the
   60 LoC example file to know what to set)
4. Restart backend (5s for launchd; 30s for manual)
5. First voice turn (success: 2-5s)

**Total**: 10-15 min for the first successful voice turn.

Sprint 44 collapses steps 2-4 into the wizard UI:
- Step 2 (LLM): paste key → wizard writes to secrets_store (.env
  with chmod 600 automatically, per memory rule)
- Step 3 (ASR): dropdown → wizard writes to config.toml
- Step 4 (TTS): dropdown → wizard writes to config.toml
- Step 5 (Theme): pick → wizard writes + immediately applies
- Step 6 (Tailscale): optional skip
- Step 7 (Smoke): auto-runs

**Target**: 90s from `/setup` page open to step 7 PASS. The
backend restart still happens but it's transparent (the wizard's
"smoke test" step waits for it).

## Implementation

### State machine (`hooks/useSetupWizard.ts`)

```ts
/**
 * useSetupWizard — single source of truth for the wizard's
 * UI state. Mirrors the backend's `compute_setup_state()`
 * but holds the local form state for fields the user is
 * currently editing.
 *
 * Step lifecycle:
 *   1. Mount → call api.getSetupState() → seed initial step
 *   2. User clicks "Next" → POST /api/setup/<step-endpoint>
 *   3. On success → advance current_step
 *   4. On error → display field-level errors, stay on step
 *
 * Crash recovery: the backend's `setup_state.json` is the
 * source of truth for "what step are we on". If the wizard
 * crashes mid-flow, the next mount picks up where we left off.
 * We DO NOT cache the wizard's form state in localStorage —
 * that's extra complexity for a flow that takes 90s.
 */
type WizardStep = 1 | 2 | 3 | 4 | 5 | 6 | 7;
type WizardStatus = 'loading' | 'active' | 'submitting' | 'error' | 'finished';

interface UseSetupWizardResult {
  status: WizardStatus;
  currentStep: WizardStep;
  completedSteps: WizardStep[];
  errors: Array<{ field: string; code: string; message: string }>;
  
  // Per-step submit handlers.
  submitLLM: (cfg: LLMConfig) => Promise<void>;
  submitASR: (cfg: VoiceASRConfig) => Promise<void>;
  submitTTS: (cfg: VoiceTTSConfig) => Promise<void>;
  submitTheme: (cfg: ThemeConfig) => Promise<void>;
  submitTailscale: (cfg: TailscaleConfig) => Promise<void>;
  runSmoke: () => Promise<void>;
  
  finish: () => Promise<void>;
  skip: () => Promise<void>;
  reset: () => Promise<void>;
  
  // Form state for each step (controlled inputs).
  llmForm: LLMConfig;
  asrForm: VoiceASRConfig;
  ttsForm: VoiceTTSConfig;
  themeForm: ThemeConfig;
  tailscaleForm: TailscaleConfig;
  
  setLlmForm: (cfg: LLMConfig) => void;
  setAsrForm: (cfg: VoiceASRConfig) => void;
  setTtsForm: (cfg: VoiceTTSConfig) => void;
  setThemeForm: (cfg: ThemeConfig) => void;
  setTailscaleForm: (cfg: TailscaleConfig) => void;
}
```

### Per-step component contract

Each step is a controlled form that renders fields + a single
"Next" / "Back" footer. The shell handles navigation; the
step just submits when "Next" is clicked.

```tsx
// StepLLM.tsx (most complex — step 2)
export function StepLLM({ form, setForm, onSubmit, errors, busy }) {
  // 1. Provider dropdown (4 options)
  // 2. API key input (password type; "show" toggle)
  // 3. Inline validate button — calls a separate endpoint
  //    `POST /api/setup/llm/validate` (NEW, ~30 LoC backend)
  //    that ONLY tests the key without saving
  // 4. Base URL (auto-fills based on provider)
  // 5. Default model dropdown (auto-fills based on provider)
  // 6. Fallback model (optional)
  
  // On submit, write form to localStorage as draft (NOT the
  // API key — see note below). On "Next", POST /api/setup/llm.
}
```

### Inline API key validation (new endpoint, 1 sprint + 30 LoC backend)

The user should NOT have to click "Next" to find out their key
is wrong. We add `POST /api/setup/llm/validate` that runs the
same `_test_llm_connection()` helper as `/api/setup/llm` but
without persisting anything.

```python
@router.post("/llm/validate", response_model=dict[str, Any])
async def post_setup_llm_validate(payload: LLMSetupRequest) -> dict[str, Any]:
    """Sprint 44 — inline validation before the user clicks Next.
    
    Mirrors /llm's connection test but skips the TOML write.
    Returns {ok: bool, model: str | null, error: str | null}.
    """
    ok, model, err = await _test_llm_connection(payload)
    return {"ok": ok, "model": model, "error": err}
```

This is a 1-line wrapper around the existing `_test_llm_connection()`
helper that the `/llm` endpoint already uses. Add 2 tests.

### Pre-step gate (Step 0 — health check)

Render-only. If `BackendHealthBanner` IPC returns
`{respawn_disabled: true}` OR `{crash_count_60m > 0}`, the wizard
shows a full-page "Backend is unhealthy — fix it first" screen
with a link to the cockpit's health banner. Once the backend is
healthy (polled every 5s), the wizard unlocks.

```tsx
export function SetupWizard() {
  const health = useBackendHealth();  // IPC + 5s poll
  
  if (health.respawn_disabled) {
    return <HealthBlockedScreen reason="respawn_disabled" />;
  }
  if (health.crash_count_60m > 0) {
    return <HealthBlockedScreen reason="recent_crashes" />;
  }
  
  return <WizardShell />;
}
```

### Live TTS preview (Step 4)

The TTS step has a "Preview" button next to each voice option.
Clicking it POSTs to `/api/setup/tts/preview` (NEW, ~40 LoC backend)
that runs a 1-sentence TTS render + returns the audio as a base64
data URL. The frontend plays it inline.

```python
@router.post("/tts/preview", response_model=dict[str, Any])
async def post_setup_tts_preview(payload: TTSPreviewRequest) -> dict[str, Any]:
    """Sprint 44 — render a 1-sentence TTS preview.
    
    Mirrors /voice-tts's save logic but returns the audio bytes
    instead of persisting. Used by the wizard's "Preview voice"
    buttons.
    
    Body: {backend: str, voice: str, text: str = "你好，Unicorn。"}
    Returns: {ok: bool, audio_base64: str | null, error: str | null}
    """
```

If TTS isn't bootable (voice layer not loaded yet), this endpoint
returns `{ok: false, error: "voice_layer_not_loaded"}` and the
frontend shows "Preview unavailable until voice is configured
(after step 7)".

### Theme preview swatch (Step 5)

8 themes × 4 swatches each (background / accent / text / glow).
Render as 8 cards in a 2×4 grid; each card shows the theme's
accent color + name + a 2-line sample. Click → applies theme
locally + writes to backend on "Next".

```tsx
const THEMES = [
  { id: 'gundam-ntd', name: 'NT-D / Unicorn', accent: '#ff2dd4', sample: 'Psychoframe online.' },
  { id: 'gundam-god', name: 'Gundam God', accent: '#ffaa00', sample: 'Divine strike.' },
  // ... 6 more
];

export function StepTheme({ form, setForm }) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
      {THEMES.map(theme => (
        <button
          key={theme.id}
          data-testid={`theme-${theme.id}`}
          onClick={() => {
            setForm({ themeId: theme.id });
            document.documentElement.setAttribute('data-theme', theme.id);
          }}
          className={cn(
            "border-2 p-3 text-left",
            form.themeId === theme.id
              ? "border-[var(--accent)]" 
              : "border-[var(--border-color)]"
          )}
          style={{ borderColor: form.themeId === theme.id ? theme.accent : undefined }}
        >
          <div className="h-8 w-full mb-2" style={{ background: theme.accent }} />
          <div className="text-sm font-[Rajdhani]">{theme.name}</div>
          <div className="text-[10px] text-[var(--text-muted)]">{theme.sample}</div>
        </button>
      ))}
    </div>
  );
}
```

## Test plan

### Frontend (vitest) — 7 tests

`src/components/wizard/StepLLM.test.tsx`:

1. **`test_provider_dropdown_auto_fills_base_url`** — pick "minimax"
   → base_url field auto-fills `https://api.minimax.io/v1`; pick
   "openai" → `https://api.openai.com/v1`.

`src/components/wizard/StepVoiceASR.test.tsx`:

2. **`test_asr_backend_picker_disables_model_field_for_local`** —
   pick `whisper_local` → model_size field enabled; pick
   `sherpa` → model_size field hidden (sherpa uses model_path).

`src/components/wizard/StepVoiceTTS.test.tsx`:

3. **`test_preview_button_calls_tts_preview_endpoint`** — click
   "Preview" with voice "zh-HK" → POST `/api/setup/tts/preview`
   fires with the right body.

`src/components/wizard/StepTheme.test.tsx`:

4. **`test_theme_picker_applies_data_theme_attribute`** — click
   "gundam-ntd" card → `document.documentElement.dataset.theme`
   === "gundam-ntd".

`src/components/wizard/StepSmoke.test.tsx`:

5. **`test_smoke_step_runs_automatically_on_mount`** — mount
   `<StepSmoke />` → POST `/api/setup/smoke` fires within 100ms.

`src/components/wizard/StepTailscale.test.tsx`:

6. **`test_tailscale_skip_button_skips_to_next_step`** — click
   "Skip for now" → POST `/api/setup/skip` fires; on success,
   currentStep advances to 7.

`src/hooks/useSetupWizard.test.ts`:

7. **`test_state_machine_advances_on_successful_submit`** — start
   at step 2, call `submitLLM({...})` (mock 200 response) →
   currentStep becomes 3.

### Backend (pytest) — 3 tests

Add to `tests/api/test_setup.py`:

8. **`test_setup_state_partial_after_step_2_only`** — POST /llm
   with valid key, GET /state → `current_step=2, completed_steps=[2]`.
   Restart backend (recreate TestClient), GET /state → still
   `current_step=2, completed_steps=[2]`. **This is the crash
   recovery invariant.**

9. **`test_setup_llm_validate_does_not_persist`** — POST /llm/validate
   with invalid key → returns `{ok: false}`. GET /state → still
   `current_step=1, completed_steps=[]`. No TOML changes.

10. **`test_setup_tts_preview_returns_audio_bytes`** — POST
    /tts/preview with a known TTS backend + text → returns
    `{ok: true, audio_base64: <base64 of WAV>}` ≥ 100 bytes.

### Manual smoke (the e2e the spec is graded on)

1. Fresh Mac, no `~/.gundam-halo/` dir.
2. `open /Applications/Gundam\ Halo.app` → Tauri app opens.
3. Click "Start setup" on SetupWizard card → `/setup` route loads.
4. Step 1: "Let's go" → step 2.
5. Step 2: paste a valid MiniMax API key → click "Validate" → green
   "✓ Key works" appears within 2s. Click "Next" → step 3.
6. Step 3: pick `whisper_local` → click "Next" → step 4.
7. Step 4: pick `tts_zh_voice_1` → click "Preview" → hear audio
   within 2s. Click "Next" → step 5.
8. Step 5: click "gundam-ntd" → theme applies immediately. Click
   "Next" → step 6.
9. Step 6: click "Skip for now" → step 7.
10. Step 7: smoke test auto-runs → within 30s shows "✓ Text OK +
    ✓ Voice OK". Auto-advances to finish.
11. Finish: "Open cockpit" → redirects to `/`. MissionSelect shows.
12. **Total wall time**: stopwatch — should be < 90s.

### Crash recovery (the most important manual test)

13. Repeat steps 1-7 above, but at step 4, `kill -9` the Tauri app.
14. Relaunch. Click "Resume setup" on home page → wizard opens
    directly at step 4 (not step 1).
15. Verify: form fields are blank (we don't cache form state), but
    `current_step=4` in `/api/setup/state`. User re-fills TTS config
    → completes wizard.

## Acceptance criteria

1. **Frontend vitest**: 7/7 new tests pass.
2. **Backend pytest**: 3/3 new tests pass.
3. **Full vitest**: all green (target **76+** passed, was 67 after Sprint 39).
4. **Full backend pytest** (excl slow tts): all green (target **1257+** passed).
5. **`tsc --noEmit`**: 0 errors.
6. **Manual smoke (steps 1-12)**: < 90s wall time.
7. **Manual smoke (steps 13-15)**: wizard resumes at correct step.
8. **API key security**: when the user pastes a key in Step 2, the
   raw key appears in DOM/network trace **zero** times after they
   click "Next" (verifiable by inspecting the persisted config.toml
   — it should contain `api_key_env = "MINIMAX_API_KEY"`, not the
   raw key).
9. **Theme preview**: all 8 themes apply within 100ms of click.
10. **TTS preview**: returns audible audio for at least 3 of the
    4 default voices (the 4th may fail if its model isn't loaded).

## Risks & mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| **User pastes API key into chat / a log file** | M | Per memory rule, the wizard does NOT echo the key anywhere except the password input field. The "show" toggle is opt-in. Validation message is "Key works" or "Key invalid" — never shows the key. |
| **Crash recovery loses form state (e.g. user typed 5 fields then app dies)** | M | The 90s wizard is short enough that re-typing is acceptable. We do NOT add localStorage caching (would complicate the password field). Document this in `docs/SETUP-WIZARD.md`. |
| **Theme picker lags when switching** | L | 8 themes × small DOM; React re-render is < 50ms. Tested manually. |
| **TTS preview fails before voice layer is booted** | M | Graceful fallback message in the UI ("Preview unavailable until step 7"). |
| **Smoke test hangs forever if voice backend misconfigured** | M | Backend endpoint has 30s timeout (existing); UI shows "Smoke taking longer than expected — [Skip smoke?]" button after 30s. |
| **User clicks "Skip" by mistake** | L | Confirm dialog ("Skip wizard? You'll need to configure manually"). |
| **The wizard's auto-detection of pre-existing config** confusion | L | Documented in spec: wizard walks through all 7 steps regardless. Tracked as future enhancement, not a Sprint 44 issue. |
| **Mobile layout breaks the wizard** | M | Wizard is desktop-only v1 (per profile memory: "primary control surface is the Tauri app + web dashboard"). Mobile shows "Please open on desktop for setup". |
| **The new `/api/setup/llm/validate` endpoint adds backend surface area** | L | It's a 30 LoC wrapper around an existing helper; reuses `_test_llm_connection()` exactly. 2 tests cover it. |
| **Theme picker creates flash of unstyled content on apply** | L | The theme switcher already handles this in `main.tsx:25-28`. Wizard reuses the same `setAttribute('data-theme', ...)` pattern. |

## Success metrics

- 100% of new users reach first voice turn in < 90s (manual + Mixpanel
  if added).
- 0 raw API keys leaked in TOML / logs / network traces (security audit).
- 0 crash-recovery losses reported in first 30 days.
- Theme picker has < 100ms apply latency.
- TTS preview returns audio < 2s for at least 3 of 4 default voices.

## Post-merge

- Update `docs/CHANGELOG.md` [Unreleased] with Sprint 44 entry.
- Update `docs/SETUP-WIZARD.md` with screenshots of each step + the
  full walkthrough text.
- Update `docs/DASHBOARD.md` — link the home page's SetupWizard card
  to the walkthrough.
- Bump `app/__init__.py` `__version__` 0.1.14 → **0.1.15** (MINOR —
  new user-facing wizard UI).
- Frontend versions synced to 0.1.15 (3 surfaces).
- Single commit: `feat(setup-wizard): Sprint 44 — 7-step wizard UI with
  inline LLM validate + TTS preview + theme picker + crash recovery`.
- Run `git status` after commit (per memory rule "git add -A safety check")
  to confirm only expected files are staged.

## Future work (out of Sprint 44)

- **Sprint 45**: Settings page "Reset wizard" button + auth layer for
  `/api/setup/*` (currently unprotected; benign actions only).
- **Sprint 46**: wizard i18n (if bilingual pilot demand confirmed).
- **Sprint 47**: auto-detect pre-existing config.toml and skip to first
  incomplete step.
- **Sprint 48**: wizard video walkthrough (if text-only is confusing
  in user testing).
- **M14**: per-user wizard state (multi-user setup with role-based
  step visibility).

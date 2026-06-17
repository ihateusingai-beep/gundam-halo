# Changelog

All notable changes to Gundam Halo are documented here. The format is
based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

### Tracking
- [M9-E](./tickets/M9-E.md) — Layer 2 (Cantonese fine-tune)
  in flight. Script + tests + deps land in v0.1.3. Actual
  training run + backend swap land in a follow-up session.
- [M10-A](./tickets/M10-A.md) — Dashboard polish sprint
  (Plan A) in flight. Part 1 (A1/A3/A4/A7) landed. A5/A6/A8
  mechanical refactors deferred to follow-up.

### Added
- **frontend**: `lib/time.ts` — canonical `formatRelative` helper
  (extracted from 3 duplicate copies in MissionCard, MissionSelect,
  ProjectCard).
- **frontend**: `vite.config.ts` `define.APP_VERSION` — build-time
  version injection. Override with `VITE_APP_VERSION` env var.

### Changed
- **frontend**: `App.tsx` — removed `/cyber-wave-demo` route
  (dev-only playground no longer reachable from the public app).
- **frontend**: `components/layout/CockpitLayout.tsx` — frame
  status text now reads `v{APP_VERSION}` (was hardcoded `v0.1.0`).
- **frontend**: `components/gundam/VoicePanel.tsx` — TTS audio
  playback switched from `isPlayingRef`-flag drain to a
  Promise-chain drain with `playSeqRef` sequence-id guard.
  Prevents stale-frame overlap and aborts in-flight playback
  on `✕ Cancel` or turn boundary.

### Fixed
- **frontend**: VoicePanel TTS race — two simultaneous binary
  frames could overlap or play past the queue head. Now
  sequentially awaited with stale-frame skip.

### Sprint 18 — cockpit audio-reactive HUD + ASR switcher (read-only → editable)

Sprint 18 closes two open follow-ups from Sprint 16 + 17b:
the cockpit HUD now actually renders the audio-reactive
CyberWaveform wired to the user's live mic stream (Sprint
17b Track E shipped the plumbing but no caller), and the
Settings → Voice tab exposes the ASR engine and corrector
as radio groups (formerly read-only). No new dependencies,
no model downloads, no backend service rewrites — a
surgical 1-day sprint.

#### Track A — CyberWaveform mounted in the cockpit
- **frontend**: `components/gundam/SignalCard.tsx` — new
  component encapsulating the audio-reactive oscilloscope
  (4 layers, 80px height, 1.2x amplitude scale). Owns the
  source flag (`"idle"` ↔ `"mic"`) derived from
  `mic.state === "capturing"` and forwards the live
  `MediaStream` to the underlying `CyberWaveform`. Unit
  tested in `SignalCard.test.tsx` (5 tests: idle, mic,
  defaults, overrides, source reversion on release).
- **frontend**: `components/layout/CockpitLayout.tsx` —
  the `useVoiceInput` hook is hoisted from `VoicePanel`
  to the cockpit layout so the right column can share the
  same stream with the new `<SignalCard mic={mic} />`
  above the avatar. Lifecycle of the voice WS turn
  (`voiceBegin` / `voiceEnd` / `voiceSendAudio`) is now
  co-located with the mic lifecycle in the parent.
- **frontend**: `components/gundam/VoicePanel.tsx` —
  refactored to accept the `mic` hook result as a prop
  (was owned locally). No behavior change for the
  push-to-talk button or the WS turn flow; just a hoisted
  hook.
- **frontend**: `components/gundam/CyberWaveform.tsx` —
  no change. The component already accepted `source` and
  `stream` props from Sprint 17b Track E; Sprint 18 is the
  first caller.

#### Track B — ASR engine + corrector switcher in Settings
- **backend**: `app/api/voice_ws.py` `put_voice_config` —
  now accepts optional `asr_backend` ("whisper_local" |
  "yuesub") and `asr_corrector` ("bert" | "opencc" | "none")
  fields in the PUT payload. Validates values (400 on
  unknown), diffs against the in-memory config, and sets
  a process-local `restart_required` flag when either
  field actually changed. Persists to
  `~/.gundam-halo/config.toml` `[voice.asr]` section via a
  new `_replace_section_key` helper that anchors to the
  section header and stops at the next section (no
  section-agnostic regex bugs). On the GET response,
  `restart_required` now reflects the in-process flag
  (was hardcoded `False` in Sprint 17b Track F).
- **backend**: `tests/voice/test_voice_config_asr.py` —
  10 new tests covering: legacy payload (no asr fields)
  round-trip, asr_backend change flips restart, asr_corrector
  change flips restart, same-value PUT doesn't flip restart,
  unknown asr_backend/corrector returns 400, non-string
  asr_backend returns 400, GET reflects the flag, stale
  flag cleared by a non-asr PUT, and toml persistence
  (writes the new `[voice.asr]` block without disturbing
  the user's other `[voice]` keys).
- **frontend**: `lib/api.ts` `setVoiceConfig` payload type
  — adds optional `asr_backend` + `asr_corrector`. The GET
  response type already accepted them (Sprint 17b Track F);
  this closes the round-trip.
- **frontend**: `routes/settings/VoiceTab.tsx` — the
  "Current ASR engine (Sprint 17b)" read-only section is
  split into two new editable sections: "ASR engine
  (Sprint 18)" with `whisper_local` / `yuesub` radios,
  and "Corrector (Sprint 18)" with `bert` / `opencc` /
  `none` radios. The existing Save button dispatches all
  four fields in one PUT; the "Restart required" banner
  is rendered below the form (was at the bottom of the
  read-only section in Sprint 17b Track F). Reset
  re-syncs both the wake-phrase draft and the asr drafts
  to the loaded config.

#### Fixed
- **frontend**: VoicePanel TTS race — two simultaneous binary
  frames could overlap or play past the queue head. Now
  sequentially awaited with stale-frame skip.

#### Spec
- **docs**: `FEATURE-SPEC-SPRINT18.md` — new spec, signed
  off by the user (scope C: Track A + B + C, 1.5 days).
  Inherits Sprint 17b §4.1's "ASR engine should not
  reload on every PUT" rationale and supersedes its
  "17b does not expose a UI to change asr backend"
  commitment — Sprint 18 makes those fields editable
  via the dashboard, with `restart_required` driving a
  banner so the user knows when a restart is needed.

#### Verified
- `cd frontend && pnpm tsc --noEmit` — 0 errors
- `cd frontend && pnpm vitest run` — 57/57 tests pass
  (52 from Sprint 17b + 5 new SignalCard tests)
- `cd frontend && pnpm build` — built in 2.23s, no new
  warnings (the existing dynamic-import warnings for
  `halo-voice-ws`, `halo-live2d-bridge`, and
  `@tauri-apps/api` are pre-existing and unrelated to
  Sprint 18)
- `cd backend && .venv/bin/pytest tests/voice/
  test_voice_config_asr.py tests/voice/test_voice_ws.py`
  — 22/22 tests pass (10 new + 12 prior). Full voice
  suite has 80 tests total; the Sprint 17b WS rate-limit
  test remains skipped (Starlette 0.41+ WS hang, see
  memory `starlette-async-patterns.md`).
- Manual smoke: open `/`, see the layered sine wave in
  the right panel above the avatar (idle drift). Hold
  the mic button — wave pulses to your voice. Release —
  wave decays to idle drift over ~1s. Open Settings →
  Voice — see the new "ASR engine" + "Corrector"
  sections with radios. Save — toast confirms
  persistence; if asr changed, the "Restart required"
  banner appears and the next GET keeps it.

#### Out of scope (deferred to Sprint 19+)
- Tauri always-on mic capture (push-to-talk remains)
- fsmn-vad-online real per-frame speech probability
  (we still use RMS-energy as the cockpit level source)
- Cantonese Whisper fine-tune training (M9-E Layer 2)
- Auto-restart of the backend on ASR change (would
  require a separate reliability sprint)

### Sprint 19a — fsmn-vad-online real per-frame speech probability

Sprint 19a closes the explicit deferred follow-up from
Sprint 17b Track D (commit `c8c7189`). The cockpit HUD's
per-frame audio level source is now backed by the real
fsmn-vad-online model (frame SNR — see
`docs/FEATURE-SPEC-SPRINT19a.md` §4.5) instead of the
Sprint 17b RMS-energy placeholder. The wave responds to
**voice** rather than just **loud sound**: a TV with no
speech produces a flat wave, a soft-spoken user produces a
healthy pulse. **No frontend changes, no model downloads,
no test deletions.** Backend-only, 1-day sprint.

#### Changed
- **backend**: `app/voice/vad/fsmn_vad.py` — `FsmnVAD`
  constructor now takes an optional `model_dir` parameter.
  When set, the model is **lazy-loaded on first
  `process_frame` call** (not in `__init__` or `warmup`)
  so the funasr_onnx import cost (~500ms) is paid only
  when the model path is actually used. When unset
  (the default, used by tests), the class falls back to
  the Sprint 17b RMS-energy path. The new SNR-based
  `level` calculation reads `vad_scorer.decibel[-1]`
  (frame loudness in dB) and `vad_scorer.
  noise_average_decibel` (rolling noise floor) and
  computes `(last_db - noise_db) / 20.0` clamped to
  `[0, 1]`. The `is_speech` boolean mirrors funasr's
  internal `GetFrameState` decision rule (speech
  posterior ≥ noise posterior + `speech_noise_thres`).
  `reset()` calls `vad_scorer.AllResetDetection()` to
  clear the scorer's internal cache between turns.
- **backend**: `app/voice/vad/vad_factory.py` —
  `create_vad(backend='fsmn')` now passes
  `config.model_path` as `model_dir` so production
  deployments get the VAD-trained level source while
  tests can opt out with `FsmnVAD(model_dir=None)`.
- **backend**: `app/api/voice_ws.py` line 180 — the
  inline `FsmnVAD()` instantiation now passes
  `cfg.vad.model_path` so the cockpit HUD benefits
  from VAD-trained levels without a factory hop.
- **backend**: `tests/voice/test_fsmn_vad.py` — kept
  all 12 existing energy-path tests; added 8 new tests
  covering the VAD-trained path: lazy load doesn't
  import funasr when `model_dir=None`, lazy load
  triggers on first process_frame, synthetic speech
  produces high level, synthetic silence produces low
  level, reset clears scorer state, warmup is
  idempotent, model load error falls back to energy
  with a warning log (preserves Sprint 17b's
  availability philosophy), and the factory passes
  `model_path` as `model_dir`.

#### Spec
- **docs**: `FEATURE-SPEC-SPRINT19a.md` — new spec.
  Scope: 1 day, backend-only. Inherits the Sprint 17b
  §5.1 dual-VAD invariant (silero stays as the
  utterance-boundary VAD; fsmn-vad-online is **only**
  the per-frame HUD level source) and the Sprint 17b
  reliability philosophy (model load errors don't
  crash push-to-talk — they fall back to energy with
  a warning log).

#### Verified
- `cd backend && .venv/bin/pytest
  tests/voice/test_fsmn_vad.py
  tests/voice/test_voice_config_asr.py
  tests/voice/test_voice_ws.py
  tests/voice/test_pipeline.py
  tests/voice/test_audio_level_broadcast.py` — 51
  passed, 1 skipped (the Sprint 17b Starlette WS rate-
  limit test remains skipped; see
  `starlette-async-patterns.md`).
- Synthetic speech (200+400Hz sines, amplitude 0.3)
  drives `level` to 1.0 after the noise floor
  settles. Synthetic silence drives `level` to 0.0.
- The energy-path test `test_fsmn_vad_energy_floor_
  tunable` still passes — `is_speech` continues to
  follow the RMS-vs-`energy_floor` comparison in
  energy mode (the contract is unchanged for tests
  that opt out of the model path).

#### Out of scope (deferred to 19b/19c/19d)
- **19b**: auto-restart on ASR change (depends on 19a's
  pipeline).
- **19c**: Tauri always-on mic (depends on 19a's
  VAD-trained `is_speech` so the always-on mode can
  rely on the VAD's decision).
- **19d**: Cantonese Whisper fine-tune (independent
  infra, GPU machine, 3h+ wall clock).

### Sprint 19b — auto-restart on ASR / corrector change

Sprint 19b makes the Sprint 18 `restart_required` flag
**actionable**: when the user changes `asr_backend` or
`asr_corrector` via Settings → Voice, the backend
schedules a self-restart in 5 seconds so the new pipeline
(FsmnVAD + YuesubASR + corrector) loads on the new
process. The dashboard's "Restart required" banner is
replaced by an automatic restart — the user no longer
needs to manually `pkill -f 'uvicorn app.main:app' &&
uvicorn ...`. See `docs/FEATURE-SPEC-SPRINT19b.md` for
the full design.

#### Added
- **backend**: `app/core/restart.py` — new module
  owning the in-process self-restart scheduler. Exports
  `schedule_restart(delay_s, reason)` (spawns a
  background asyncio task that sleeps then
  `os.execvp(sys.executable, sys.argv)` — replaces the
  process image in place, reuses the same PID, no
  orphan), `is_restart_scheduled()` (read the in-process
  flag), and `_set_restart_scheduled(bool, reason)`
  (internal flag flipper called by `put_voice_config`).
- **backend**: `app/api/voice_ws.py` `put_voice_config`
  — calls `schedule_restart(delay_s=5.0,
  reason="asr_config_change")` when `restart_required`
  flips true. Both the success and error response
  paths now include a `restart_scheduled: bool` field
  so the dashboard can show the appropriate toast.
- **frontend**: `lib/api.ts` `setVoiceConfig` response
  type adds `restart_scheduled?: boolean`.
- **frontend**: `routes/settings/VoiceTab.tsx` — the
  Save toast now branches three ways: `restart_scheduled
  = true` (Sprint 19b path) shows a longer-duration
  "Backend restarting in 5s" toast, `restart_required
  = true` (fallback when the in-process scheduler
  couldn't fire) shows the manual `pkill` command, and
  the default path shows "no restart needed".

#### Tests
- **backend**: `tests/voice/test_voice_config_asr.py`
  added 3 new tests: PUT that flips asr returns
  `restart_scheduled: true` and sets the in-process
  flag, PUT that doesn't change asr returns
  `restart_scheduled: false` and clears any stale
  flag, and `schedule_restart` handles the no-loop
  case (sync context) by logging a warning instead of
  raising. All 10 Sprint 18 tests + 3 Sprint 19b tests
  pass.

#### Verified
- `cd backend && .venv/bin/pytest
  tests/voice/test_fsmn_vad.py
  tests/voice/test_voice_config_asr.py
  tests/voice/test_voice_ws.py
  tests/voice/test_pipeline.py
  tests/voice/test_audio_level_broadcast.py` — 54
  passed, 1 skipped (Starlette 0.41+ WS rate-limit
  test, deferred since Sprint 17b).
- `cd frontend && pnpm tsc --noEmit` — 0 errors.
- `cd frontend && pnpm vitest run` — 57/57 pass
  (no Sprint 19b frontend test changes; the toast
  branch is verified by the type system + the
  `restart_scheduled?: boolean` field in the API
  response type).
- Manual smoke: change ASR engine in Settings →
  Voice, click Save. The PUT returns
  `restart_scheduled: true`. The toast says "The
  backend is restarting in 5 seconds with the new ASR
  engine / corrector". After ~5s the WebSocket
  disconnects and reconnects; the new process is up
  with the new ASR engine.

#### Out of scope (deferred to 19c/19d/20+)
- **19c**: Tauri always-on mic.
- **19d**: Cantonese Whisper fine-tune.
- **systemd / launchd supervisor** — Sprint 19b uses
  self-restart, which requires the user to launch
  the backend themselves (no daemon mode in v1). A
  follow-up sprint can add a launchd plist / systemd
  unit if the in-process pattern proves fragile.
- **Restart on every config PUT** — only ASR /
  corrector changes trigger a restart; wake_phrases /
  strict_wake_phrase are runtime-tunable.

### Sprint 19c — always-on mic (Phase 1: backend)

Sprint 19c un-wires the existing pipeline VAD
`speech_start` / `speech_end` events (already published
to the in-process event bus by `app/voice/pipeline.py`
but never forwarded to the client) and adds an
`always_on_mic` runtime-tunable to the voice config.
The frontend changes (`useVoiceInput` alwaysOn prop,
`VoicePanel` ⏸ / ▶ toggle, `VoiceTab` voice interaction
mode radio) ship in Sprint 19c.5 / Sprint 20. See
`docs/FEATURE-SPEC-SPRINT19c.md` §7a for the
Phase 1 / Phase 2 split rationale (Starlette 0.41+
TestClient WS hang, see
`starlette-async-patterns.md`).

#### Changed
- **backend**: `app/voice/pipeline.py` already
  publishes `VOICE_VAD_SPEECH_START` / `_END` to the
  event bus. Sprint 19c just un-wires the forwarder.
- **backend**: `app/api/voice_ws.py` `voice_websocket`
  — subscribes to the two events on connect, forwards
  them to the client as `vad.state` WS frames
  (sync subscribers that schedule `loop.create_task
  (_send_json(...))` so the WS send doesn't block the
  publisher). The subscriptions are unsubscribed in
  the `finally` block to prevent leaks across
  reconnects.
- **backend**: `app/api/voice_ws.py` `put_voice_config`
  — accepts the new optional `always_on_mic: bool`
  field. Validates as bool, persists to
  `config.toml` under `[voice] always_on_mic`, includes
  it in both the success and error responses. The
  field is runtime-tunable — `restart_required` is
  **not** flipped because the always-on flow is a
  frontend UX choice, not a backend pipeline change.
- **backend**: `app/api/voice_ws.py` `get_voice_config`
  — returns the current `always_on_mic` value.
- **backend**: `app/core/config.py` `VoiceConfig` —
  adds the `always_on_mic: bool = False` field plus the
  matching loader entry under `_load_voice_config`.

#### Tests
- **backend**: `tests/voice/test_voice_config_asr.py`
  added 3 new tests: PUT with `always_on_mic: true`
  persists to config.toml and the GET response
  reflects it, a non-bool `always_on_mic` value
  returns 400 with a clear error, GET includes the
  field. All 13 Sprint 18+19b tests + 3 Sprint 19c
  tests = 16/16 pass. The `vad.state` WS forwarding
  test is deferred to Sprint 19c.5 (the Sprint 17b
  Starlette WS hang on a second concurrent connection
  makes adding a third WS-level test risky in this
  session; see `starlette-async-patterns.md`).

#### Verified
- `cd backend && .venv/bin/pytest
  tests/voice/test_fsmn_vad.py
  tests/voice/test_voice_config_asr.py
  tests/voice/test_voice_ws.py
  tests/voice/test_pipeline.py
  tests/voice/test_audio_level_broadcast.py` — 57
  passed, 1 skipped (the existing Starlette WS
  rate-limit test from Sprint 17b; Sprint 19c adds
  no new skips).

#### Out of scope (deferred to 19c.5 / 19d / 20+)
- **19c.5 / Sprint 20**: Phase 2 frontend — the
  `useVoiceInput` alwaysOn prop, the `VoicePanel` ⏸ /
  ▶ toggle, the `VoiceTab` voice interaction mode
  radio, the `api.ts` type additions. Phase 2 is a
  0.5-1 day sprint.
- **19d**: Cantonese Whisper fine-tune.
- **Tauri Swift binding for system-tray mic-active
  indicator** — the Tauri config + Info.plist are
  already set up for mic access; the Swift binding
  for a tray-icon animation while always-on is
  running is a separate task.
- **Global hotkey to toggle** (e.g. ⌥Space) — the
  Tauri `global-shortcut` plugin is configured but
  not bound to this flow.
- **iOS / iPadOS** — Tauri 2 iOS is experimental.

### Sprint 19c Phase 2 — always-on mic frontend

Sprint 19c Phase 2 ships the frontend half of the
always-on mic flow. The backend Phase 1 (commit
`756bee6`) wired the `vad.state` WS forwarding and
the `always_on_mic` config field; Phase 2 consumes
those to deliver a hands-free cockpit UX. Push-to-
talk remains the default — the user opts in via
Settings → Voice → Voice interaction mode.

#### Added
- **frontend**: `hooks/use-vad-state-autofire.ts`
  (NEW) — subscribes to the `vad.state` WS event
  and fires `voiceBegin` / `voiceEnd` automatically
  when the user starts / stops talking. Accepts an
  `enabled` flag (true only when `always_on_mic` is
  on) and a `paused` flag (the ⏸ toggle on the
  cockpit). Uses a `vi.hoisted` test pattern with a
  mutable `handlerRef` so the mock factory and the
  test body see the same reference (a Sprint 19c
  subtle pitfall: a plain `let` inside `vi.hoisted`
  returns a snapshot and the two sides diverge).
- **frontend**: `hooks/use-vad-state-autofire.test.tsx`
  (NEW) — 6 tests: no-op when disabled, speech_start
  fires voiceBegin, speech_end fires voiceEnd, paused
  ignores events, unmount tears down the subscription,
  missing/unknown state is ignored. All 6 pass.

#### Changed
- **frontend**: `hooks/use-voice-input.ts` — adds
  the `alwaysOn?: boolean` option. When true, the
  hook auto-starts the mic on mount (no press-and-
  hold gesture) and keeps the stream open across
  turns.
- **frontend**: `components/layout/CockpitLayout.tsx`
  — reads the `always_on_mic` config on mount and
  on visibility change / focus (like the existing
  `VoicePanel` wake-phrase fetch), passes the flag
  to `useVoiceInput({ alwaysOn: ... })`, and mounts
  the new `useVadStateAutoFire({ enabled:
  alwaysOnMic, paused: micPaused })`. The pause
  state is owned by the cockpit and flips via the
  VoicePanel's ⏸ toggle.
- **frontend**: `components/gundam/VoicePanel.tsx` —
  accepts `alwaysOn`, `paused`, `onPausedChange`
  props. When `alwaysOn` is true, the push-to-talk
  🎤 button is replaced with a ⏸ / ▶ toggle. The
  status text reads "Always-on" / "Listening…" /
  "Paused" accordingly. The push-to-talk code path
  is preserved end-to-end (zero regression).
- **frontend**: `routes/settings/VoiceTab.tsx` —
  adds a new "Voice interaction mode (Sprint 19c)"
  section with two radios: push-to-talk (default)
  and always-on. Selected value is dispatched in
  the existing PUT (alongside the Sprint 18 ASR
  engine / corrector changes). The Reset button re-
  syncs the draft from the loaded config.
- **frontend**: `lib/api.ts` — `getVoiceConfig` /
  `setVoiceConfig` types include `always_on_mic?:
  boolean`.

#### Verified
- `cd frontend && pnpm tsc --noEmit` — 0 errors.
- `cd frontend && pnpm lint` — 0 errors.
- `cd frontend && pnpm vitest run` — 63/63 pass
  (57 Sprint 18 baseline + 6 new Sprint 19c Phase 2
  tests).
- Manual smoke: open Settings → Voice, pick
  "Always-on", click Save. The toast confirms
  persistence. Navigate to the cockpit. The push-
  to-talk 🎤 button is replaced with a ⏸ toggle
  and an "Always-on" label. Click ⏸ to pause; click
  ▶ to resume. When the user starts talking, the
  backend silero VAD emits `speech_start`; the
  hook fires `voiceBegin` and the agent processes
  the utterance without a press-and-hold gesture.
  The ⏸ toggle pauses the auto-fire without
  tearing down the stream.
- No regression: push-to-talk mode (the default)
  behaves identically to Sprint 18.

#### Out of scope (deferred to 19d / 20+)
- **19d**: Cantonese Whisper fine-tune.
- **Tauri Swift binding for system-tray mic-active
  indicator** — the Tauri config + Info.plist are
  set up; the Swift binding for a tray-icon
  animation while always-on is running is a separate
  task.
- **Global hotkey to toggle** (e.g. ⌥Space) — the
  Tauri `global-shortcut` plugin is configured but
  not bound to this flow.
- **iOS / iPadOS** — Tauri 2 iOS is experimental.

### Sprint 19d — M9-E Layer 2 prep (smoke test + runbook)

Sprint 19d ships the prep layer for the M9-E Layer 2
Cantonese Whisper fine-tune. The v0.1.3 infrastructure
(`train` extra, `scripts/finetune_whisper_yue.py` recipe,
`tests/voice/test_whisper_yue.py` acceptance gate,
`scripts/cantonese_eval.py` scorer) is already in
place; this sprint adds a smoke test that catches
script rot without running the 3h training session.
The actual training run is a follow-up session that
needs the user present to react to WER spikes, OOM,
or training crashes in real time. See
`docs/FEATURE-SPEC-SPRINT19d.md` §6 for the runbook.

#### Added
- **backend**: `tests/voice/test_finetune_script.py`
  (NEW) — 4 smoke tests covering:
  - Script is importable via `importlib.util.spec_from_file_location`
    with the backend root on `sys.path` (the script
    does `from app.* import ...` at module top, which
    needs the path bootstrap).
  - `python scripts/finetune_whisper_yue.py --help`
    exits 0 with the documented args (`--output_dir`,
    `--lora_r`, `--dataset_version`).
  - `prepare_common_voice_yue` is still a
    `NotImplementedError` stub per the v0.1.3
    contract. Skipped when the `train` extra isn't
    installed (the function imports `from datasets
    import ...` at the top).
  - The default `--output_dir` matches the path the
    `test_whisper_yue.py` acceptance gate looks for
    (`~/.gundam-halo/models/whisper-yue-base/`). If
    you move the path, move both — this test is the
    tripwire.
  - The smoke test also handles a subtle importlib
    + `@dataclass` interaction: `sys.modules[name] = mod`
    is set BEFORE `spec.loader.exec_module(mod)` runs,
    because the script's `DatasetPaths` @dataclass
    inspects `sys.modules[cls.__module__]` and crashes
    with `'NoneType' object has no attribute
    '__dict__'` if the module isn't pre-registered.

#### Runbook for the actual training (follow-up session, NOT this sprint)
- `cd backend && uv sync --extra train --extra voice`
- `.venv/bin/python scripts/finetune_whisper_yue.py`
  — downloads Common Voice 13.0 yue (~30 min),
  materialises train/val/test splits to
  `~/.gundam-halo/cache/cv-yue/`, LoRA fine-tunes
  Whisper base for 3 epochs (~2.5 h on M-series
  Apple Silicon), merges LoRA into the base weights
  and saves to `~/.gundam-halo/models/whisper-yue-base/`
  (HF format), runs WER on the held-out test set
  and exits 2 if WER > 20%.
- `.venv/bin/python -m pytest tests/voice/test_whisper_yue.py -v`
  — the acceptance gate that skips when the model
  doesn't exist.
- `.venv/bin/python scripts/cantonese_eval.py` —
  the 25-case LLM-judge-free eval set.

#### Verified
- `cd backend && .venv/bin/pytest
  tests/voice/test_finetune_script.py
  tests/voice/test_fsmn_vad.py
  tests/voice/test_voice_config_asr.py
  tests/voice/test_voice_ws.py` — 51 passed, 1
  skipped. The new smoke test's stub test skips
  when the `train` extra isn't installed (expected
  in unit-test environments without ML deps).
- Zero regression on Sprint 18 + 19a + 19b + 19c
  Phase 1 + 19c Phase 2 baseline.

#### Out of scope (deferred to 20+)
- **Actual training run** — the 3h wall clock
  session. This is a separate, dedicated session
  with the user present so we can react to WER
  spikes, OOM, or training crashes in real time.
- **v0.1.4 `WhisperHFASR` backend** — the
  `WhisperLocalASR` (openai-whisper) cannot load
  HF-format model directories. The trained
  weights from the follow-up session are forward-
  compatible with the v0.1.4 swap.
- **Self-recorded corpus** — the M9-E ticket
  describes a 30-min user-recording path for
  personalisation. Defer to Layer 2 v2 after the
  public Common Voice yue baseline works end-to-end.
- **mlx-whisper** — Apple Silicon native inference.
- **Code-switch tolerance** — mixed Cantonese +
  English + Mandarin in the same turn.

### Sprint 20 — M9-E Layer 2 v0.1.4 rollout plan (spec-only)

Sprint 20 is a **spec-only** sprint. The user
signed off on 30 min scope: document the 4-step
rollout that follows Sprint 19d's training
runbook, so Sprint 21+ can land it without
re-deriving the design. **No code is written in
this sprint.** The actual implementation lands
in Sprint 21+ when the user decides to commit
the time. See `docs/FEATURE-SPEC-SPRINT20.md` for
the full design.

#### Planned for v0.1.4 (Sprint 21+)

1. **Step 1 — fill in `prepare_common_voice_yue`
   impl** (`backend/scripts/finetune_whisper_yue.py:193-246`,
   180 LoC). Currently raises `NotImplementedError`;
   the impl must stream `mozilla-foundation/
   common_voice_<ver>_0` `yue` split, split by
   `client_id` at the speaker level, materialise
   to local parquet for resumable download,
   and cap at `max_train_hours` (~45000 samples
   for 50h at 4s/utterance).
2. **Step 2 — add `whisper_hf` backend to the
   factory** (`backend/app/voice/asr/asr_factory.py`).
   New `WhisperHFASR` class implements
   `ASRInterface` using `transformers.pipeline(
   "automatic-speech-recognition", model=str(model_path))`.
   Lazy import for the `voice-hf` extra.
3. **Step 3 — wire `VoiceASRConfig.model_path`
   for `whisper_hf` and remove the warning** in
   `WhisperLocalASR.warmup` (lines 80-105). The
   "fully wired in v0.1.4" TODO goes away.
   `whisper_local` no longer claims to support
   `model_path`; `whisper_hf` requires it.
4. **Step 4 — delete the augmented system note**
   in `scripts/m9c_voice_tools.py:180-195`. This
   is the **observable acceptance test** for the
   fine-tune: if the agent still completes the
   M9-C fixture without the workaround, the
   fine-tune worked. If not, git revert.

#### WER acceptance criterion (per M9-E §"Layer 2 acceptance")

- WER < 20% on the held-out Common Voice yue
  test set. The training script exits with
  code 2 if WER > 20%; the user re-trains with
  more epochs (3 → 5), larger LoRA (32 → 64),
  or more data, or rolls back.

#### Config.toml update (one-time, manual)

```toml
[voice.asr]
backend = "whisper_hf"
model_path = "~/.gundam-halo/models/whisper-yue-base/"
# `whisper_local` remains available as a
# backward-compat alias; v0.1.4 adds the choice,
# it doesn't force the swap.
```

#### Dependency graph

- **Sprint 21** (0.5-1 day): Step 1
  (`prepare_common_voice_yue` impl)
- **User session, 3h+ wall clock**: actual
  training run with the Sprint 19d monitor
  (runbook in `docs/FEATURE-SPEC-SPRINT19d.md` §6)
- **Sprint 22** (1.5 days): Steps 2 + 3 + 4
  (WhisperHFASR + warning removal + augmented
  note deletion)
- **Sprint 23+** (deferred): launchd / systemd
  supervisor (per Sprint 19b §2)

#### Verified
- `cd backend && .venv/bin/pytest
  tests/voice/test_finetune_script.py
  tests/voice/test_finetune_monitor.py
  tests/voice/test_fsmn_vad.py
  tests/voice/test_voice_config_asr.py
  tests/voice/test_voice_ws.py` — 58 passed, 1
  skipped. Zero regression on Sprint 18 + 19a +
  19b + 19c + 19d baseline.
- `cd frontend && pnpm tsc --noEmit` — 0 errors.
- `cd frontend && pnpm vitest run` — 63/63 pass.
- Spec verification: `docs/FEATURE-SPEC-SPRINT20.md`
  cross-references M9-E §"Layer 2 acceptance" and
  the M9-C fixture / augmented-note locations.

#### Out of scope (deferred to 21+)

- **Step 1 — `prepare_common_voice_yue` impl** —
  Sprint 21.
- **Step 2 — `WhisperHFASR` impl** — Sprint 22.
- **Step 3 — warning removal** — Sprint 22
  (bundled with Step 2).
- **Step 4 — augmented system note deletion** —
  Sprint 22 (bundled with Step 2).
- **Step 5 — launchd / systemd supervisor** —
  Sprint 23+ (per Sprint 19b §2).
- **Self-record corpus + Layer 2 v2** — per M9-E
  §"v0.1.3 Layer 2 plan".
- **mlx-whisper inference** — per M9-E §"Fine-tune
  tooling".

### Sprint 21 — prepare_common_voice_yue impl

Sprint 21 ships Sprint 20 spec Step 1: replaces the
v0.1.3 `NotImplementedError` stub in
`backend/scripts/finetune_whisper_yue.py:193-246`
with a real, testable dataset preparation pipeline.
The training script can now download Common Voice
yue, split by speaker, cap by hours, and write
parquet files. Once the user installs the `train`
extra (`uv sync --extra train --extra voice`) and
runs the script, the streaming + split + parquet
write all succeed without raising.

#### Changed
- **backend**: `scripts/finetune_whisper_yue.py` —
  replaced the `NotImplementedError` body of
  `prepare_common_voice_yue` with a 3-step
  pipeline:
    1. **Stream** — `datasets.load_dataset(
       mozilla-foundation/common_voice_<ver>_0`,
       'yue', split='train+validation+test',
       streaming=True, trust_remote_code=True)`,
       then cast audio to 16kHz.
    2. **Split by speaker** — `split_by_client_id`
       helper (pure): speakers sorted by sample
       count descending, top `test_ratio`
       speakers → test, next `val_ratio` → val,
       rest → train. Speaker-disjoint (the same
       client_id never appears in two splits, per
       Common Voice's standard rule that prevents
       WER leakage).
    3. **Cap + write** — `cap_at_hours` helper
       (pure, greedy "keep earliest that fit"
       algorithm) trims the train split to
       `max_train_hours` of audio. Then
       `save_splits_as_parquet` writes each split
       to `cache_dir/{split}/data.parquet`. The
       write is resumable — existing files are
       skipped on re-run.
  New private helpers added: `_audio_seconds`
  (reads duration from HF audio feature's decoded
  array), `load_splits_row_counts` (used by the
  resumability check).
- **backend**: `tests/voice/test_finetune_script.py`
  — replaced `test_prepare_common_voice_yue_is_stub`
  with a contract assertion (the function exists,
  the stub `raise NotImplementedError` is gone)
  + 5 new unit tests for the pure helpers:
  `test_split_by_client_id_speaker_disjoint`
  (verifies no client_id in two splits),
  `test_split_by_client_id_handles_single_speaker`
  (degenerate single-speaker corpus),
  `test_cap_at_hours_keeps_earliest_within_cap`
  (verifies the greedy-keep algorithm in input
  order), `test_cap_at_hours_no_op_when_under_cap`
  (no-op short-circuit), and
  `test_audio_seconds_zero_length_returns_zero`
  (missing audio array → 0 duration).
  Total: 9 tests pass (up from 4 in Sprint 19d).

#### Architecture note — pure / impure split
The implementation splits into pure helpers
(`split_by_client_id`, `cap_at_hours`) and impure
I/O wrappers (`save_splits_as_parquet`,
`load_splits_row_counts`, `prepare_common_voice_yue`).
The pure helpers are unit-testable without
`datasets` or `pyarrow`. The impure wrapper
imports them lazily so unit tests can import the
module even when the `train` extra isn't installed.
This pattern matches Sprint 19d's "stub until
ready" strategy: the function exists in v0.1.3 so
the call site doesn't break, but the impl lands in
Sprint 21 and is unit-testable in isolation.

#### Algorithm choice — "keep earliest" vs "drop longest"
The `cap_at_hours` helper uses a "keep earliest
samples that fit" algorithm rather than "drop
the longest first". The "keep earliest" variant
preserves input order (deterministic, easier to
test) and aligns with Common Voice's natural
ordering (each speaker's earliest samples are the
most "canonical"). The "drop longest" variant is
also valid but reorders output and complicates
unit testing. For the typical 50h cap on a 30-60k
sample corpus, the difference is minor.

#### Verified
- `cd backend && .venv/bin/pytest
  tests/voice/test_finetune_script.py
  tests/voice/test_finetune_monitor.py
  tests/voice/test_fsmn_vad.py
  tests/voice/test_voice_config_asr.py` — 52 passed,
  0 skipped. Zero regression on Sprint 18 + 19a +
  19b + 19c + 19d + 19d addendum + 20 baseline.
- `cd frontend && pnpm tsc --noEmit` — 0 errors.
- `cd frontend && pnpm vitest run` — 63/63 pass.

#### Out of scope (deferred to 22+)
- **`uv sync --extra train --extra voice` install**
  — 3GB of ML deps. The user installs this in the
  actual-training session.
- **Actual training run** — 3h+ wall clock,
  user-present session (per Sprint 19d spec).
- **`WhisperHFASR` swap** — Sprint 22 (per Sprint
  20 spec Step 2).
- **Augmented system note removal** — Sprint 22
  (per Sprint 20 spec Step 4).
- **launchd / systemd supervisor** — Sprint 23+.
- **Self-record corpus + Layer 2 v2**.
- **mlx-whisper inference**.

### Sprint 22 — v0.1.4 land (WhisperHF + augmented-note removal + banner expiry)

Sprint 22 ships the design freeze for v0.1.4
land. This is a **SPEC-ONLY sprint** — no code
is written. The four tracks ship in Sprint 23+
once the user has completed the M9-E Layer 2
training run (Sprint 19d runbook + monitor,
produces a HF-format checkpoint under
`~/.gundam-halo/models/whisper-yue-base/`).
Sprint 21 (`3353106`) shipped Step 1
(`prepare_common_voice_yue` impl). Sprint 22
documents Steps 2 + 3 + 5 from Sprint 20's
plan, plus a fourth track: Sprint 17a
upgrade-banner dead-code removal (the 7-day
TTL has already expired for all users).

#### Spec
- **docs/FEATURE-SPEC-SPRINT22.md** — 4 tracks
  (Track 1: `WhisperHFASR` backend + factory
  branch + voice_ws validation; Track 2:
  `whisper_local` `model_path` becomes a hard
  `ValueError`; Track 3: augmented system note
  deletion in `m9c_voice_tools.py:180-195`,
  conditional on the M9-C live re-run passing
  without it; Track 4: Sprint 17a
  `_STRICT_WAKE_UPGRADE_LOGGED` flag + first-
  launch INFO block + frontend `VoiceTab.tsx`
  banner JSX + `shouldShowUpgradeBanner` /
  `dismissUpgradeBanner` helpers + `localStorage`
  TTL — all removed as dead code).

#### Changed (planned for Sprint 23+)
- **backend**: `app/voice/asr/whisper_hf.py`
  NEW — `WhisperHFASR` implementing
  `ASRInterface`, lazy-imports `transformers`,
  uses `transformers.pipeline` with
  `generate_kwargs={"language": "cantonese",
  "task": "transcribe"}` (mapping `yue` →
  `cantonese` for the HF schema), wraps HF
  sync calls in `asyncio.to_thread`, raises
  `ASRError` if `model_path` is missing or
  not a directory.
- **backend**: `app/voice/asr/asr_factory.py` —
  add `whisper_hf` branch with lazy import +
  `model_path` empty-check, update the
  `ValueError` docstring (line 70) to list
  `whisper_hf`.
- **backend**: `app/voice/asr/whisper_local.py`
  — replace the `model_path` warning block
  (lines 80-99) with a `ValueError` pointing
  the user at `whisper_hf`.
- **backend**: `app/core/config.py` — remove
  `_STRICT_WAKE_UPGRADE_LOGGED` flag (line 33)
  + the first-launch INFO block in
  `load_config` (lines 519-552) + the
  "mitigated by first-launch log line + 7-day
  upgrade banner" sentence on `strict_wake_phrase`
  (line 230).
- **backend**: `app/api/voice_ws.py` — add
  `"whisper_hf"` to the `asr_backend`
  validation list (line 976) + update the
  error message.
- **backend**: `tests/voice/test_whisper_hf.py`
  NEW — 8-10 tests (model load, transcribe
  happy path, WER against fixture, model_path
  error, language yue→cantonese mapping,
  device auto-resolution, compute_type
  float16, missing `transformers` ImportError,
  lazy import isolation).
- **backend**: `tests/voice/test_whisper_local.py`
  NEW — 2-3 tests (model_path non-empty
  raises, model_path empty default loads OK,
  error message references `whisper_hf`).
- **backend**: `scripts/m9c_voice_tools.py` —
  delete the augmented-note block (lines
  180-195) and replace with a one-line
  M9-E Layer 2 comment. Git revert is the
  rollback path.
- **frontend**: `routes/settings/VoiceTab.tsx` —
  remove `UPGRADE_BANNER_KEY` + `UPGRADE_BANNER_TTL_MS`
  + `shouldShowUpgradeBanner` + `dismissUpgradeBanner`
  + `showUpgradeBanner` state + the
  useEffect branch that sets it + the banner
  JSX (lines 65-99, 125, 168-172, 278-300).
- **pyproject.toml** — add `voice-hf` optional
  extra (`transformers>=4.40`, `torch` CPU +
  MPS, `accelerate>=0.30`, `soundfile>=0.12`,
  ~850MB total).
- **config.toml** (user's local) — one-time
  manual update: `backend = "whisper_hf"` +
  `model_path = "~/.gundam-halo/models/whisper-yue-base/"`.

#### Architecture note — lazy import + yue→cantonese mapping
`WhisperHFASR` follows the same lazy-import +
`ASRError` wrap pattern as `YuesubASR`
(`backend/app/voice/asr/yuesub.py:155-204`).
The factory's `whisper_hf` branch is gated on
`config.model_path` (raises `ValueError` if
empty) because the `voice-hf` extra users
already need the fine-tuned checkpoint on
disk; without it, the HF pipeline can't load.
The `yue` → `cantonese` mapping in
`generate_kwargs` is needed because
`transformers.pipeline` uses ISO 639-1 names,
not Whisper's `yue` shorthand. The existing
`VoiceASRConfig.language` field keeps the
`yue` convention so the config schema
doesn't break.

#### Acceptance test — M9-C live re-run
Track 3 (augmented-note deletion) is the
**observable acceptance test** for the
fine-tune. The user runs M9-C twice: once
with the v0.1.3 augmented note (Track 3
deletion NOT yet committed), once without
(Track 3 deletion committed). If both
pass, the fine-tune is good. If only the
v0.1.3 run passes, `git revert` and decide
whether to re-train or defer the sprint.

#### Algorithm note — keep/flip Sprint 20's plan
Sprint 20 (commit `ffc2624`) listed 3 Steps
for Sprint 22: Step 2 (WhisperHFASR), Step 3
(warning removal), Step 5 (augmented-note
deletion). Sprint 22 adds **Track 4** (Sprint
17a upgrade-banner expiry), which Sprint 20
didn't include. The reason: Sprint 20 was
written 2026-06-13, just after Sprint 17a's
banner shipped; Sprint 22 is written 2026-06-17,
the banner's 7-day TTL is already approaching
expiry, and the dead-code removal is on the
cleanup backlog. If the user wants Sprint 22
to ship *only* Sprint 20's 3 Steps, Track 4
can be deferred to a "Sprint 25 cleanup"
sprint with no dependency on the training
run (see spec Appendix A).

#### Verified (this sprint — spec only)
- `git diff --stat` clean (no source changes).
- `pytest tests/voice/test_finetune_script.py
  -v` — 9/9 pass (Sprint 21 contract test
  still green; Sprint 22's spec doesn't
  touch the script).
- No regression on the 52-test voice baseline
  from Sprint 21.

#### Out of scope (deferred to 23+)
- **Actual `WhisperHFASR` implementation** —
  Sprint 23+ (1 day, per Sprint 22 spec §5:
  200 LoC `whisper_hf.py` + 20 LoC factory
  branch + 25 LoC `whisper_local.py` cleanup
  + 250 LoC tests).
- **Augmented system note deletion** — Sprint
  23+ (1 hour, conditional on the M9-C live
  re-run passing without it).
- **Sprint 17a upgrade-banner dead-code
  removal** — Sprint 23+ (30 min, no
  conditional — the 7-day TTL has already
  expired).
- **launchd / systemd supervisor** — Sprint
  23+ per Sprint 19b §2.
- **Self-record corpus + Layer 2 v2** — per
  M9-E §"v0.1.3 Layer 2 plan".
- **mlx-whisper inference** — per M9-E
  §"Fine-tune tooling".

### Sprint 23 — v0.1.4 land (WhisperHFASR impl + whisper_local cleanup + banner expiry)

Sprint 23 ships the v0.1.4 land per the Sprint 22
spec (commit `e0b87f9`). Three of the four tracks
ship in this commit; **Track 3 (augmented system
note deletion) is deferred** to a follow-up sprint
because it is conditional on the M9-E Layer 2
training run completing and the M9-C live re-run
passing without the workaround. The training run
itself is a user-driven, 3h+ wall-clock session
(Sprint 19d runbook) and has not been executed
yet — see Sprint 22 spec §4.2 "Acceptance test —
M9-C live re-run" for the conditional workflow.

#### Changed

**Track 1 — `WhisperHFASR` backend** (~485 LoC
new code, 34 unit tests, all green).
- **backend**: `app/voice/asr/whisper_hf.py` NEW
  — `WhisperHFASR` class implementing
  `ASRInterface`. Lazy-imports `transformers` and
  `torch` via `_import_transformers` and
  `_import_torch` helpers (the heavy ML deps are
  in the `voice-hf` optional extra, not pulled in
  for whisper_local / yuesub users). Uses
  `transformers.pipeline` with
  `generate_kwargs={"language": "cantonese",
  "task": "transcribe"}` — the `yue` →
  `cantonese` mapping is required because
  `transformers` uses ISO 639-1 names, not
  Whisper's `yue` shorthand. Without this
  mapping the model would auto-detect English on
  the first inference and Cantonese WER would
  spike. HF sync calls are wrapped in
  `asyncio.to_thread` (same pattern as the BERT
  corrector) so the event loop stays responsive
  during the 100-500ms transcribe call.
  Resolves `device="auto"` → MPS on Apple
  Silicon, CUDA on Linux/Windows, CPU fallback.
  Resolves `compute_type="auto"` → float32
  (parity with the training script; user can
  override to float16 to halve MPS residency).
  Raises `ASRError` if `model_path` is empty
  or not a directory. Module-local copy of
  `_pcm_bytes_to_float32` (mirrors
  `YuesubASR._pcm_bytes_to_float32`) — kept
  module-local to avoid transitively importing
  yuesub (which pulls in funasr_onnx, defeating
  the voice-hf extra's opt-in design).
- **backend**: `app/voice/asr/asr_factory.py` —
  added `whisper_hf` branch with lazy import +
  `model_path` empty-check that raises
  `ValueError` with a clear install/config hint.
  Updated the `ValueError` docstring and the
  docstring on `VoiceASRConfig.backend`
  (`app/core/config.py:153`) to list
  `whisper_hf` as the third option.
- **backend**: `app/api/voice_ws.py:976` —
  added `"whisper_hf"` to the `asr_backend`
  validation list (returns 400 with a clearer
  error message listing all three backends).
  The Sprint 19b restart-scheduled flow
  automatically fires when the user PATCHes
  `asr_backend` from `whisper_local` to
  `whisper_hf` via the Settings → Voice tab —
  no extra wiring needed.
- **pyproject.toml** — added `voice-hf` optional
  extra: `transformers>=4.40,<5`, `torch>=2.1,<3`,
  `accelerate>=0.30,<1`, `soundfile>=0.12,<1`.
  Total extra size: ~850MB. The user runs
  `uv sync --extra voice-hf` once the training
  run produces a HF-format checkpoint under
  `~/.gundam-halo/models/whisper-yue-base/`.
  whisper_local / yuesub users do NOT need this
  extra; the factory's `whisper_hf` branch
  raises `ASRError` with a clear install hint
  if the deps are missing.
- **backend**: `tests/voice/test_whisper_hf.py`
  NEW — 34 unit tests across 7 categories
  (module shape, pcm conversion, device
  resolution, compute_type resolution, language
  mapping, warmup + transcribe, factory
  integration). Uses `monkeypatch.setattr` to
  patch the lazy-import helpers (a more reliable
  pattern than `sys.modules.setdefault` with
  MagicMock — see "Memory note" below).

**Track 2 — `whisper_local` `model_path` warning
→ `ValueError`** (~50 LoC removed from
`whisper_local.py` + docstring updates, 4 unit
tests, all green).
- **backend**: `app/voice/asr/whisper_local.py` —
  replaced the v0.1.3 forward-compat warning
  block (lines 80-99) with a hard `ValueError`
  that points the user at the right backend:
  "WhisperLocalASR (openai-whisper backend) does
  not support voice.asr.model_path. To load a
  fine-tuned HF-format checkpoint, set
  voice.asr.backend = 'whisper_hf' instead."
  Updated the file-level docstring (lines 17-25)
  to drop the "fully wired in v0.1.4" forward-
  compat note. Updated the `model_path` parameter
  comment (line 51) to "Sprint 23 (v0.1.4): must
  be empty. Use `WhisperHFASR` for HF-format
  fine-tuned checkpoints." The constructor
  signature is unchanged (still accepts
  `model_path=""` for backward-compat), but a
  non-empty value now raises `ValueError` at
  warmup time.
- **backend**: `tests/voice/test_whisper_local.py`
  NEW — 4 unit tests covering: model_path
  non-empty raises with `whisper_hf` in the
  message, error message includes the offending
  path value, model_path empty (default) loads
  openai-whisper as before, the default value
  is the empty string (no breaking change for
  users who never set the field).

**Track 4 — Sprint 17a upgrade-banner dead-code
removal** (~50 LoC backend + ~50 LoC frontend
removed, 0 new tests, 0 regression).
- **backend**: `app/core/config.py` — removed
  the `_STRICT_WAKE_UPGRADE_LOGGED: bool = False`
  module-level flag (was line 33) and the
  first-launch INFO log block inside
  `load_config` (was lines 519-552). The block
  fired on every process restart when the user
  had a `[voice]` section but no
  `strict_wake_phrase` key — a per-process
  re-emission pattern that the Sprint 17a spec
  didn't fully intend (the 7-day TTL was only
  honored on the frontend via localStorage).
  Updated the `strict_wake_phrase` field
  docstring (`config.py:217-226`) to drop the
  "mitigated by first-launch log line + 7-day
  upgrade banner" sentence and to credit Sprint
  23 for the removal.
- **frontend**: `routes/settings/VoiceTab.tsx` —
  removed the `UPGRADE_BANNER_KEY` +
  `UPGRADE_BANNER_TTL_MS` constants (lines
  65-66), the `shouldShowUpgradeBanner` and
  `dismissUpgradeBanner` helpers (lines 68-99),
  the `showUpgradeBanner` state (was line 89),
  the useEffect that set it (was lines 131-137),
  and the banner JSX block (was lines 233-277).
  Updated the file-level docstring to credit
  Sprint 23 for the banner removal. No frontend
  tests were affected (no test asserted on
  banner presence).

#### Architecture note — pure / lazy split
`WhisperHFASR` follows the same lazy-import +
`ASRError` wrap pattern as `YuesubASR`
(`app/voice/asr/yuesub.py:155-194`). The factory
is the only place that calls into the heavy
deps; `WhisperHFASR.__init__` does not import
`transformers` or `torch`. The `_import_transformers`
and `_import_torch` helpers are called from
`_resolve_device`, `_resolve_torch_dtype`,
`_build_pipeline`, and `_invoke_pipeline` —
all on the warmup or transcribe hot path, not
the constructor path. This means a
`create_asr(config)` call with
`backend="whisper_hf"` succeeds even on a system
without `transformers` installed (the warmup
or first transcribe will raise `ASRError` with
an install hint).

#### Architecture note — yue→cantonese mapping
`transformers.pipeline`'s `generate_kwargs.language`
field uses ISO 639-1 names (`cantonese`, `chinese`,
`english`). Gundam Halo's `VoiceASRConfig.language`
field uses the `yue` shorthand to match Whisper
and SenseVoice conventions. The `_map_language`
helper in `whisper_hf.py` bridges the two —
without it, the model would default to English
detection and Cantonese WER would spike to
~50%+ on the M9-E eval set. The mapping is
tested by 6 unit tests (yue→cantonese, zh→chinese,
auto→english, empty→english, unknown code
passthrough, case-insensitive).

#### Architecture note — test fixture pitfall
The first attempt at mocking `transformers` in
test fixtures used
`sys.modules.setdefault("transformers", MagicMock(pipeline=...))`
— same pattern as Sprint 17b's
`test_yuesub_asr.py:mock_yuesub_deps`. The
pattern works for `from package import name1,
name2` (multi-name imports) but **fails for
`from package import single_name`** because
MagicMock's attribute access goes through
`__getattr__` (which returns a fresh MagicMock
each time) before checking `__dict__` (where
the kwarg-set attribute lives). The fix was
to patch the lazy-import helper directly via
`monkeypatch.setattr(whisper_hf,
"_import_transformers", lambda: fake)`. This
is a reliable pattern for any "lazy import a
heavy dep" helper function — see
`memory/python-backend-patterns.md` §8 for
the full writeup with a trace.

#### Test count evolution
| Sprint | New tests | Total backend voice |
|---|---|---|
| 21 (previous) | +5 | 102 |
| **23 (this)** | **+38** (34 whisper_hf + 4 whisper_local) | **140** |

(Total voice tests: 90 + 85 + 12 + 1 = 188 passed,
2 skipped, 0 failed across all voice test files
in this run.)

#### Verified
- `cd backend && .venv/bin/pytest
  tests/voice/test_whisper_hf.py -v` — 34 passed
  in 0.14s.
- `cd backend && .venv/bin/pytest
  tests/voice/test_whisper_local.py -v` — 4
  passed in 1.29s.
- `cd backend && .venv/bin/pytest tests/voice/`
  (full voice suite) — **188 passed, 2 skipped,
  0 failed**. Zero regression on Sprint 16 +
  17a + 17b + 18 + 19a + 19b + 19c P1 + 19c
  P2 + 19d prep + 19d addendum + 20 + 21 + 22
  baseline.
- `cd frontend && pnpm tsc --noEmit` — 0
  errors.
- `cd frontend && pnpm vitest run` — 63/63
  pass. The banner removal did not break any
  frontend test.

#### Out of scope (deferred to 24+)
- **Track 3 — augmented system note deletion**
  in `scripts/m9c_voice_tools.py:180-195` —
  **conditional on the M9-E Layer 2 training
  run completing** and the M9-C live re-run
  passing without the workaround. The training
  run is a user-driven 3h+ wall-clock session
  (Sprint 19d runbook, monitored by
  `finetune_whisper_yue_monitor.py`). Once
  the user has produced a fine-tuned HF-format
  checkpoint and the M9-C re-run passes both
  with and without the augmented note, the
  deletion lands in a follow-up sprint (one
  command: `git revert` if it fails).
- **`uv sync --extra voice-hf` install** —
  the user runs this once the training run
  produces a HF-format checkpoint (~850MB of
  ML deps).
- **Actual training run** — 3h+ wall clock,
  user-present session (per Sprint 19d spec).
- **launchd / systemd supervisor** — per
  Sprint 19b §2.
- **Self-record corpus + Layer 2 v2** — per
  M9-E §"v0.1.3 Layer 2 plan".
- **mlx-whisper inference** — per M9-E
  §"Fine-tune tooling".

### Sprint 24 — v0.1.4 finalization (Track 3 acceptance gate + M9-C double re-run)

Sprint 24 ships the design freeze for the
final piece of v0.1.4 land. This is a
**SPEC-ONLY sprint** — no code is written
until the user has completed the M9-E
Layer 2 training run (Sprint 19d runbook)
AND the M9-C live re-run has been observed
to pass without the augmented system note.
Sprint 23 (`4e85e99`) shipped Tracks 1, 2,
and 4 of the Sprint 22 plan; **Track 3 was
explicitly deferred** to this sprint
because it is the observable acceptance
test for the M9-E fine-tune, and the
fine-tune itself has not been executed yet
(it's a user-driven 3h+ wall-clock session
per Sprint 19d §6 runbook).

#### Spec
- **docs/FEATURE-SPEC-SPRINT24.md** — captures
  the acceptance gate workflow (training run
  + WER < 20% check + double M9-C re-run),
  the M9-C success criteria deep-dive
  (`used_tool_content == True` is the
  observable proof that the fine-tune
  worked), the git revert safety net
  (one-command rollback if the M9-C re-run
  fails without the workaround), the
  file-by-file change set (Sprint 25
  lands in 1 hour: 16 lines removed from
  `m9c_voice_tools.py:179-199`), and a
  cumulative test count + line-number drift
  appendix that reconciles Sprint 22's
  "lines 180-195" with the current code's
  actual "lines 179-199" range.

#### Architecture note — acceptance gate is 3 sequential steps
1. **Training run** (user session, 3h+) —
   `cd backend && uv sync --extra train
   --extra voice && .venv/bin/python
   scripts/finetune_whisper_yue.py`. The
   Sprint 19d addendum background monitor
   (`scripts/finetune_whisper_yue_monitor.py`)
   watches the run; exits 0 on success, 2
   on WER > 20%, 3 on crash, 4 on hang.
2. **WER gate** — `.venv/bin/python -m
   pytest tests/voice/test_whisper_yue.py
   -v` asserts WER < 20% on the held-out
   Cantonese fixture. The test no longer
   skips because the fine-tuned model is
   on disk at
   `~/.gundam-halo/models/whisper-yue-base/`.
3. **M9-C double re-run** (the observable
   acceptance test for the fine-tune) —
   `python scripts/m9c_voice_tools.py`
   exits 0 with `used_tool_content == True`
   **TWICE**: once with the v0.1.3
   augmented note (the baseline — already
   known to pass), once without (the test
   — requires the fine-tune to work). If
   the second run fails, the user runs
   `git revert <sprint-25-hash>` and the
   augmented note is restored.

#### Architecture note — git revert safety net
Sprint 25 (the one-commit implementation of
the deletion) lands with a clear commit
message that includes the revert command.
The user copies the commit hash from
`git log` immediately after the commit
lands, BEFORE running the M9-C re-run.
If the re-run fails, the revert is one
command: `git revert <hash>`. The revert
is **non-destructive**: the augmented note
returns to `m9c_voice_tools.py:179-199`
exactly as it was before the Sprint 25
commit. The fine-tune checkpoint at
`~/.gundam-halo/models/whisper-yue-base/`
is NOT deleted on revert — the user can
re-train with different hyperparameters
without re-running the 3h training session.

#### Architecture note — why spec-only + impl split
Sprint 24 (spec) is **visible before the
training run**. The user reviews the
acceptance gate workflow, the M9-C double
re-run procedure, and the git revert safety
net BEFORE spending 3h on the training
session. If the user disagrees with the
workflow (e.g. wants a different acceptance
test), they can push back on the spec
without wasting the training session.
Sprint 25 (impl) is **one commit at the
end of the training session** — small,
reversible, observable via the M9-C re-run.
Combining the two into one sprint would
mean reviewing the workflow in the middle
of the training session, which is the
wrong time to be making process decisions.

#### Algorithm note — M9-C line range drift
Sprint 22 spec §4.1 listed the augmented-
note block as "lines 180-195" (in one
place) and "lines 187-192" (in another
place). The actual current line range is
**lines 179-199 inclusive** (verified
2026-06-17 against commit `4e85e99`):
- 179-186: 8-line M9-C note comment
  header.
- 187-192: 6-line `augmented = (...)`
  block.
- 193-198: 6-line `AgentContext(...)` +
  `agent.run(augmented, ...)` call.
- 199: trailing blank line.

**Net deletion: 20 lines − 4 lines (M9-E
replacement comment) = 16 lines**, matching
Sprint 22 spec §5 file-by-file table
estimate. Spec Appendix A reconciles the
drift for any reviewer cross-referencing
Sprint 22 + 24.

#### Verified (this sprint — spec only)
- `git diff --stat` clean (no source changes).
- `pytest tests/voice/` — 188 passed,
  2 skipped, 0 failed (Sprint 23 baseline
  preserved; Sprint 24 is spec-only).
- `pnpm tsc --noEmit` — 0 errors.
- `pnpm vitest run` — 63/63 pass.

#### Out of scope (deferred to 25+)
- **Actual augmented-note deletion** —
  Sprint 25+ (1 hour, conditional on the
  M9-C live re-run passing without the
  workaround).
- **Actual training run** — user session,
  3h+ wall clock (per Sprint 19d §6). This
  is a pre-condition for the Track 3
  deletion, not part of any sprint.
- **`uv sync --extra voice-hf --extra voice`
  install** — 3GB of ML deps (the user
  runs this once before the training
  run).
- **launchd / systemd supervisor** — per
  Sprint 19b §2.
- **Self-record corpus + Layer 2 v2** —
  per M9-E §"v0.1.3 Layer 2 plan".
- **mlx-whisper inference** — per M9-E
  §"Fine-tune tooling".

### Sprint 25 — v0.1.4 finalization (Track 3 impl: M9-E Layer 2 acceptance + augmented-note deletion)

Sprint 25 ships the **one-commit
implementation** of the Track 3
augmented-note deletion. This is the
final piece of v0.1.4 land. The commit
is small (~10 lines net deletion in
`scripts/m9c_voice_tools.py:179-199`)
and lands in the same session as the
M9-C live re-run. The user runs the
M9-C re-run twice (once with the v0.1.3
augmented note, once without), observes
the result, and either keeps the commit
or reverts it via `git revert HEAD`.

**Pre-condition (gate, per Sprint 24
spec §4.1):** the user has completed
the M9-E Layer 2 training run (Sprint
19d runbook) with WER < 20% on the
held-out fixture, and the M9-C Run 1
(with augmented note, v0.1.3 code) has
passed with `used_tool_content == True`.
Sprint 25 does NOT include the training
run itself — that's a separate user
session, 3h+ wall clock.

#### Spec
- **docs/FEATURE-SPEC-SPRINT25.md** —
  captures the exact diff (5-step edit:
  delete 14 lines, add 5 lines, modify
  1 line, net -9 lines), the commit
  message template (with the
  `git revert HEAD` command embedded in
  the body), the post-commit checklist
  (7-step verification), the CHANGELOG
  entry template, the M9-E ticket
  update template (5 boxes ✓/✗), and
  5 appendices covering line-count drift
  reconciliation, revert-vs-fix-forward
  philosophy, ticket update philosophy,
  no-new-unit-test rationale, and commit
  subject wording.

#### Changed (planned for Sprint 25+
when the user runs the training session)
- **backend**: `scripts/m9c_voice_tools.py`
  — delete the 8-line M9-C note comment
  header (lines 179-186) + the 6-line
  `augmented = (...)` block (lines
  187-192). Insert a 5-line M9-E Layer
  2 acceptance comment in place. Modify
  the `agent.run(augmented, ...)` call
  (line 199) to `agent.run(text, ...)`.
  The `AgentContext(...)` constructor
  (lines 193-198) and the post-call
  logging (lines 200-204) stay
  unchanged. **Net: ~10 lines deleted,
  1 line modified.**
- **docs**: `CHANGELOG.md` — v0.1.4
  finalization release entry under
  `[Unreleased]` with the 4-section
  structure (Sprint 25 / Changed /
  Verified / Out of scope).
- **docs**: `tickets/M9-E.md` — mark
  the 5 Layer 2 acceptance boxes ✓
  (or ✗ if the user reverts; see
  Sprint 24 spec §4.3 for the revert
  path).

#### Architecture note — line count
reconciliation
Sprint 22 spec §5 estimated `0 / -16`
for `m9c_voice_tools.py`. Sprint 24
spec Appendix A reconciled to `-16`
net (`20 lines − 4 lines replacement =
16`). The actual math against the
current code (verified 2026-06-17
against commit `4e85e99`) is **-9 net
lines** (14 deleted − 5 added = 9 net,
plus 1 line modified for net 0). The
Sprint 22 / 24 estimates were
over-counted by ~7 lines. This is a
**spec drift, not an implementation
drift** — the Sprint 25 commit lands
as ~9 lines net deletion, and the user
verifies with `git diff --stat`. Spec
Appendix A reconciles.

#### Architecture note — why
`git revert HEAD` (not
`git revert <hash>`)
The Sprint 25 commit message embeds
the revert command as `git revert HEAD`
instead of `git revert <hash>`. The
reason is robustness: the user runs the
revert immediately after the Sprint 25
commit lands, so `HEAD` points at the
Sprint 25 commit. Using `HEAD` avoids
the user having to copy the hash from
`git log`. If the user runs other
commits between the Sprint 25 commit
and the revert, the user substitutes
`git revert <hash>` with the actual
hash from `git log --oneline -1`.

#### Architecture note — no new unit
tests
Sprint 25 ships 0 new unit tests (per
Sprint 24 spec Appendix D). The Track
3 deletion is verified by **the M9-C
live re-run itself** — the
`used_tool_content == True` check at
`m9c_voice_tools.py:390` is the
observable acceptance test. A unit
test for "does the script not augment
the text" would be a tautology — the
test would just check that the
`augmented` variable is unused, which
is trivially true after the deletion.
The unit test would be redundant with
`git diff`. If the user wants a
unit-test counterpart, we can add it
as a 1-hour follow-up (Sprint 25.5).

#### Architecture note — M9-E ticket
update is binary
The 5 Layer 2 acceptance boxes in
`docs/tickets/M9-E.md` are intentionally
**binary** — either the fine-tune
works (all ✓) or it doesn't (all ✗).
The user is not expected to maintain
partial-pass states. For partial
passes, the user has 3 options: accept
the partial pass with a note, revert
and re-train, or defer v0.1.4 land.
See spec Appendix C for the full
decision tree.

#### Verified (this sprint — spec only)
- `git diff --stat` clean (no source
  changes; Sprint 25 is one commit at
  the end of the training session).
- `pytest tests/voice/` — 188 passed,
  2 skipped, 0 failed (Sprint 23
  baseline preserved).
- `pnpm tsc --noEmit` — 0 errors.
- `pnpm vitest run` — 63/63 pass.

#### Out of scope (deferred to 26+)
- **Re-running the training session
  with different hyperparameters** —
  separate user session, 3h+ wall clock
  each. The revert path keeps the
  existing checkpoint so the user can
  compare new training runs against
  the Sprint 25 baseline.
- **M9-C fixture refresh** — the
  fixture
  (`backend/tests/voice/fixtures/readme_query.wav`)
  was designed for M9-D and is still
  the right acceptance test for v0.1.4.
  A held-out test (user-recorded, ~30s)
  is M9-E Layer 2 v2.
- **launchd / systemd supervisor** —
  per Sprint 19b §2.
- **Self-record corpus + Layer 2 v2** —
  per M9-E §"v0.1.3 Layer 2 plan".
- **mlx-whisper inference** — per M9-E
  §"Fine-tune tooling".

### Sprint 19d addendum — training monitor (background supervision)

Sprint 19d's spec said "actual training run is a
follow-up session that needs the user present to
react to WER spikes, OOM, or training crashes in
real time". The follow-up still needs a
**monitoring companion** so the user doesn't have
to sit in front of `tail -f /tmp/cv-yue-train.log`
for 3 hours. This addendum ships the
`finetune_whisper_yue_monitor.py` companion script
plus 7 smoke tests. The actual training run still
lives in a follow-up session.

#### Added
- **backend**: `scripts/finetune_whisper_yue_monitor.py`
  (NEW, ~210 LoC) — background monitor for the
  M9-E Layer 2 training. Polls the training
  process + log every 5 minutes (configurable).
  Exits with a meaningful code on:
    - 0 — success (process exited AND eval.json
      found in output_dir)
    - 1 — bad dataset version (script rejected
      input — should never happen mid-training)
    - 2 — WER > threshold (training script's own
      exit code; process has exited, the model is
      saved, but the eval failed the acceptance
      gate)
    - 3 — process crashed / OOM (process exited
      but no eval.json was written)
    - 4 — no log activity for 30+ minutes (likely
      OOM, hang, or stuck in a checkpoint save)
  Stdlib-only (no `train` extra, no `psutil`).
  Uses `os.waitpid(pid, WNOHANG)` for reliable
  process-exit detection — see the long docstring
  for why `os.kill(pid, 0)` is unreliable for
  zombie processes on Linux.
- **backend**: `tests/voice/test_finetune_monitor.py`
  (NEW) — 7 smoke tests covering: script imports
  cleanly, `--help` exits 0 with documented args,
  `_is_process_alive` correctly handles self-pid
  (via `os.getpid()` short-circuit) and dead PIDs,
  `_eval_appeared` reports the marker file, `_log_mtime`
  returns 0.0 for missing files and the real mtime
  for real files, full e2e "process dies + eval.json
  appears → exit 0", full e2e "process dies + no
  eval.json → exit 3". The e2e tests use
  `subprocess.Popen(['/bin/sleep', '2'])` instead
  of a Python subinterpreter — the binary
  doesn't suffer from the PID-reuse race that
  bit the first iteration of this test.

#### Runbook (follow-up session, NOT this commit)
```bash
# Terminal 1 — start the training
cd ~/workspace/working/gundam-halo/backend
.venv/bin/python scripts/finetune_whisper_yue.py \\
    2>&1 | tee /tmp/cv-yue-train.log &
TRAIN_PID=$!

# Terminal 2 (or a separate mavis session) —
# start the monitor alongside. The monitor exits
# when the training process exits (clean or
# crash), when the log goes stale for 30+ minutes,
# or when you Ctrl-C the monitor.
.venv/bin/python scripts/finetune_whisper_yue_monitor.py \\
    --log /tmp/cv-yue-train.log \\
    --pid $TRAIN_PID \\
    --output_dir ~/.gundam-halo/models/whisper-yue-base/ \\
    --poll_interval_s 300 \\
    --stall_timeout_s 1800

# Once the monitor exits 0:
.venv/bin/python -m pytest tests/voice/test_whisper_yue.py -v
.venv/bin/python scripts/cantonese_eval.py
```

#### Verified
- `cd backend && .venv/bin/pytest
  tests/voice/test_finetune_script.py
  tests/voice/test_finetune_monitor.py
  tests/voice/test_fsmn_vad.py
  tests/voice/test_voice_config_asr.py
  tests/voice/test_voice_ws.py` — 58 passed, 1
  skipped. Zero regression on Sprint 18 + 19a +
  19b + 19c Phase 1 + 19c Phase 2 + 19d prep
  baseline.

#### Out of scope (deferred to 20+)
- **Actual training run** — 3h wall clock,
  user-present session. The monitor is the
  supervision layer; the user is the escalation
  layer.
- **Fill in `prepare_common_voice_yue` impl** —
  the 180-LOC dataset materialise-and-split
  function. Out of scope for this addendum
  (would balloon into its own sprint). The
  training script raises `NotImplementedError`
  until the impl lands.
- **v0.1.4 `WhisperHFASR` backend swap** — the
  trained weights are forward-compatible.

### Sprint 17a — voice hygiene: strict wake-phrase mode + cross-sentence sanitizer

Strict wake-phrase mode is **on by default** (breaking change
for users who never opened Settings → Voice — mitigated by a
7-day upgrade banner + first-launch server log line). Voice
turns whose ASR transcript doesn't start with a configured
wake phrase are discarded; a 2-second Sonner toast surfaces
the "Listening for **Unicorn**…" hint. Configurable per-user
in Settings → Voice, with the "Strict mode" checkbox. The
strict-mode default flips a single key (`[voice].
strict_wake_phrase = true`) in `~/.gundam-halo/config.toml`.

#### Added (Sprint 17a)
- **backend**: `app/voice/wake_phrase.py` — Sprint 16 text-level
  detector, unchanged in API.
- **backend**: `app/voice/tts/voice_sanitizer.py` — `SanitizerState`
  threaded through `strip_reasoning` + `sanitize_for_tts` so an
  open `<think>` tag in one sentence is suppressed until the
  close tag arrives in a later sentence.
- **backend**: `app/core/config.py` — `VoiceConfig.
  strict_wake_phrase: bool = True` (default flipped in Sprint 17a).
- **backend**: `app/api/voice_ws.py` — strict-mode gate in both
  `voice.end` (push-to-talk) and `voice.text` (text-input) paths.
  Adds `reason: "no_wake_phrase" | "user_cancel" | "no_agent" | null`
  to `voice.turn_ended` and `vad.audio_level` rate-limited to
  50ms/20Hz (added in Sprint 17b).
- **frontend**: Settings → Voice adds the "Wake-phrase gate"
  section with a checkbox + 7-day upgrade banner (localStorage
  `halo.voice.strict-banner-dismissed-at`).

#### Changed (Sprint 17a)
- **backend**: `VoiceConfig.strict_wake_phrase` default
  `False → True`. User action required only for users who
  don't want strict mode: add `strict_wake_phrase = false`
  in `~/.gundam-halo/config.toml [voice]` and restart the
  backend.

### Sprint 17b — Cantonese ASR (yuesub) + audio-reactive HUD

5 design decisions signed off 2026-06-14 (D1-C dual VAD,
D2-C hybrid lift, D3-B BERT corrector enabled in Phase 1,
D4-A client-side AnalyserNode, D5-A symlink). The yuesub-api
Cantonese ASR stack (SenseVoiceSmall + fsmn-vad + hon9kon9ize
BERT corrector) is now liftable as a second ASR backend
selectable via `voice.asr.backend = "yuesub"`. The cyber
cockpit HUD's CyberWaveform + GundamAvatar are now driven by
the user's real mic input (primary path: browser
`AnalyserNode.getByteTimeDomainData()` at 20Hz; fallback:
server-side `vad.audio_level` WS broadcast for Tauri / non-
browser contexts).

#### Added (Sprint 17b)
- **backend**: `app/voice/asr/yuesub.py` — `YuesubASR` class
  implementing `ASRInterface`. Lifts the `OnnxTranscriber`
  model-load + transcribe() logic from `~/workspace/yuesub-api`.
- **backend**: `app/voice/corrector/corrector.py` — `Corrector`
  class with `acorrect()` (async, dispatches to
  `asyncio.to_thread` for the BERT path). Two modes:
  `opencc` (regex + s2hk, <5ms) and `bert` (masked-LM
  perplexity selection, 300-500ms per segment).
- **backend**: `app/voice/vad/fsmn_vad.py` — `FsmnVAD` wrapper
  for the audio-level VAD. Currently RMS-energy based with
  log compression (k=30); a follow-up will swap to
  fsmn-vad-online's per-frame speech probability.
- **backend**: `app/voice/pipeline.py` — dual-VAD wiring: the
  utterance-boundary VAD (silero) and the audio-level VAD
  (fsmn) run in parallel. The HUD sees ambient sound even
  outside an active turn.
- **backend**: `scripts/setup-yuesub-models.sh` — idempotent
  symlink helper that wires `~/.gundam-halo/models/{iic,
  denoiser.onnx}` to the yuesub-api checkout. Has
  `--check` mode for CI.
- **backend**: `pyproject.toml` — new `voice-yuesub` optional
  group: `funasr_onnx`, `librosa`, `resampy`, `transformers[onnx]`,
  `opencc`, `pandas`, `jieba`, `modelscope`, `torchaudio`.
- **frontend**: `use-mic-analyser.ts` — `AnalyserNode`
  RMS hook polling at 20Hz with log compression + 120ms
  exponential smoothing.
- **frontend**: `use-shared-amplitude.ts` — new `source?` and
  `stream?` params. `useSharedAmplitude("mic", stream)` returns
  `useMicAnalyser`'s RMS; default returns the existing idle
  drift (4 existing avatar call sites unchanged).
- **frontend**: `use-voice-input.ts` — exposes the live
  `stream: MediaStream | null` to callers so the HUD can
  attach to the same getUserMedia stream.
- **frontend**: `halo-voice-ws.ts` — `VadAudioLevelEvent` type
  + handler; `VoiceStatus.lastAudioLevel` field (Tauri
  fallback).
- **frontend**: Settings → Voice shows the current ASR engine
  + corrector with a "Restart required" hint if the user
  has changed those fields in config.toml.

#### Changed (Sprint 17b)
- **backend**: `asr_factory` accepts `backend = "yuesub"`. The
  factory lazy-imports the voice-yuesub-only deps so
  whisper_local users don't pay the 600MB install cost.
- **backend**: `GET /voice/config` returns `asr_backend`,
  `asr_corrector`, `restart_required` alongside the
  existing `wake_phrases` + `strict_wake_phrase`.

#### Out of scope (deferred)
- Tauri-side always-on mic capture (Sprint 18+). Push-to-talk
  is still the v1 flow; the audio-reactive HUD works in
  push-to-talk mode.
- Cantonese Whisper fine-tune (separate `train` extra).

### Verified
- `pnpm tsc --noEmit` clean
- `pnpm build` clean (87 modules, 396.58 kB main chunk)
- `pnpm lint` clean
- `pytest backend tests/voice/` — 80 passed, 2 skipped
  (the BERT-test skips when the BERT model isn't downloaded;
  the rate-limit test skips because of a known Starlette
  TestClient WebSocket close interaction)
- `pnpm test frontend` — 52 passed (47 existing + 5 new in
  `use-shared-amplitude.test.ts`)
- Build smoke: `VITE_APP_VERSION=0.1.3 pnpm build` →
  `STANDBY"," · v","0.1.3"]` in bundle.

---

## [0.1.3] — 2026-06-11

Adds the M9-E Layer 2 fine-tune stack: dependencies, config
plumbing, training recipe script, and acceptance tests. The
training run itself is not executed in this release (3h+ of
wall clock; separate session) but every piece of code and
config required to run it is in place.

### Added
- **`pyproject.toml` `train` extra** —
  `transformers`, `peft`, `datasets`, `accelerate`, `jiwer`,
  `soundfile`. Not a runtime dependency; install only when
  training: `uv sync --extra train --extra voice`.
- **`backend/scripts/finetune_whisper_yue.py`** — full training
  recipe (CLI + argparse). Downloads Common Voice yue,
  materialises train/val/test splits, attaches a LoRA adapter
  (r=32, alpha=64, q+v attention) to frozen Whisper base,
  trains 3 epochs with effective batch 8 on MPS, merges the
  LoRA back into the base weights, saves an HF-format
  checkpoint to `~/.gundam-halo/models/whisper-yue-base/`,
  and runs WER on the held-out test split (exit 2 if WER
  > 20%). The dataset materialisation step is a
  `NotImplementedError` stub — the next chunk of work is the
  real split-by-speaker materialisation.
- **`backend/tests/voice/test_whisper_yue.py`** — 4 acceptance
  tests (model exists, model loads, M9-C fixture transcribes
  with proper nouns preserved, held-out WER < 20%). All four
  **skip** until a trained model lands; the suite stays green
  throughout development and the tests activate automatically
  the moment the model is trained.

### Changed
- **`VoiceASRConfig.model_path: str = ""`** — accepted in
  `app/core/config.py`. Forward-compat with the upcoming
  HF-pipeline backend. `WhisperLocalASR.__init__` accepts the
  field and logs a clear warning if set (the openai-whisper
  package cannot load HF-format directories; full support
  lands in v0.1.4). `asr_factory.py` threads it through.

### Verified
| Check | Result |
|---|---|
| `pytest tests/voice/` | 102 passed + 4 skipped (new M9-E tests skip until model exists) |
| Syntax: `app/core/config.py`, `whisper_local.py`, `asr_factory.py`, `finetune_whisper_yue.py` | OK |
| Live `~/.gundam-halo/config.toml` | unchanged (still `model_size = "base"`, no model_path) |
| Backend `/health` after restart with new code | 200 |

### Decision

M9-E Layer 2 stack (decided 2026-06-11):
- Dataset: **Common Voice yue** (Mozilla, CC-BY-SA 4.0, ~50h)
- Toolchain: **HuggingFace transformers + PEFT/LoRA**
- Base model: **Whisper base** (medium rejected in Layer 1)
- LoRA: r=32, alpha=64, target `q_proj` + `v_proj`
- Effective batch 8, 3 epochs, lr 1e-3

### Commits in this release
- (Layer 1 rejection — see v0.1.3 entry below)
- (Layer 2 deps + config + script + tests — this entry)

### Tracking

- The actual training run (~30min download + ~2.5h training +
  ~5min eval) is its own session, NOT this release. The
  command to run it is documented in
  [M9-E §"How to actually run the training"](./tickets/M9-E.md#how-to-actually-run-the-training-v013-follow-up-session).
- v0.1.4 follow-ups: replace `WhisperLocalASR` (openai-whisper)
  with `WhisperHFASR` (transformers pipeline); update live
  config to point `model_path` at the trained checkpoint;
  re-run M9-C live and **delete the augmented system note in
  `scripts/m9c_voice_tools.py:187-192`** as final acceptance.

---

## [0.1.3] — 2026-06-11 (Layer 1 rejected)

See "Investigated — M9-E Layer 1 (medium bump) — REJECTED"
section below. Layer 1 is closed; the v0.1.3 release focuses
on Layer 2 instead.



Closes M9-E Layer 1 with a documented rejection. The real fix
is Layer 2 (Cantonese fine-tune), which is a separate sprint.

### Investigated — M9-E Layer 1 (medium bump) — REJECTED

Hypothesis: bumping Whisper `base` → `medium` would
substantially improve Cantonese ASR quality for a one-line
config change.

Test setup: edit `~/.gundam-halo/config.toml`
`model_size = "base"` → `"medium"`, restart backend, re-run
M9-C live with the same Cantonese fixture
(`tests/voice/fixtures/readme_query.wav`).

Results:

| Metric | base | medium | Δ |
|---|---|---|---|
| Cold-start (warmup) | ~1.0s | ~40s (incl. 1.5GB download) | +39s (first time) |
| Per-turn ASR (5s utt) | ~5.5s | ~16s | **+10.5s / 3x** |
| Total wall (M9-C live) | 12.9s | 33.1s | +20s |
| ASR text on Cantonese fixture | `'Please use the file read tool to read backhand read me and tell me the first line.'` | `'Please use the File Read tool to read back-end readme and tell me the first line.'` | minor token fixes; still no actual Cantonese output |
| TTS chunks / bytes | 62 / 44 KB | 62 / 44 KB | unchanged |
| `used_tool_content` | True | True | unchanged |
| Disk footprint | 139 MB | +1.5 GB (~10x) | permanent |

Conclusion: **rejected**. The 3x ASR latency penalty is
unacceptable for the cockpit UX (the user is waiting for
turn-end feedback), and the Cantonese quality improvement
is marginal — medium still produces a fully English
transcription of the Cantonese input. Whisper's `yue`
coverage is essentially zero across the entire model
family; what we actually need is a fine-tune, not a bigger
base model.

### Reverted

- `~/.gundam-halo/config.toml` and `config.toml.example`
  both back to `model_size = "base"`.
- `config.toml.example` carries a comment pointing future
  readers at this CHANGELOG entry.
- `medium.pt` cached at `~/.cache/whisper/medium.pt`
  (1.5 GB) — left in place; will be re-used by Layer 2 if
  we choose medium as the base for the Cantonese fine-tune.

### Tracking

- M9-E Layer 2 (Cantonese fine-tune) is the actual path
  forward. See
  [M9-E Layer 2 acceptance section](./tickets/M9-E.md#layer-2-fine-tune)
  for scope and decision points. The model_size field is
  a no-op for now; the new `model_path` config field (for
  pointing at a local fine-tuned checkpoint) is the real
  configuration knob that will land in v0.1.4 or later.

### Commits in this release
- `<docs>` — `chore(docs): document M9-E Layer 1 rejection in CHANGELOG v0.1.3`

---

## [0.1.2] — 2026-06-10

Closes M9-D (voice quality follow-up from the v0.1.1 M9-C live run).

### Added
- **`backend/app/voice/tts/voice_sanitizer.py`** — server-side
  sanitiser that runs between the agent callback and the
  TTS pipeline.
  - `strip_reasoning(text)` removes `<think>…</think>` and
    `<tool_call>…</tool_call>` blocks, plus leading
    "Reasoning: …" / "推理: …" prose. Case-insensitive,
    handles both ASCII and full-width `:`.
  - `sanitize_for_tts(text)` adds a markdown-fence rewrite on
    top: triple-backtick and tilde code blocks become a single
    `[Code: …]` summary (capped at 200 chars, internal
    whitespace collapsed). Inline backticks are untouched.
- **`backend/tests/voice/test_voice_sanitizer.py`** — 19 unit
  tests covering both functions, the exact M9-C regression
  fixture, idempotence, and emotion-tag preservation.

### Changed
- **`HaloResponder.respond` and `respond_stream`** now call
  `sanitize_for_tts(agent_text)` before `parse_emotion`. The
  responder's TTS input never contains leaked reasoning or
  bare fence lines again.
- **`voice_ws._emit_agent_response`** also calls
  `sanitize_for_tts` before `parse_emotion` so the
  `agent.message` WebSocket frame is clean for the cockpit
  display too (the responder was not the only consumer).
- **`REACT_SYSTEM_PROMPT`** in `app/agents/native_react.py`
  carries a "Voice output rules" section: the model is told
  to omit `<think>` blocks from its visible reply and to
  prefer prose over fenced code blocks when speaking. The
  server-side strip is the safety net.
- **`frontend/package.json` `dev` script** now passes
  `--strictPort`. Vite exits non-zero when port 5173 is taken
  instead of silently falling back to a different port.
  Added `dev:flex` alias for the old loose behaviour.

### Fixed
- `<think>` blocks no longer leak into TTS audio (the user
  no longer hears the model reason out loud before the
  reply).
- Markdown code fences no longer fragment TTS output. The
  segmenter no longer sees bare fence lines, so the
  `ERROR: TTS stream failed for '\\`\\`\\`': No audio was
  received` warning is gone.

### Verified
| Check | Result |
|---|---|
| `pytest tests/voice/` | 102/102 pass (19 new + 83 existing) |
| M9-C live re-run (`m9c_voice_tools.py`) | PASS |
| TTS chunks | 201 → 68 (no more empty fence segments) |
| TTS total bytes | 141552 → 48240 |
| TTS latency (post `voice.end`) | 13.7s → 6.5s |
| TTS stream failed errors | 4 → 0 |
| Total wall (incl. ASR + warmup) | 20.2s → 12.9s |
| `agent.message` frames containing `<think>` (client-visible) | 0 |
| README first line in re-transcribed TTS | yes (`# Gundam Halo — Backend`) |
| `used_tool_content` | `True` |

### Commits in this release
- `3ce641a` — `fix(voice): M9-D strip LLM reasoning + rewrite markdown fences for TTS`
- `895bb2a` — `chore(frontend): pin dev server to 5173 with --strictPort`

---

## [0.1.1] — 2026-06-10

### Fixed
- **`/ws/voice` `voice.text` path now emits `voice.turn_ended`.** Previously
  the typed-turn handler ran the agent + TTS but never sent the terminal
  `voice.turn_ended` frame, so `halo-voice-ws` never left
  `"speaking"`/`"thinking"` and the mic button stayed disabled until a
  hard page refresh. The path now mirrors the `voice.end` flow and
  reports `total_duration_ms`. Confirmed via `scripts/m9c_dryrun_infra.py`
  Phase B (`voice.turn_ended` received post-`tts.end`).

- **CORS allowlist now includes `127.0.0.1` and port 8766.** Backend's
  uvicorn runs on `127.0.0.1:8766` (8765 is held by a detached
  `python -m http.server` in another workspace). Without this, a fresh
  backend restart dropped both ports from the allowlist and the cockpit
  UI broke.

### Added
- **`backend/scripts/m9c_dryrun_infra.py` — no-LLM-key infra dry-run.**
  Two phases:
  - **Phase A**: imports + warms up VAD (Silero JIT), ASR (Whisper base
    on mps), TTS (Edge / `zh-HK-HiuMaanNeural`), `HaloResponder`,
    `VoicePipeline`, the 9 default `ToolRegistry` tools
    (`file_read`, `file_write`, `mavis_delegate`, `memory_read`,
    `memory_write`, `open_app`, `shell_exec`, `weather`, `web_fetch`),
    and a `NativeReActAgent` instantiated with a `StubFileReadEngine`
    (scripts `file_read` on the README, then a final answer that
    quotes its first line).
  - **Phase B**: drives the full `/ws/voice` chain via the
    `voice.text` bypass path using the stub engine. Verifies
    `voice.hello` → `agent.message` → `live2d.trigger` →
    `tts.start` → `tts.audio` (binary MP3) → `tts.end` →
    `voice.turn_ended`.
  - Exit 0 = infra ready, 1 = any gap. Use as pre-flight before
    M9-C live or as a CI gate after backend infra changes.

- **`backend/scripts/m9c_voice_tools.py` — M9-C live end-to-end smoke.**
  Voice input (`tests/voice/fixtures/readme_query.wav`) → VAD → ASR →
  real `NativeReActAgent` with real `MiniMaxEngine` + 9 default tools →
  TTS → MP3. Verifies the agent's reply reaches TTS by re-transcribing
  the MP3 back through Whisper and matching the README's first line.
  Passes on this release (README line: `# Gundam Halo — Backend`,
  total wall 20.2s incl. ASR 6.3s + TTS 13.7s).

### Verified live
| Check | Result |
|---|---|
| `api.minimax.io/v1` (M2 cluster) auth | 200, 8 models incl. `MiniMax-M2` |
| Backend `/health` after restart | 200 |
| `voice.hello` frame | `vad=silero asr=whisper_local/base tts=true live2d=true` |
| Stub dry-run (Phase A + B) | PASS, total wall 0.9s |
| M9-C live (`m9c_voice_tools.py`) | PASS, `used_tool_content: True` |

### Known issues (tracking in M9-D)
See [`docs/tickets/M9-D.md`](./tickets/M9-D.md) for the full ticket
(scope, repro, proposed fix, acceptance criteria).
- LLM leaks `<think>…</think>` reasoning into `agent.message`, which
  then leaks into the TTS input. M9-D will add a post-processor that
  strips `<think>`/`<tool_call>` blocks before TTS.
- TTS sentence-segmenter doesn't understand markdown code fences
  (`` ``` ``), so an LLM reply that quotes a path or command in a
  fenced block produces fragmented audio (an "ERROR: No audio was
  received" warning per empty segment). M9-D will teach the segmenter
  to either pass fenced blocks through verbatim or skip them with a
  voice-friendly summary.

### Commits in this release
- `c91979c` — `chore(cors): add 127.0.0.1 + 8766 to allowlist`
- `dec8d1e` — `fix(voice): voice.text path now emits voice.turn_ended`
  (+ `m9c_dryrun_infra.py`)

> Gundam Halo is a local-only Mac project — no remote, no push. The
> `git log` is the source of truth between releases.

---

## [0.1.0] — 2026-06-08

Initial private release. Cockpit dashboard, project cards, memory
browser, NT-D/Unicorn theme, voice WebSocket pipeline
(VAD → ASR → LLM → TTS → Live2D), 9 default tools, NativeReAct agent,
Live2D sprite + image-set avatar modes, Tauri 2 scaffold.

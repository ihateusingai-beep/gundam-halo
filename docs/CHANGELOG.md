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

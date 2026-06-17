# Feature Spec — Sprint 26: v0.1.5 — post-v0.1.4 cleanup (Layer 2 v2 + supervisor + held-out eval)

> **Status:** DRAFT — proposed Sprint 26 scope.
> **This is a SPEC-ONLY sprint.** No code is
> written. The implementation lands in Sprint
> 27+ when the user has capacity for the
> post-v0.1.4 cleanup work.
> **Predecessors:**
> - Sprint 22 (commit `e0b87f9`) shipped the
>   v0.1.4 rollout plan.
> - Sprint 23 (commit `4e85e99`) shipped
>   Tracks 1, 2, 4.
> - Sprint 24 (commit `c24eb85`) shipped
>   the acceptance gate workflow.
> - Sprint 25 (commit `1461ce8`) shipped
>   the Track 3 impl template (1-commit
>   deletion + revert path).
> **v0.1.4 land pre-condition:** the user has
> completed the M9-E Layer 2 training run
> (Sprint 19d runbook) and shipped the
> Sprint 25 commit (Track 3 deletion). v0.1.4
> is tagged in main.
> **Scope:** spec-only freeze for 4
> post-v0.1.4 tracks (Layer 2 v2 self-record
> corpus + launchd supervisor + held-out
> Cantonese eval + mlx-whisper inference
> accelerator). Total: ~3-5 days wall clock
> when implemented, spread across 2-3 sprints
> (27+).
> **Out of scope (deferred to 28+):** iOS /
> iPadOS, code-switch tolerance (per M9-E
> §"Out of scope"), ASR streaming, multi-
> speaker / diarisation, Whisper large-v3
> evaluation.

---

## 0. Why this sprint exists

Sprints 22-25 ship the v0.1.4 land: the
fine-tuned Cantonese Whisper model is
trained, the `WhisperHFASR` backend is
shipped, the `whisper_local` `model_path`
warning is replaced with a `ValueError`,
the Sprint 17a upgrade banner is removed,
and the M9-C augmented system note
workaround is deleted. v0.1.4 is the
**production-grade Cantonese baseline**:
WER < 20% on Common Voice yue, agent
uses `file_read` endogenously, no
workarounds.

But v0.1.4 is not the end of the M9-E
roadmap. The M9-E ticket (line 80, 238-243,
337-338, 349-350) calls out a Layer 2 v2
**self-record corpus** path that personalises
the fine-tune to a single user's voice.
Sprint 19b §2 defers a launchd supervisor
that survives backend crashes and starts
at boot. M9-E line 255-257 mentions mlx-
whisper as a faster inference accelerator
on Apple Silicon. And the v0.1.4 acceptance
test (`used_tool_content == True` on
`backend/tests/voice/fixtures/readme_query.wav`)
is a **synthesised Cantonese fixture** —
a held-out test (user-recorded, ~30s) is
needed to verify the fine-tune works on
the user's actual voice, not just a
read-aloud test prompt.

Sprint 26 is the design freeze for the
**post-v0.1.4 cleanup**. The user picks
which of the 4 tracks to implement first
based on what they care about most:
personalisation (Layer 2 v2), availability
(supervisor), accuracy on real voice
(held-out eval), or speed (mlx-whisper).
Sprint 26 is a menu, not a single commit
— the user can ship the 4 tracks in
any order over multiple sprints.

## 1. Goals

1. **Document the 4 post-v0.1.4 tracks** so
   the user can pick the order based on
   priority. Each track has a clear
   acceptance criterion, risk register,
   and file-by-file change set.
2. **Capture the Layer 2 v2 self-record
   path** end-to-end: Tauri app records
   mic on demand, 30-min user session,
   fine-tune on the user's voice, swap
   the model in `~/.gundam-halo/`, verify
   the held-out test passes. This is the
   single biggest quality improvement
   available after v0.1.4.
3. **Capture the launchd supervisor path**
   so the user can run the backend as a
   daemon that survives crashes and starts
   at boot. The supervisor uses the
   existing `os.execvp` self-restart
   pattern (Sprint 19b) — the launchd
   plist just wraps it.
4. **Capture the held-out Cantonese eval
   path** so the v0.1.5 acceptance test
   is on real user-recorded audio, not
   just the synthesised M9-C fixture.
   The 25-case eval set
   (`scripts/cantonese_eval.py`) is the
   baseline; Sprint 26 adds a 30-sec
   user-recorded held-out set.
5. **Capture the mlx-whisper inference
   accelerator** as an **optional
   drop-in for `WhisperHFASR`** that
   trades ~300ms per-turn latency for
   ~50% energy cost. The user picks
   based on their Mac's thermal headroom.
6. **No code is written in this sprint.**
   Sprint 26 is spec-only. The CHANGELOG
   entry is "Planned for v0.1.5+ (Sprint
   27+)".

## 2. Out of scope (deferred)

- **iOS / iPadOS** — per M9-E §"Out of
  scope" (line 294). The Gundam Halo
  cockpit is a Tauri desktop app, not
  a mobile app. A separate ticket
  (M14?) would be needed to port the
  voice layer to iOS, and that's a
  multi-month effort.
- **Code-switch tolerance** (mixed
  Cantonese + English + Mandarin in
  the same turn) — per M9-E §"Out of
  scope" (line 295). The Common Voice
  yue fine-tune is monolingual; code-
  switch requires a code-switch corpus
  (MDCC, line 234-235) and a different
  fine-tune recipe.
- **ASR streaming** (transcribe
  chunk-by-chunk instead of waiting
  for `voice.end`) — per M9-E
  §"Out of scope" (line 293). The
  current pipeline transcribes the
  whole turn at turn-end, which is
  fine for the cockpit's human-paced
  UX but doesn't help with sub-200ms
  streaming use cases.
- **Multi-speaker / diarisation** —
  per M9-E §"Out of scope" (line 294).
  Gundam Halo is a single-user project;
  diarisation is a different domain
  (WhisperX, pyannote.audio).
- **Whisper large-v3 evaluation** —
  per M9-E §"Out of scope" (line 297).
  Large-v3 is ~3GB and slow on MPS;
  not in scope for a single-user Mac
  project.

## 3. User-facing behavior

This sprint is **invisible to the user
until Sprint 27+ lands at least one
track**. The 4 tracks are:

- **Track 1 — Layer 2 v2 self-record
  corpus**: The user opens the Tauri
  cockpit, clicks "Record 30 min of
  Cantonese", speaks for 30 minutes
  (the app records + transcribes in
  parallel, the user can stop early or
  extend). The recording is saved to
  `~/.gundam-halo/recordings/yue-self-2026-06-17/`
  with timestamps. The user runs a
  re-training command that mixes the
  self-record corpus with the Common
  Voice yue corpus (50/50 mix) and
  fine-tunes for 1 hour. The new
  checkpoint is saved to
  `~/.gundam-halo/models/whisper-yue-self-2026-06-17/`.
  The user updates `~/.gundam-halo/config.toml`
  to point `model_path` at the new
  checkpoint. The M9-C live re-run with
  the user's voice now produces
  WER < 10% (vs. < 20% on Common Voice
  yue only). The user has a personalised
  model.
- **Track 2 — launchd supervisor**: The
  user runs `bash scripts/install-launchd.sh`
  once. The script copies a `.plist` file
  to `~/Library/LaunchAgents/com.gundam.halo.plist`
  and `launchctl load`s it. The backend
  now starts at boot and auto-restarts
  on crash. The user can still launch
  the backend manually (`./run.sh`) for
  dev — the launchd plist only fires if
  the user isn't already running the
  backend (the `launchctl` `KeepAlive`
  flag respects a lock file at
  `~/.gundam-halo/.backend.lock`).
- **Track 3 — held-out Cantonese eval**:
  The user records 30 seconds of
  Cantonese (a different prompt from
  the M9-C fixture, e.g. "what's the
  weather today" or "read me the first
  three lines of the README"). The
  recording is saved to
  `~/.gundam-halo/recordings/held-out-2026-06-17.wav`
  with a hand-typed transcript. The
  user runs `pytest
  tests/voice/test_held_out_eval.py -v`
  — the test loads the held-out WAV,
  transcribes with the fine-tuned
  WhisperHFASR backend, and asserts
  WER < 15% on the user's voice. The
  test fails if WER > 15% (the
  fine-tune didn't personalise enough
  — back to Track 1 with more
  self-record data).
- **Track 4 — mlx-whisper inference
  accelerator** (optional): The user
  sets `device = "mlx"` in
  `~/.gundam-halo/config.toml`. The
  `WhisperHFASR` backend swaps to
  `mlx-whisper` for inference (the
  training still uses HF + LoRA per
  Sprint 19d). Per-turn latency drops
  from ~600ms to ~300ms on M-series
  (per mlx-whisper benchmarks).
  Energy cost drops ~50%. The trade-off
  is mlx-whisper's API is less mature
  than the HF pipeline (no
  `generate_kwargs.language` hint at
  the time of writing — the user has
  to wrap the model with their own
  prompt logic). For Cantonese, the
  language hint is critical, so this
  trade-off may not be worth it. The
  user can `git revert` Track 4 if
  the language hint gap is a blocker.

## 4. Architecture

### 4.1 Track 1 — Layer 2 v2 self-record corpus

The Tauri app gains a new page:
**Settings → Voice → Personalised Fine-tune**.
The page has 3 sections:

1. **Record** — "Click to start recording.
   Speak Cantonese for 30 minutes. The
   app saves audio chunks every 30s to
   `~/.gundam-halo/recordings/yue-self-<date>/`
   and transcribes them in parallel using
   the v0.1.4 `WhisperHFASR` backend. The
   transcriptions are saved as a JSONL
   manifest with `{audio_path, text,
   duration_s, sample_rate}`. The user
   can stop early (min 10 min) or extend
   (max 60 min). At 30 min, the app
   auto-stops and shows a summary
   (total duration, sample count, average
   SNR, any low-quality chunks flagged)."
2. **Train** — "Run the personalised
   fine-tune. This loads the v0.1.4
   checkpoint (Common Voice yue only)
   as the base, fine-tunes on the
   self-record corpus (50/50 mix with
   Common Voice yue, 1 hour wall
   clock on M-series), and saves the
   new checkpoint to
   `~/.gundam-halo/models/whisper-yue-self-<date>/`.
   The training runs in a background
   subprocess (the Tauri app shows
   progress via a polled log file).
   The user can keep using the cockpit
   while the training runs."
3. **Swap** — "When the training
   completes, click 'Activate
   personalised model' to update
   `~/.gundam-halo/config.toml` to
   point `model_path` at the new
   checkpoint. The backend restarts
   (Sprint 19b self-restart) and the
   cockpit now uses the personalised
   model. The previous v0.1.4
   checkpoint is kept as a fallback
   (the user can revert with
   `git checkout` on the config.toml
   + backend restart)."

**Code changes**:
- **frontend**: `routes/settings/VoiceTab.tsx`
  — new "Personalised Fine-tune" section
  with 3 cards (Record / Train / Swap).
  Uses the existing
  `useVoiceInput` hook for the record
  card (Sprint 18 hoisted it to
  CockpitLayout). New IPC commands
  to the Tauri backend: `start_record`,
  `stop_record`, `start_train`,
  `get_train_progress`, `activate_model`.
- **backend** (Tauri): `src-tauri/src/`
  new commands: `start_record`,
  `stop_record`, `start_train`,
  `get_train_progress`, `activate_model`.
  Reuses the existing
  `finetune_whisper_yue.py` script
  via subprocess (the Tauri command
  spawns the script with the
  self-record corpus + the v0.1.4
  checkpoint as the base).
- **backend** (Python): no new code
  needed — the existing
  `finetune_whisper_yue.py` accepts
  `--base_model_path` (the v0.1.4
  checkpoint to continue from) and
  `--train_audio_dir` (the
  self-record manifest directory).
  Both flags are documented in the
  Sprint 19d §6 runbook.
- **storage**: `~/.gundam-halo/recordings/`
  is the new top-level dir. The
  manifest format is JSONL with
  `{audio_path, text, duration_s,
  sample_rate}`. The existing
  `prepare_common_voice_yue`
  (Sprint 21) handles the self-record
  manifest the same way it handles
  the Common Voice yue manifest —
  one extra `data_source` field
  in the parquet output.

**Test changes**:
- `tests/voice/test_finetune_script.py`
  — add a test for the
  `--base_model_path` flag (the
  existing 9 tests don't cover it).
- `tests/voice/test_self_record_manifest.py`
  NEW — 5-8 tests for the
  self-record manifest format (the
  `prepare_common_voice_yue` adapter
  for the self-record JSONL).

**Acceptance criterion**:
- The user records 30 min of Cantonese
  via the Tauri app.
- The personalised fine-tune runs to
  completion (1 hour wall clock).
- The user activates the personalised
  model.
- The held-out test (Track 3) passes
  with WER < 15% (vs. < 20% on
  Common Voice yue only).

### 4.2 Track 2 — launchd supervisor

**Scope**: a `.plist` file in
`~/Library/LaunchAgents/` that:
- Runs the backend (`./run.sh`) at
  user login.
- Auto-restarts on crash (with a
  5-second backoff).
- Respects a lock file at
  `~/.gundam-halo/.backend.lock`
  so the user can run the backend
  manually for dev without
  interference.
- Logs to
  `~/.gundam-halo/logs/launchd-stdout.log`
  and `launchd-stderr.log`.

**Code changes**:
- **scripts**: `scripts/install-launchd.sh`
  NEW — copies the `.plist` to
  `~/Library/LaunchAgents/`, runs
  `launchctl load`, verifies the
  backend started.
- **scripts**: `scripts/com.gundam.halo.plist`
  NEW — the actual launchd
  configuration. ~30 lines of XML
  with `KeepAlive` + `RunAtLoad`
  + `StandardOutPath` +
  `StandardErrorPath` + `WorkingDirectory`.
- **scripts**: `scripts/uninstall-launchd.sh`
  NEW — `launchctl unload` + rm
  the `.plist`. The user can disable
  the supervisor without losing
  data.
- **backend**: `app/core/lockfile.py`
  NEW — the lock file helper. The
  `create_app()` lifespan acquires
  the lock; if another instance is
  already running, the new instance
  exits cleanly. The lock file
  is checked at startup AND on
  every config-driven restart
  (Sprint 19b's `os.execvp` path).

**Test changes**:
- `tests/test_launchd_plist.py`
  NEW — 3-5 tests that lint the
  `.plist` XML (no missing
  required keys, valid `KeepAlive`
  syntax, paths expand correctly).
- `tests/core/test_lockfile.py`
  NEW — 4-6 tests for the lock
  file acquire / release /
  conflict-detection logic.

**Acceptance criterion**:
- The user runs
  `bash scripts/install-launchd.sh`.
- `launchctl list | grep gundam-halo`
  shows the daemon PID.
- The user kills the backend process
  manually. Within 5 seconds,
  `launchd` re-spawns the backend.
- The user runs the backend manually
  (`./run.sh`) without first
  unloading the daemon. The manual
  instance sees the lock file
  conflict and exits; the daemon's
  instance continues running.

### 4.3 Track 3 — held-out Cantonese eval

**Scope**: a new test file
`tests/voice/test_held_out_eval.py`
that loads a user-recorded WAV + a
hand-typed transcript, transcribes
with the v0.1.4 `WhisperHFASR` backend,
and asserts WER < 15%. The test
**skips** if the held-out WAV is
missing (the user has to record it
once before the test runs).

**Code changes**:
- **scripts**: `scripts/record-held-out.sh`
  NEW — a 5-min interactive shell
  script that prompts the user to
  record 30s of Cantonese, plays
  the recording back, and asks the
  user to type the correct transcript.
  The script writes
  `~/.gundam-halo/recordings/held-out-<date>.wav`
  and
  `~/.gundam-halo/recordings/held-out-<date>.txt`.
- **backend**: `tests/voice/test_held_out_eval.py`
  NEW — 3-4 tests:
  - `test_held_out_eval_loaded` —
    loads the WAV, transcribes with
    WhisperHFASR, asserts the
    transcribe call doesn't raise.
    **No WER assertion** (we don't
    know the user's expected WER).
  - `test_held_out_eval_wer_below_threshold`
    — asserts WER < 15% (or a
    user-configurable threshold
    via `~/.gundam-halo/test-config.toml`).
  - `test_held_out_eval_skips_when_missing` —
    asserts the test skips with a
    clear message if the held-out
    WAV is missing (the user hasn't
    run `record-held-out.sh` yet).

**Test changes**: the test file is
new; no existing test changes.

**Acceptance criterion**:
- The user runs
  `bash scripts/record-held-out.sh`
  once (5 min).
- The user runs
  `pytest tests/voice/test_held_out_eval.py -v`.
- The test passes with WER < 15%
  on the v0.1.4 WhisperHFASR backend.
- If the user has Track 1 (Layer 2
  v2 self-record) active, the test
  passes with WER < 10%.

### 4.4 Track 4 — mlx-whisper inference accelerator

**Scope**: an optional `device = "mlx"`
flag in `WhisperHFASR` that swaps the
inference path from the HF `pipeline`
to `mlx-whisper` (a separate package
`mlx-whisper` on PyPI, ~50MB). The
training still uses HF + LoRA per
Sprint 19d; only inference swaps.

**Code changes**:
- **backend**: `app/voice/asr/whisper_hf.py`
  — add a new `_invoke_pipeline_mlx`
  method that uses `mlx_whisper.transcribe`
  instead of the HF pipeline. The
  `WhisperHFASR.__init__` accepts a
  new `inference_backend: str = "hf"`
  field (`"hf" | "mlx"`). The factory
  forwards `device = "mlx"` to
  `inference_backend = "mlx"`.
- **pyproject.toml**: new `voice-hf-mlx`
  optional extra: `mlx-whisper>=0.4`,
  `mlx>=0.20`, `numpy>=1.26`. Total
  ~500MB on top of the `voice-hf`
  extra (mlx itself is heavy). The
  default install (`uv sync --extra
  voice --extra voice-hf`) does NOT
  pull this; the user opts in with
  `uv sync --extra voice-hf-mlx`.
- **memory**: the new
  `python-backend-patterns.md` §9
  should document the mlx import
  path (mlx is `darwin-only`; raise
  `ASRError` with a clear message
  on non-Mac platforms).

**Test changes**:
- `tests/voice/test_whisper_hf.py`
  — add 3-4 tests for the
  `inference_backend = "mlx"` path
  (mocked — mlx is not installed in
  the test env). The tests verify
  the lazy import + the ASRError
  on non-Mac.

**Acceptance criterion**:
- The user runs
  `uv sync --extra voice-hf-mlx`.
- The user sets `device = "mlx"`
  in `~/.gundam-halo/config.toml`.
- The user restarts the backend.
- The user runs a 5-second
  Cantonese utterance. The
  per-turn latency drops from
  ~600ms (HF pipeline) to ~300ms
  (mlx-whisper).
- The user verifies WER is
  unchanged (< 20% on Common Voice
  yue, < 15% on the held-out
  test from Track 3).

**Caveat**: mlx-whisper's API
**doesn't support `language =
"cantonese"` in `generate_kwargs`**
at the time of writing (per
public benchmarks). The
Cantonese language hint has to be
applied via prompt engineering
on the decoder side, which is
non-trivial. The user may find
that mlx-whisper's WER on
Cantonese is **worse** than the
HF pipeline's because the
language hint gap. If the WER
regresses, the user reverts Track
4 (`git revert <commit-hash>`)
and stays on the HF pipeline.

## 5. File-by-file change set (when Sprint 27+ lands)

| Path | Change | LoC est. |
|---|---|---|
| **Track 1 — Layer 2 v2 self-record** | | |
| `frontend/src/routes/settings/VoiceTab.tsx` | New "Personalised Fine-tune" section (3 cards) | +200 / 0 |
| `frontend/src-tauri/src/commands.rs` | New IPC commands (start_record, stop_record, start_train, etc.) | +150 / 0 |
| `frontend/src-tauri/src/recording.rs` | NEW — record + transcribe parallel pipeline | +200 / 0 |
| `backend/scripts/finetune_whisper_yue.py` | Document `--base_model_path` and `--train_audio_dir` flags (no new code) | +30 / 0 |
| `backend/tests/voice/test_finetune_script.py` | Add 1 test for `--base_model_path` flag | +30 / 0 |
| `backend/tests/voice/test_self_record_manifest.py` | NEW — 5-8 tests for self-record manifest | +150 / 0 |
| **Track 2 — launchd supervisor** | | |
| `scripts/install-launchd.sh` | NEW — copy `.plist` + `launchctl load` | +50 / 0 |
| `scripts/com.gundam.halo.plist` | NEW — launchd configuration XML | +30 / 0 |
| `scripts/uninstall-launchd.sh` | NEW — `launchctl unload` + rm | +20 / 0 |
| `backend/app/core/lockfile.py` | NEW — lock file acquire / release / conflict | +80 / 0 |
| `backend/app/main.py` | Wire lock file into `create_app()` lifespan | +10 / 0 |
| `backend/tests/test_launchd_plist.py` | NEW — 3-5 lint tests | +100 / 0 |
| `backend/tests/core/test_lockfile.py` | NEW — 4-6 lock file tests | +120 / 0 |
| **Track 3 — held-out Cantonese eval** | | |
| `scripts/record-held-out.sh` | NEW — interactive 5-min record + transcribe | +80 / 0 |
| `backend/tests/voice/test_held_out_eval.py` | NEW — 3-4 held-out eval tests | +100 / 0 |
| **Track 4 — mlx-whisper accelerator** | | |
| `backend/app/voice/asr/whisper_hf.py` | Add `inference_backend: str = "hf"` field + `_invoke_pipeline_mlx` method | +80 / 0 |
| `backend/app/voice/asr/asr_factory.py` | Forward `device = "mlx"` to `inference_backend = "mlx"` | +20 / 0 |
| `backend/pyproject.toml` | New `voice-hf-mlx` extra | +5 / 0 |
| `backend/tests/voice/test_whisper_hf.py` | Add 3-4 tests for `inference_backend = "mlx"` (mocked) | +100 / 0 |
| `docs/CHANGELOG.md` | v0.1.5 release entry per track | +120 / 0 |
| `docs/tickets/M9-E.md` | Update Layer 2 v2 status when Track 1 lands | +10 / 0 |

**Total**: ~1,485 LoC across 18 files. ~3-5
days wall clock when implemented, spread
across Sprint 27 (Track 1+3, ~2 days),
Sprint 28 (Track 2, ~0.5 day), Sprint 29
(Track 4, ~1-2 days).

The user can pick any order. The most
likely sequence is:

- **Sprint 27**: Track 3 (held-out eval)
  first, because it's a 1-day sprint
  that gives the user the **baseline
  WER measurement** before they invest
  in Track 1. The held-out test is the
  gate for Track 1's success.
- **Sprint 28**: Track 1 (Layer 2 v2)
  once the held-out test confirms the
  v0.1.4 model is good but not
  personalised. The self-record
  corpus is the user-driven step
  (30 min recording + 1 hour training).
- **Sprint 29**: Track 2 (launchd
  supervisor) as a quality-of-life
  improvement. The supervisor is
  optional — the user can still run
  the backend manually.
- **Sprint 30+**: Track 4 (mlx-whisper)
  as an experiment. If the WER
  regresses, revert and skip.

## 6. Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **Layer 2 v2 self-record corpus is too small** | Medium | High | The Common Voice yue mix (50/50) gives the personalised model a base of ~50h of public data. The 30-min self-record is for personalisation, not baseline. The user can extend to 60 min if the held-out test still shows WER > 15%. |
| **Personalised fine-tune overfits to the user's recording conditions** | Medium | Medium | The held-out test (Track 3) is recorded in different conditions (different mic, different room) to catch overfit. If the held-out test fails, the user re-trains with more Common Voice yue in the mix (e.g. 70/30 Common Voice / self-record). |
| **launchd supervisor and manual dev mode conflict** | Medium | Medium | The lock file at `~/.gundam-halo/.backend.lock` prevents both from running at the same time. The lock is acquired at `create_app()` lifespan startup. If the manual instance can't acquire the lock, it exits with a clear error pointing at the daemon. |
| **launchd plist is too permissive** | Low | Medium | The plist uses `KeepAlive` with `SuccessfulExit=false` (the daemon restarts on crash, not on clean exit). The user can `launchctl unload` to disable. The `WorkingDirectory` is the user's Gundam Halo checkout (not `/`). |
| **Held-out test is too lenient (WER threshold too high)** | Medium | Low | The threshold is user-configurable via `~/.gundam-halo/test-config.toml`. The default is 15% (vs. 20% on Common Voice yue). The user can tighten to 10% if they want a stricter gate. |
| **Held-out test is too strict (WER threshold too low)** | Low | Low | Same as above — user-configurable. The test is **skipped** if the held-out WAV is missing, so the test is never a CI blocker. |
| **mlx-whisper doesn't support `language = "cantonese"`** | High | High | The WER on Cantonese regresses. The user reverts Track 4 (`git revert <hash>`) and stays on the HF pipeline. The mlx-whisper path is **optional**; the HF pipeline is the default. |
| **mlx-whisper install breaks the venv** | Low | Low | The `voice-hf-mlx` extra is opt-in (`uv sync --extra voice-hf-mlx`). The user can `uv sync --extra voice-hf` to restore the baseline without mlx. The mlx package is `darwin-only`; on non-Mac platforms the import raises a clear error. |
| **Self-record corpus has PII concerns** | Low | Medium | The corpus is stored in `~/.gundam-halo/recordings/` (user's local disk, not cloud). The user can delete the directory with `rm -rf ~/.gundam-halo/recordings/`. The cockpit privacy toggle (per M9-E ticket line 242) gates the record button. |
| **Held-out test becomes a flaky test (user's voice varies day-to-day)** | Low | Low | The WER threshold (15%) is loose enough to absorb day-to-day variation. If the test becomes flaky, the user can mark it `xfail` in pytest or move it to a manual `make held-out-eval` target. |
| **Personalised fine-tune takes longer than 1 hour** | Medium | Low | The training script is monitored by `finetune_whisper_yue_monitor.py` (Sprint 19d addendum). If the monitor detects a hang (no progress for >30 min), it exits 4 and the user can `kill` the training. The Common Voice yue materialisation is cached, so the re-run is faster on a second pass. |
| **The 4 tracks are too ambitious for one sprint** | High | Medium | The user picks the order based on priority. Track 3 (held-out eval) is the smallest and ships first as Sprint 27. Track 1 (Layer 2 v2) is the largest and ships as Sprint 28. Track 2 (launchd) is medium and ships as Sprint 29. Track 4 (mlx-whisper) is experimental and may not ship at all. |

## 7. Acceptance tests

1. **Track 1 — personalised fine-tune
   produces a checkpoint** —
   `bash scripts/install-self-record-pipeline.sh`
   (or the Tauri app's Record card) +
   the training run +
   `ls ~/.gundam-halo/models/whisper-yue-self-<date>/`
   shows `config.json` + `model.safetensors`
   + `tokenizer.json`.
2. **Track 1 — held-out test passes with
   WER < 10% on the personalised model**
   — `pytest tests/voice/test_held_out_eval.py -v`
   with the personalised model active.
3. **Track 2 — backend survives a crash**
   — `kill -9 <backend-pid>` →
   within 5 seconds, `launchctl list | grep gundam-halo`
   shows a new PID. `curl localhost:8765/api/health`
   returns 200.
4. **Track 2 — manual dev mode doesn't
   conflict with the daemon** — the user
   runs `./run.sh` without unloading
   the daemon. The manual instance
   exits with a "lock file conflict"
   error. The daemon's instance
   continues running.
5. **Track 3 — held-out test loads the
   user's recording** —
   `pytest tests/voice/test_held_out_eval.py -v`
   passes the "loaded" test (the
   WAV is found, the transcribe call
   succeeds, no WER assertion yet).
6. **Track 3 — held-out test asserts
   WER < 15%** — same command, full
   assertion. WER is computed and
   reported in the test output.
7. **Track 4 — mlx-whisper install
   succeeds on Mac** — `uv sync
   --extra voice-hf-mlx` exits 0.
   `python -c "import mlx_whisper; print(mlx_whisper.__version__)"`
   prints the version.
8. **Track 4 — mlx-whisper inference
   is faster than HF pipeline** — the
   user measures per-turn latency on
   a 5-second Cantonese utterance.
   Target: < 400ms (vs. ~600ms for HF
   pipeline).
9. **Track 4 — mlx-whisper WER is
   within 1% of HF pipeline WER** —
   the held-out test (Track 3) passes
   with `inference_backend = "mlx"`
   AND `inference_backend = "hf"`.
   If the WER regresses by > 1%, the
   user reverts Track 4.
10. **No regression** — all 188
    backend voice tests + 2 skipped
    from Sprint 23 still pass. All
    63 frontend vitest tests still
    pass. The M9-C live re-run
    (with v0.1.4 code) still passes
    with `used_tool_content == True`.

## 8. Sign-off

- [ ] **4 tracks agreed as the post-v0.1.4
      menu** — Track 1 (Layer 2 v2
      self-record), Track 2 (launchd
      supervisor), Track 3 (held-out
      Cantonese eval), Track 4 (mlx-whisper
      inference accelerator).
- [ ] **Track ordering recommended**
      — Track 3 first (1 day, gives
      baseline WER), Track 1 second
      (1-2 days, the user-driven
      personalisation), Track 2 third
      (0.5 day, quality-of-life),
      Track 4 fourth (1-2 days,
      experimental, may not ship).
- [ ] **Out-of-scope items confirmed**
      — iOS / iPadOS, code-switch
      tolerance, ASR streaming,
      multi-speaker / diarisation,
      Whisper large-v3 evaluation
      all deferred to Sprint 30+
      (or separate tickets).

---

## Appendix A — Why 4 tracks, not 1 sprint per track

Sprint 26 is a **menu sprint**, not a
single-commit sprint. The reason: the
4 tracks are **independent** in
implementation but **interdependent**
in dependency graph:

- Track 1 (Layer 2 v2) depends on
  Track 3 (held-out eval) for the
  WER measurement.
- Track 2 (launchd supervisor) is
  independent of all the others.
- Track 4 (mlx-whisper) is independent
  of all the others but is **experimental**
  and may not ship.

If the 4 tracks were combined into
a single sprint, the user would have
to commit to all 4 simultaneously
or none. The menu-sprint pattern lets
the user pick the order based on
priority:

- If the user cares about quality
  most: Tracks 3 + 1.
- If the user cares about
  availability most: Track 2.
- If the user cares about speed
  most: Track 4 (with the caveat
  that it may not ship).

The spec captures the **shape** of
all 4 tracks so the user can decide
the order without re-deriving the
design.

## Appendix B — Track 4 (mlx-whisper) caveat

mlx-whisper's API **doesn't support
`language = "cantonese"` in
`generate_kwargs`** at the time of
writing (per mlx-whisper's public
docs, mid-2026). The user has 2
options to bridge the gap:

1. **Post-process the model's
   output** with a language hint:
   after the transcribe call, run
   the text through the BERT
   corrector (already shipped in
   Sprint 17b) to "Yue-ify" English
   hallucinations. The corrector is
   already trained on Cantonese +
   English code-switch (per Sprint
   17b Track C).
2. **Skip mlx-whisper for Cantonese**:
   use the HF pipeline (Track 4
   default) for Cantonese audio and
   mlx-whisper for English / Mandarin
   audio. The WhisperHFASR
   `inference_backend` field accepts
   a language-conditional backend
   (e.g. `{"yue": "hf", "en": "mlx"}`).

Option 1 is simpler (no per-language
routing logic). Option 2 is faster
for English (mlx-whisper's sweet
spot is English). The user picks
based on their typical use case.

If neither option works (e.g. the
BERT corrector doesn't fix the
language hint gap, or the
per-language routing is too
complex), the user reverts Track
4 and stays on the HF pipeline.
The HF pipeline is the default;
mlx-whisper is purely an
**optional accelerator**.

## Appendix C — Track 1 self-record
UX design

The self-record UX is a 3-card
flow (Record / Train / Swap). The
cards are intentionally **separate**
so the user can pause between steps
(e.g. record 30 min, then come
back later to train). The cards
also have **independent progress
indicators** so the user can see
each step's status without losing
the others.

- **Record card** shows: current
  duration, sample count, average
  SNR, low-quality chunks flagged.
  The user can stop early or extend.
  At 30 min, the card auto-stops
  and shows a summary.
- **Train card** shows: training
  status (idle / running /
  complete), training log tail
  (last 5 lines), epoch progress
  bar. The user can cancel the
  training (kills the subprocess;
  the partial checkpoint is deleted
  for cleanliness).
- **Swap card** shows: current
  model path (Common Voice yue or
  personalised), new model path
  (the personalised checkpoint
  when training completes), the
  "Activate personalised model"
  button. The user can revert to
  the Common Voice yue model with
  one click.

The cards are stored as
localStorage state (per the
existing CockpitLayout pattern) so
the user can navigate away and
back without losing the training
progress.

## Appendix D — Track 2 launchd plist
design

The launchd plist uses the
following keys (per Apple's
launchd.plist man page):

- `Label`: `com.gundam.halo` (the
  reverse-DNS identifier for
  `launchctl list`).
- `ProgramArguments`: array of
  strings — the absolute path
  to the user's `run.sh` + the
  `--no-interactive` flag (so the
  backend doesn't prompt for
  config on stdin).
- `WorkingDirectory`: the user's
  `~/workspace/working/gundam-halo/`
  (so `./run.sh` finds `backend/`
  and `frontend/` relative paths).
- `RunAtLoad`: `true` (start at
  user login).
- `KeepAlive`: dictionary with
  `SuccessfulExit: false` (restart
  on crash, not on clean exit).
- `StandardOutPath`:
  `~/.gundam-halo/logs/launchd-stdout.log`.
- `StandardErrorPath`:
  `~/.gundam-halo/logs/launchd-stderr.log`.
- `EnvironmentVariables`: dict
  with `HALO_HOME` set to
  `~/.gundam-halo/` (so the
  backend uses the user's
  config.toml, not the
  `HALO_HOME` env default).

The plist is **user-scoped**
(installed to
`~/Library/LaunchAgents/`), not
**system-scoped** (which would
require sudo and install to
`/Library/LaunchDaemons/`). The
user-scope is right for a
single-user Mac app.

The `install-launchd.sh` script
verifies the plist XML is well-formed
(before `launchctl load`) and
verifies the daemon started (after
`launchctl load`) by waiting 5
seconds and checking `launchctl
list | grep gundam-halo`.

## Appendix E — Test count evolution (cumulative)

| Sprint | New tests | Total backend voice |
|---|---|---|
| 23 (previous) | +38 | 140 |
| 24 (spec-only) | 0 | 140 |
| 25 (spec-only) | 0 | 140 |
| **26 (spec-only)** | **0** | **140** |
| 27 (Track 1 + 3) | +6-12 | 146-152 |
| 28 (Track 2) | +7-11 | 153-163 |
| 29 (Track 4) | +3-4 | 156-167 |

Sprint 26 is spec-only, so 0 new
tests. Sprint 27 adds 1 test
(`--base_model_path` flag) + 5-8
self-record manifest tests + 3-4
held-out eval tests = 6-12 new
tests. Sprint 28 adds 3-5 launchd
plist tests + 4-6 lock file tests
= 7-11 new tests. Sprint 29 adds
3-4 mlx-whisper tests (mocked).

The mlx-whisper tests are mocked
because mlx is darwin-only and
~500MB; the test env doesn't
have it installed. The tests
verify the lazy import + the
`ASRError` on non-Mac platforms,
not the actual mlx-whisper
inference.

## Appendix F — Why Sprint 26 is
spec-only (not 26 = 4 separate
specs or 1 big impl sprint)

Sprint 26 is a **single spec**
capturing all 4 tracks. The
alternatives are:

- **4 separate specs** (Sprint 26a,
  26b, 26c, 26d): more admin
  overhead, but each spec is
  ~200 lines. The 4 tracks share
  dependencies (the held-out eval
  is the gate for Layer 2 v2; the
  launchd plist is independent but
  lives in the same `scripts/`
  directory as the install
  scripts), so a single spec
  captures the cross-track
  design decisions.
- **1 big impl sprint**: the user
  has to commit to all 4 tracks
  simultaneously. The menu-sprint
  pattern lets the user pick the
  order based on priority.

The single-spec pattern matches
Sprint 22 (1 spec, 4 tracks,
3 of which shipped in Sprint 23)
and Sprint 24 (1 spec, the
acceptance gate workflow that
the Sprint 25 impl template
uses). The pattern is **1
spec-only sprint to freeze the
design, then 1+ impl sprints
per track**.

## Appendix G — Sprint chain context

```
Sprint 25 (1461ce8) — Track 3 impl template + revert path
Sprint 24 (c24eb85) — Track 3 acceptance gate + M9-C double re-run
Sprint 23 (4e85e99) — v0.1.4 land impl (Tracks 1+2+4)
Sprint 22 (e0b87f9) — v0.1.4 land plan (4 tracks spec)
Sprint 21 (3353106) — prepare_common_voice_yue impl
Sprint 20 (ffc2624) — M9-E Layer 2 v0.1.4 rollout plan (spec-only)
Sprint 19d addendum (a8d8e17) — training monitor
Sprint 19d (0388699) — M9-E Layer 2 prep
Sprint 19c P2 (de87c1b) — always-on mic frontend
Sprint 19c P1 (756bee6) — always-on mic backend (VAD events)
Sprint 19b (69957b2) — auto-restart on ASR / corrector change
Sprint 19a (f8bbfa4) — fsmn-vad-online real per-frame speech probability
Sprint 18 (33aafaa) — cockpit audio-reactive HUD + ASR switcher
Sprint 17b (4d925ab → 48e4581) — Cantonese ASR (yuesub) + audio-reactive HUD
Sprint 17a (12ea7c7, 4db7d43) — voice hygiene
Sprint 16 (4e61b8f, b6e1989) — wake + VoiceTab
```

Sprint 26 is the **first post-v0.1.4
sprint** (assuming the user lands
Sprint 25 first). The v0.1.4 tag
in main marks the boundary between
"v0.1.4 land" and "v0.1.5+ cleanup".
Sprint 26 is in the v0.1.5+ phase.

The 4 tracks are **deferred to
v0.1.5+** because they're not
required for v0.1.4 to ship. v0.1.4
is the **Common Voice yue baseline**;
v0.1.5+ is the **personalisation
+ availability + speed** phase.

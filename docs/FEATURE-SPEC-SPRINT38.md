# Sprint 38 — Held-out Cantonese eval end-to-end (M9-E acceptance criterion 6)

**Date**: 2026-06-25
**Status**: Draft
**Author**: Mavis
**Priority**: High (closes the last unchecked M9-E acceptance criterion)

## Goal

Close **M9-E acceptance criterion 6**: "Held-out WER < 10% with personalised model active".
The pipeline has been ready since Sprint 33b (Tauri recording) + Sprint 30 Track B
(finetune script) — what's missing is:

1. `scripts/record-held-out.sh` — the interactive recorder (Sprint 26 §4.3 promised
   it; tests in `test_held_out_eval.py` skip with a clear message pointing at it,
   but the script was never written).
2. `scripts/setup-held-out-model.sh` — verify the openai-whisper `base.pt` model
   is cached (auto-download if missing). The Sprint 38 baseline uses
   `whisper_local` ASR backend with the cached `base.pt` (75 MB) — NOT the HF
   `whisper-yue-base` model. The HF path is reserved for the **personalised
   checkpoint swap** (Sprint 30 Track B `finetune_whisper_yue.py --base_model_path`).
   Sprint 38 ships the local ASR eval gate; the personalised fine-tune run
   remains a separate user-driven step.
3. `scripts/run_held_out_eval.py` — a CLI that runs real
   `WhisperLocalASR.transcribe` against the user's held-out WAV, computes WER,
   and prints pass/fail against `~/.gundam-halo/test-config.toml` threshold
   (default 15% per Sprint 26 §4.3 acceptance criterion 2; can be tightened to
   10% for the personalised model once training lands).
4. Tests for the 3 scripts (record + setup + eval).

The **live training run** (30-min self-record corpus → LoRA fine-tune → checkpoint
swap) is intentionally out of scope for the Sprint 38 commit — it requires the
user doing the actual recording via the Tauri app + ~1-2 hr wall clock on Apple
Silicon. Sprint 38 ships the **plumbing**; the live run is the user's next step
after the commit lands.

## Why openai-whisper base.pt (not HF)

The Sprint 38 baseline uses **`whisper_local` ASR** (not `whisper_hf`):

- `~/.cache/whisper/base.pt` is already on the user's Mac (Sprint 32 install
  pulled it as part of the `voice` extra's `openai-whisper>=20231117` dep).
  No download needed — `setup-held-out-model.sh` just verifies the file
  exists and prompts an `openai-whisper` download if not.
- 75 MB vs 750 MB — fits comfortably in any venv, no HF download dance.
- The Cantonese baseline quality is the **floor**: M9-E acceptance criterion 6
  wants WER < 10% on the **personalised** model. The base model is the
  control — its WER sets the regression bar for the fine-tune run.
- `WhisperLocalASR.transcribe(audio_bytes, sample_rate=16000)` is the same
  contract as `WhisperHFASR.transcribe(...)` — the test scaffolding in
  `test_held_out_eval.py` works without changes once we route the CLI
  through `asr_factory.create_asr(config)` (which picks `whisper_local`
  by default — `voice.asr.backend = "whisper_local"`).

When the personalised fine-tune lands (Sprint 30 Track B → user runs
`scripts/finetune_whisper_yue.py`), the user sets
`voice.asr.backend = "whisper_hf"` + `voice.asr.model_path = "<checkpoint dir>"`
in `~/.gundam-halo/config.toml` and re-runs `run_held_out_eval.py` — no script
changes needed (the CLI reads the config).

## Background

### What Sprint 26 / 32 already shipped

Per `docs/FEATURE-SPEC-SPRINT26.md` §4.3 + `docs/FEATURE-SPEC-SPRINT31.md`
Track 31-A:

- `tests/voice/test_held_out_eval.py` (3 tests) — loads the latest
  `~/.gundam-halo/recordings/held-out-<date>.wav`, calls `WhisperHFASR.transcribe`,
  asserts WER < threshold. All 3 tests **skip** with a clear message when no
  held-out WAV exists. The skip message points at
  `scripts/record-held-out.sh` — but that script was never written.
- `tests/voice/test_wer_helpers.py` (12 tests) — Levenshtein-based WER math.
- `tests/voice/test_finetune_script.py` — `finetune_whisper_yue.py --base_model_path`
  + `--train_audio_dir` CLI parser tests (training script itself is from Sprint 19d).
- `backend/app/voice/self_record_manifest.py` — JSONL manifest reader.

### What's missing

| Gap | Status |
|---|---|
| `scripts/record-held-out.sh` (Sprint 26 §4.3 promise) | ❌ Doesn't exist |
| `scripts/setup-held-out-model.sh` (verify cached `base.pt` from openai-whisper) | ❌ Doesn't exist |
| `scripts/run_held_out_eval.py` (CLI runner, not just pytest skip) | ❌ Doesn't exist |
| `~/.cache/whisper/base.pt` (openai-whisper base model) | ✅ Already cached (75 MB, was Sprint 32 `uv sync --extra voice` install) |
| User's held-out recording (`~/.gundam-halo/recordings/held-out-<date>.wav`) | ❌ Not recorded |
| Personalised fine-tune checkpoint (`~/.gundam-halo/models/whisper-yue-self-<date>/`) | ❌ Not trained |

The first 3 are Sprint 38 deliverables. The last 3 are user-driven live runs.

## Design

### 1. `scripts/record-held-out.sh` — interactive recorder

Interactive bash script. Uses `rec` from SoX (already a whisper dependency) or
macOS native `say`/quicktime. Records 30 s of mono 16 kHz s16le WAV to
`~/.gundam-halo/recordings/held-out-<date>.wav`, then prompts the user to type
the correct transcript in Cantonese (no validation — that's the user's job).

The script:
1. Verifies `~/.gundam-halo/recordings/` exists (creates if missing).
2. Detects a recording tool:
   - macOS: prefers `rec` from SoX (if installed); falls back to
     `afrecord` (built-in command-line recorder, mono 16 kHz).
   - Linux: `rec` from SoX.
3. Records 30 s, writes WAV.
4. Plays back via `afplay` / `aplay`.
5. Opens the user's `$EDITOR` on a `.txt` sidecar; user types the transcript.
6. Verifies the transcript is non-empty.
7. Prints the resulting file path + reminder to run pytest.

### 2. `scripts/setup-held-out-model.sh` — verify cached `base.pt`

The Sprint 38 baseline uses **openai-whisper's `base.pt`** (75 MB, already
cached at `~/.cache/whisper/base.pt` from Sprint 32 install). The script
just **verifies** the file exists and prompts a download if not. No HF
download dance, no LFS magic.

The script:
1. Verifies `uv sync --extra voice` is in effect (checks for
   `openai-whisper` import).
2. Checks `~/.cache/whisper/base.pt` exists.
3. If missing, prints a one-liner to download:
   `uv run --with openai-whisper python -c "import whisper; whisper.load_model('base')"`
   (openai-whisper auto-downloads to the cache dir on first load).
4. Verifies the file is loadable + reports its size.
5. Prints the `voice.asr.backend` config value the user should set
   (already the default: `whisper_local`).

### 3. `scripts/run_held_out_eval.py` — CLI runner

The interesting one. Mirrors `tests/voice/test_held_out_eval.py` but in a
standalone CLI:

1. Locates `~/.gundam-halo/recordings/held-out-<date>.{wav,txt}` (latest by
   mtime — same logic as `test_held_out_eval.py:_latest_heldout_wav`).
2. Reads `voice.asr.backend` from `~/.gundam-halo/config.toml`. Defaults to
   `whisper_local` if unset.
3. Calls `asr_factory.create_asr(config)` → `WhisperLocalASR` (or
   `WhisperHFASR` for the personalised checkpoint swap path). Calls `warmup()`.
4. Reads the WAV → PCM bytes (16 kHz mono s16le) → `transcribe(pcm, 16000)`.
5. Computes WER (Levenshtein DP, same algo as `test_wer_helpers.py`).
6. Reads the threshold from `~/.gundam-halo/test-config.toml`
   `[held_out_eval].wer_threshold` (default 0.15 per Sprint 26 §4.3
   acceptance criterion 2; lower to 0.10 for the personalised model
   after training lands).
7. Prints pass/fail + WER delta + hypothesis vs reference.
8. Writes `tests/voice/held_out_results/<timestamp>.json` for trend tracking.

### 4. Tests

- `tests/scripts/test_record_held_out_helpers.py` — pure-Python helpers extracted
  from the bash script (date formatting, transcript validation, file naming).
  Bash script itself is tested manually (no easy CI for interactive shell scripts).
- `tests/scripts/test_setup_held_out_model_helpers.py` — wraps the cached-model
  check in a testable Python helper (`check_cached_whisper_model()`). Bash script
  calls this helper + exits 0/1 based on the result.
- `tests/scripts/test_run_held_out_eval.py` — full eval loop with mocked
  `asr_factory.create_asr` (mirrors `test_held_out_eval.py` pattern).

## Test changes

- New: `tests/scripts/test_record_held_out_helpers.py` (3-4 tests)
- New: `tests/scripts/test_setup_held_out_model_helpers.py` (3-4 tests)
- New: `tests/scripts/test_run_held_out_eval.py` (3-4 tests, mocked)
- Existing: `tests/voice/test_held_out_eval.py` (no changes — still skips
  without WAV; the new CLI is a parallel path that runs real inference)

## Acceptance criterion

- User runs `bash scripts/setup-held-out-model.sh` → `~/.gundam-halo/models/whisper-yue-base/`
  exists with `config.json` + `pytorch_model.bin`.
- User runs `bash scripts/record-held-out.sh` → records 30 s + types transcript.
- User runs `uv run python scripts/run-held-out-eval.py` → prints
  `WER = X.XX% < 10.00% threshold — PASS` (or FAIL with debug info).
- M9-E acceptance criterion 6 status updated to ✅ once a personalised
  checkpoint has been trained and re-evaluated with WER < 10%.

## Out of scope (deferred to user-driven follow-ups)

- The live 30-min self-record corpus (requires user recording via Tauri app).
- The LoRA fine-tune run (~1-2 hr on Apple Silicon via `finetune_whisper_yue.py`).
- The personalised-checkpoint re-eval (runs the same script with `model_path` pointing
  at the trained checkpoint, WER threshold lowered from 0.15 → 0.10).
- Updating M9-E acceptance criterion 6 to ✅ (only after the live run completes).

## Files to create

- `backend/scripts/record-held-out.sh` (NEW, ~100 LoC bash)
- `backend/scripts/setup-held-out-model.sh` (NEW, ~60 LoC bash)
- `backend/scripts/run_held_out_eval.py` (NEW, ~200 LoC Python)
- `backend/app/voice/held_out_eval.py` (NEW, ~80 LoC Python — helpers shared between
  the CLI and the bash recorder; testable in isolation)
- `backend/tests/scripts/test_record_held_out_helpers.py` (NEW, ~80 LoC, 3-4 tests)
- `backend/tests/scripts/test_setup_held_out_model_helpers.py` (NEW, ~80 LoC, 3-4 tests)
- `backend/tests/scripts/test_run_held_out_eval.py` (NEW, ~150 LoC, 3-4 tests)

Total new: ~750 LoC across 7 files. Sprint 38 commit count: 1.

## Version bump

`__version__` 0.1.10 → **0.1.11** per Mavis memory rule (significant feature:
held-out eval plumbing ships). Frontend versions unchanged (0.1.7 from Sprint 33b).

# Feature Spec — Sprint 19d: M9-E Layer 2 prep (Cantonese Whisper fine-tune)

> **Status:** DRAFT — user signed off as part of Sprint 19
> scope A-all-four. Implementation follows in this session.
> **Scope:** 1 hour. Prep-only — we ship the smoke test
> + spec documentation, but **do not run the actual 3h
> training session in this sprint**. The actual training
> run is a follow-up session that needs:
>   - `uv sync --extra train --extra voice` (already
>     documented in `pyproject.toml`)
>   - 16 GB+ Apple Silicon Mac with MPS
>   - 30 min Common Voice yue download + 2.5h LoRA
>     training + 5 min WER eval
> **Out of scope (deferred to 20+):** self-recorded
> corpus, mlx-whisper inference, v0.1.4 `WhisperHFASR`
> backend swap (the v0.1.3 `WhisperLocalASR` cannot
> load HF-format directories yet — see M9-E §"v0.1.4
> follow-ups").

---

## 0. Why this sprint exists

Sprint 17b's M9-C live run revealed the v0.1.0
Cantonese ASR quality floor: Whisper base treats
Cantonese as English and produces garbled transcripts.
M9-E Layer 1 (model_size base → medium) was tested
and **rejected in v0.1.3** (3x per-turn ASR latency,
marginal Cantonese improvement, +1 GB permanent).
M9-E Layer 2 (Cantonese fine-tune on Common Voice
yue) is the real path forward.

v0.1.3 shipped the *infrastructure* for Layer 2:
the `train` extra in `pyproject.toml`, the
`scripts/finetune_whisper_yue.py` recipe, the
`tests/voice/test_whisper_yue.py` acceptance gate
(skip-when-no-model), the `cantonese_eval.py`
scorer, and the M9-E ticket with the full design.
Sprint 19d ships the **prep-only** layer: a smoke
test that catches script rot without running the 3h
training, plus this spec that documents the actual
training run as a follow-up session.

## 1. Goals

1. **Smoke test for `finetune_whisper_yue.py`.** A
   test that imports the script via `importlib`,
   verifies `prepare_common_voice_yue` is still a
   `NotImplementedError` stub (per M9-E v0.1.3
   contract), verifies `main()` is the CLI entry
   point, and verifies the default output dir
   matches the path the `test_whisper_yue.py`
   acceptance gate looks for. Catches refactor
   rot without running the 3h training.
2. **Spec for the actual training run.** This
   document is the runbook for the follow-up
   session: install command, CLI invocation, WER
   acceptance criterion, follow-up commit pattern.
3. **No regressions.** Existing 51 backend tests +
   1 skip (the Starlette WS rate-limit test) all
   still pass. No changes to the finetune script's
   behaviour — only a test that watches it.

## 2. Out of scope (deferred)

- **Actual training run** — the 3h wall clock
  session. This is a separate, dedicated session
  with the user present (so we can react to WER
  spikes, training crashes, or OOM errors in real
  time). Setup instructions in §6.
- **v0.1.4 `WhisperHFASR` backend** — the
  `WhisperLocalASR` (openai-whisper) cannot load
  HF-format model directories. The trained
  weights from this sprint are forward-compatible
  with the v0.1.4 swap.
- **Self-recorded corpus** — the M9-E ticket
  describes a 30-min user-recording path for
  personalisation. Defer to a future Layer 2 v2
  (after the public Common Voice yue baseline
  works end-to-end).
- **mlx-whisper** — the Apple Silicon native
  inference path. Faster than transformers on MPS
  but the fine-tune story is less mature. Defer
  until the HF pipeline is validated.
- **Code-switch tolerance** — mixed Cantonese +
  English + Mandarin in the same turn. Defer to
  M9-E Layer 3 or a future M9 ticket.

## 3. User-facing behavior

This sprint is **invisible to the user** in the
happy path. The cockpit still uses
`WhisperLocalASR(base)`. The fine-tuned model
will swap in via the v0.1.4 backend replacement.

## 4. Architecture

### 4.1 What v0.1.3 already shipped (Sprint 19d is a
verification layer on top)

| File | Purpose |
|---|---|
| `pyproject.toml` | `train` extra: `transformers`, `peft`, `datasets`, `accelerate`, `jiwer`, `soundfile` |
| `app/core/config.py` | `VoiceASRConfig.model_path: str = ""` field |
| `app/voice/asr/whisper_local.py` | `model_path` wired through (warning emitted — HF loading comes in v0.1.4) |
| `app/voice/asr/asr_factory.py` | `model_path` threaded through |
| `scripts/finetune_whisper_yue.py` | Full recipe (499 LoC): CLI, `prepare_common_voice_yue` (stub), `build_model_and_processor`, `build_trainer`, `evaluate_wer`, `main` |
| `tests/voice/test_whisper_yue.py` | Acceptance gate (skips until model exists) |
| `scripts/cantonese_eval.py` | LLM-judge-free 25-case eval set (regex/heuristic scoring) |
| `tests/cantonese/eval_set.yaml` | The 25 eval cases |

### 4.2 What Sprint 19d adds

- `tests/voice/test_finetune_script.py` — 4 smoke
  tests:
  - `test_finetune_script_is_importable` — the
    script module loads without syntax errors;
    `prepare_common_voice_yue` and `main` are
    present.
  - `test_finetune_script_help_exits_zero` —
    subprocess `--help` exits 0 with the documented
    args (`--output_dir`, `--lora_r`,
    `--dataset_version`).
  - `test_prepare_common_voice_yue_is_stub` —
    pins the v0.1.3 contract: `prepare_common_voice_yue`
    raises `NotImplementedError` with an error
    message that mentions M9-E / v0.1.3. Skipped
    when `datasets` (the `train` extra) isn't
    installed, because the function imports
    `from datasets import ...` at the top.
  - `test_finetune_script_default_output_dir_matches_config`
    — tripwire: the test fixture's
    `FINE_TUNED_MODEL_DIR` (`~/.gundam-halo/models/
    whisper-yue-base/`) matches the spec's expected
    path. If you move the path, move both.

### 4.3 Why a smoke test instead of running the
training

- The 3h wall clock doesn't fit in any 1-day
  sprint; it needs a dedicated session with the
  user present to react to OOM or WER spikes.
- A smoke test catches the common failure mode
  (script rot — someone refactors and introduces
  a syntax error) at unit-test time, which is
  cheap.
- The actual training run is documented in §6
  below as a follow-up session.

## 5. File-by-file change set

| Path | Change | LoC est. |
|---|---|---|
| `backend/tests/voice/test_finetune_script.py` | NEW. 4 smoke tests | +170 / 0 |
| `docs/FEATURE-SPEC-SPRINT19d.md` | NEW. This file. | +200 / 0 |
| `docs/CHANGELOG.md` | Sprint 19d entry under [Unreleased] | +30 / 0 |

**Total**: ~400 LoC. ~1 hour wall clock.

## 6. Runbook for the actual training session
(follow-up, not this sprint)

```bash
cd ~/workspace/working/gundam-halo/backend
# 1. Install the training stack on top of the existing venv.
uv sync --extra train --extra voice

# 2. (Optional) Verify the env.
.venv/bin/python -c "import transformers, peft, datasets, jiwer; print('ok')"

# 3. Run the training. This will:
#    - Download Common Voice 13.0 yue via Hugging Face Hub (~30min)
#    - Materialise train/val/test splits to ~/.gundam-halo/cache/cv-yue/
#    - LoRA fine-tune Whisper base for 3 epochs (~2.5h on M-series)
#    - Merge LoRA into the base weights and save to
#      ~/.gundam-halo/models/whisper-yue-base/  (HF format)
#    - Run WER on the held-out test split, exit 2 if WER > 20%
.venv/bin/python scripts/finetune_whisper_yue.py

# 4. Run the acceptance tests (now that the model exists, they
#    don't skip).
.venv/bin/python -m pytest tests/voice/test_whisper_yue.py -v

# 5. Eval the model on the 25-case Cantonese eval set:
.venv/bin/python scripts/cantonese_eval.py
```

### 6.1 WER acceptance criteria

| Model | CV yue WER target |
|---|---|
| Whisper base (no fine-tune) | baseline (~70-80% per M9-E) |
| Whisper base + LoRA fine-tune on 50h yue | < 20% (per M9-E spec) |

If WER is > 20%, the script exits with code 2. The
user inspects the training log, the eval output,
and decides whether to:
  - bump `--num_train_epochs` from 3 to 5
  - bump `--lora_r` from 32 to 64
  - expand the training set
  - roll back and defer the sprint

### 6.2 Post-training follow-up (v0.1.4)

1. Replace `WhisperLocalASR` (openai-whisper) with
   `WhisperHFASR` (transformers pipeline) — same
   interface, swap the inference path.
2. Update `~/.gundam-halo/config.toml`:
   ```toml
   [voice.asr]
   backend = "whisper_hf"  # or whatever the v0.1.4 backend is called
   model_path = "~/.gundam-halo/models/whisper-yue-base/"
   ```
3. Re-run M9-C live. **Delete the augmented
   system note in `scripts/m9c_voice_tools.py:187-192`**
   — verify the agent still completes the task
   without the workaround.

## 7. Acceptance tests

1. **Script is importable** — `test_finetune_script_is_importable`
   passes. Confirms the script has no syntax
   errors and the canonical entry points exist.
2. **CLI parser works** — `test_finetune_script_help_exits_zero`
   passes. The `--output_dir`, `--lora_r`,
   `--dataset_version` args are documented.
3. **Stub contract pinned** — `test_prepare_common_voice_yue_is_stub`
   skips when the `train` extra isn't installed,
   otherwise asserts the function raises
   `NotImplementedError` with an M9-E / v0.1.3
   error message.
4. **Path consistency** — `test_finetune_script_default_output_dir_matches_config`
   passes. The fixture's `FINE_TUNED_MODEL_DIR`
   and the spec's expected path are equal.
5. **No regression** — all 51 existing backend
   voice tests + 1 skip pass. All 63 frontend
   vitest tests pass. `tsc --noEmit` returns 0
   errors. `pnpm lint` returns 0 errors.

## 8. Sign-off

- [x] **Track 19d scope agreed** — prep-only: smoke
      test + spec, no actual training run.
- [x] **Out-of-scope items confirmed** — actual
      training run, v0.1.4 backend swap, self-record
      corpus, mlx-whisper all deferred.

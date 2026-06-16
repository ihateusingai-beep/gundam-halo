# Feature Spec — Sprint 20: M9-E Layer 2 v0.1.4 (Cantonese model land)

> **Status:** DRAFT — user signed off as Sprint 20
> scope. **This is a SPEC-ONLY sprint.** No code is
> written. The actual implementation lands in Sprint
> 21+ once the user runs the M9-E Layer 2 training
> session in a dedicated 3h+ wall-clock session.
> **Scope:** 30 min. Spec + runbook + CHANGELOG entry
> for v0.1.4. Documents the 4-step rollout that
> follows Sprint 19d's training runbook.
> **Out of scope (deferred to 21+):** actual
> `WhisperHFASR` impl, `prepare_common_voice_yue`
> fill-in, augmented system note removal, supervisor
> (systemd / launchd).

---

## 0. Why this sprint exists

Sprint 19d shipped the prep layer for M9-E Layer 2
(smoke test for the training script) and the
background monitor (Sprint 19d addendum). The
training itself — the 3h+ Common Voice yue +
LoRA fine-tune — still hasn't run because it
needs the user present in a dedicated session
(spec 19d §6).

Sprint 20 is the **rollout plan** for what happens
*after* the model lands. Four coordinated changes
unlock production-grade Cantonese ASR:

1. **`WhisperHFASR` backend** — replace the
   `whisper_local` (openai-whisper) backend with a
   Hugging Face `transformers` pipeline so the
   fine-tuned HF-format checkpoint can actually
   load. v0.1.3 already accepts `model_path` but
   emits a warning saying "fully wired in v0.1.4".
2. **`prepare_common_voice_yue` impl** — fill in
   the 180-LOC `NotImplementedError` stub so the
   training script (`finetune_whisper_yue.py`)
   actually downloads + splits Common Voice yue
   instead of crashing.
3. **Augmented system note removal** — the
   workaround in `scripts/m9c_voice_tools.py:187-192`
   (the "augment spoken text with [system note] for
   the agent") was added in M9-D because Whisper
   base garbled Cantonese. With the fine-tuned
   model the workaround is redundant. Removing it
   is the M9-E Layer 2 acceptance test in disguise:
   if the agent still completes the M9-C fixture
   without the workaround, the fine-tune worked.
4. **Supervisor (deferred to 21+)** — `launchd`
   plist on macOS so the backend survives crashes
   and starts at boot. Out of scope for v0.1.4
   proper; the user has been launching the backend
   themselves.

This spec is a **handoff document**: it describes
the 4 changes, the dependency graph, the test
plan, and the WER acceptance criteria. The actual
implementation lands in Sprint 21+ when the user
decides to commit the time.

## 1. Goals

1. **Document the v0.1.4 rollout plan** so the
   next sprint can land it without re-deriving
   the design.
2. **Capture the acceptance test in code form**:
   the M9-C fixture must complete without the
   augmented system note. This is the single
   observable proof that the fine-tune worked.
3. **Pin the WER acceptance criterion** at < 20%
   on the held-out Common Voice yue test set
   (per M9-E §"Layer 2 acceptance").
4. **No code is written in this sprint.** Sprint
   20 is spec-only. The CHANGELOG entry is
   "Planned for v0.1.4".

## 2. Out of scope (deferred)

- **Actual `WhisperHFASR` implementation** —
  Sprint 21+ (1-1.5 day backend).
- **Fill in `prepare_common_voice_yue` impl** —
  Sprint 21+ (0.5-1 day).
- **Augmented system note removal** — Sprint 22+
  (1 hour, conditional on Layer 2 actually
  working).
- **launchd / systemd supervisor** — Sprint 22+
  (deferred per Sprint 19b §2).
- **Self-record corpus + Layer 2 v2** — per
  M9-E §"v0.1.3 Layer 2 plan".
- **mlx-whisper inference** — per M9-E §"Fine-tune
  tooling".
- **iOS / iPadOS** — per M9-E §"Out of scope".

## 3. User-facing behavior

This sprint is **invisible to the user**. The
cockpit still uses `WhisperLocalASR(base)`. v0.1.4
ships the swap to `WhisperHFASR` and the user just
edits `~/.gundam-halo/config.toml` to point at the
new model directory. The M9-C live re-run then
verifies the fine-tune worked.

## 4. Architecture

### 4.1 The 4-step rollout

**Step 1 — fill in `prepare_common_voice_yue`**
(`backend/scripts/finetune_whisper_yue.py:193-246`,
180 LoC). Currently raises `NotImplementedError`
with a TODO. The implementation must:
- Stream `mozilla-foundation/common_voice_<ver>_0`
  `yue` split via `datasets.load_dataset(..., streaming=True)`
  (per the existing `prepare_common_voice_yue`
  function body)
- Split by `client_id` at the speaker level
  (Common Voice's standard split — never split one
  speaker across train and val, that leaks the WER)
- Materialise to local parquet
  (`~/.gundam-halo/cache/cv-yue/{train,validation,test}`)
  for resumable download
- Track audio length to honour
  `max_train_hours`; cap the training set at
  ~45000 samples for 50h at 4s/utterance
- Use HF's `Audio(sampling_rate=16000)` to resample
  to 16kHz on the fly

The output of Step 1: a populated
`~/.gundam-halo/cache/cv-yue/` directory that the
training script can `load_from_disk()` directly.

**Step 2 — add `whisper_hf` backend to the factory**
(`backend/app/voice/asr/asr_factory.py`).

```python
if backend == "whisper_hf":
    # Lazy import: the HF pipeline pulls in
    # `transformers` + `torch` (CPU or MPS). The
    # `voice-hf` extra declares these deps. whisper_local
    # users don't pay for them.
    from app.voice.asr.whisper_hf import WhisperHFASR

    return WhisperHFASR(
        model_path=config.model_path,
        language=config.language,
        device=config.device,
        compute_type=config.compute_type,
    )
```

The new `WhisperHFASR` class implements
`ASRInterface` (the same interface `WhisperLocalASR`
and `YuesubASR` implement). It uses
`transformers.pipeline("automatic-speech-recognition",
model=str(model_path))` to load the fine-tuned
checkpoint, then transcribes PCM bytes by:
- Wrapping the int16 PCM in a `datasets.Audio` array
  (HF expects numpy float32; we convert)
- Calling the pipeline with `generate_kwargs={
  "language": "yue", "task": "transcribe"}` (the
  Cantonese hint we want baked in at inference time)
- Returning the same `ASRResult` dataclass the
  other ASR engines return

**Step 3 — wire `VoiceASRConfig.model_path` for
`whisper_hf` and remove the warning**. The
`WhisperLocalASR.warmup` warning at
`whisper_local.py:80-105` (the "is set but the
backend can't load HF directories yet" message)
goes away — `whisper_local` no longer claims to
support `model_path`. The `whisper_hf` backend
*requires* `model_path` (no fallback to a default
HF model — the user must have the fine-tuned
checkpoint on disk).

**Step 4 — delete the augmented system note** in
`scripts/m9c_voice_tools.py:180-195`. This is the
**observable acceptance test** for the fine-tune:

```python
# Before v0.1.4:
augmented = (
    f"{text}\n\n"
    "[system note for the agent: the user is asking about the "
    f"file {README_PATH!r}. Use the file_read tool to read it, "
    "then quote its first line. Reply in Cantonese.]"
)
result = await agent.run(augmented, context=ctx)

# After v0.1.4 (verify the agent still completes the task
# without the workaround):
result = await agent.run(text, context=ctx)
```

If the agent no longer completes the M9-C
fixture after the swap, the fine-tune didn't
work and the user has a choice: revert the
augmented-note deletion and investigate, or
re-train with more data / more epochs.

### 4.2 WER acceptance criterion

Per M9-E §"Layer 2 acceptance":

- [ ] `scripts/finetune_whisper_yue.py` runs
      end-to-end on a 30-min fixture corpus and
      produces a checkpoint under
      `~/.gundam-halo/models/whisper-yue-base/`.
- [ ] `tests/voice/test_whisper_yue.py` loads the
      fine-tuned model and asserts WER < 20% on
      a held-out Cantonese fixture.
- [ ] M9-C live re-run: `ASR text` matches the
      user's spoken Cantonese closely enough that
      the agent's **augmented system note is no
      longer needed** (delete lines 187–192 of
      `m9c_voice_tools.py` and verify the agent
      still completes the task).

The 20% threshold is the "production usable" line
in M9-E §"Expected outcomes": a WER < 20% on a
single user's voice is good enough for the LLM
downstream to route requests correctly without the
augmentation workaround. If WER is > 20%, the
script exits with code 2; the user inspects the
training log + eval output and decides whether
to:
  - bump `--num_train_epochs` from 3 to 5
  - bump `--lora_r` from 32 to 64
  - expand the training set
  - roll back and defer the sprint

### 4.3 Config.toml update

```toml
[voice.asr]
backend = "whisper_hf"
model_path = "~/.gundam-halo/models/whisper-yue-base/"
# language defaults to "yue" in WhisperHFASR;
# device defaults to "auto" (MPS on Apple Silicon).
# No model_size (HF-format checkpoints don't use
# openai-whisper size names like "base" / "small").
```

`whisper_local` remains available as a backward-
compat alias — users who don't want to re-train
can keep using openai-whisper base / medium with
the existing `model_size` field. v0.1.4 adds the
choice; it doesn't force the swap.

### 4.4 Dependency graph

```
+----------------------------------+
| Step 1: prepare_common_voice_yue |  ← Sprint 21, 0.5-1 day
| (180 LoC impl in finetune script) |
+----------------+-----------------+
                 v
+----------------------------------+
| Actual training run             |  ← User session, 3h+
| (Sprint 19d runbook + monitor)   |
+----------------+-----------------+
                 v
+----------------------------------+
| Step 2: WhisperHFASR backend     |  ← Sprint 22, 1-1.5 day
| (factory + impl + tests)         |
+----------------+-----------------+
                 v
+----------------------------------+
| Step 3: remove warning           |  ← Sprint 22, 30 min
| (WhisperLocalASR cleanup)        |
+----------------+-----------------+
                 v
+----------------------------------+
| Step 4: M9-C live re-run         |  ← User session, 5 min
| (acceptance test for the fine-tune)
+----------------+-----------------+
                 v
+----------------------------------+
| Step 5: delete augmented note   |  ← Sprint 22, 30 min
| (m9c_voice_tools.py:180-195)     |
+----------------+-----------------+
                 v
+----------------------------------+
| Optional: supervisor             |  ← Sprint 23+ (deferred)
+----------------------------------+
```

Steps 2 + 3 + 5 cluster naturally into one sprint
(1.5 days total). Step 1 is its own sprint (0.5-1
day) because the impl is a chunk of work, not a
quick win. Step 4 is a user-driven acceptance
test, not a sprint.

## 5. File-by-file change set (when Sprint 21+ lands)

| Path | Change | LoC est. |
|---|---|---|
| `backend/scripts/finetune_whisper_yue.py` | Fill in `prepare_common_voice_yue` impl (180 LoC) | +180 / -10 |
| `backend/app/voice/asr/whisper_hf.py` | NEW. `WhisperHFASR` class implementing `ASRInterface` | +200 / 0 |
| `backend/app/voice/asr/asr_factory.py` | Add `whisper_hf` branch | +12 / 0 |
| `backend/app/voice/asr/whisper_local.py` | Remove the `model_path` warning (now lives in `whisper_hf` only) | 0 / -25 |
| `backend/tests/voice/test_whisper_hf.py` | NEW. 8-10 tests: model load, transcribe happy path, WER against fixture, model_path error, language hint passthrough | +250 / 0 |
| `backend/tests/voice/test_finetune_script.py` | The `test_prepare_common_voice_yue_is_stub` test now FAILs (the function is no longer a stub). Replace with a real test that the impl runs end-to-end against a 5-sample fixture. | +120 / -30 |
| `backend/scripts/m9c_voice_tools.py` | Delete lines 180-195 (augmented note). If M9-C live re-run fails, revert via git. | 0 / -16 |
| `~/.gundam-halo/config.toml` | Update `[voice.asr]` block to `backend = "whisper_hf"` + `model_path = "~/.gundam-halo/models/whisper-yue-base/"` (one-time, manual) | +3 / -1 |
| `docs/CHANGELOG.md` | v0.1.4 release entry: model swap, M9-C acceptance, augmented-note removal | +60 / 0 |
| `docs/tickets/M9-E.md` | Mark Layer 2 acceptance boxes ✓ (or ✗ if WER > 20%) | +5 / -5 |
| `pyproject.toml` | Add `voice-hf` optional extra: `transformers`, `torch` (CPU + MPS wheels), `accelerate`, `soundfile` | +5 / 0 |

**Total**: ~830 LoC. ~2-3 days wall clock over
2-3 sprints (Sprint 21 + 22).

## 6. Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **WER > 20% on first run** | Medium | High | The training script exits 2 on WER > 20%. The user re-trains with more epochs / larger LoRA / more data. Worst case: roll back to `whisper_local(base)` and defer the swap. |
| **`WhisperHFASR` cold-start is slow** | Medium | Low | HF pipeline cold-start on M-series is ~3-5s (model load + cache prime). The voice WS already takes ~1-3s for the silero VAD + FunASR yuesub path, so adding 3-5s to the first WS connect is acceptable. |
| **MPS has a 4GB residency cap on M-series** | Medium | Medium | The `transformers` pipeline uses float32 by default (~300MB for whisper-base). With FP16 / BF16, ~150MB. Both fit. We default to FP32 for parity with the training script; user can override via `compute_type = "float16"`. |
| **Augmented-note deletion breaks M9-C** | Low | High | The git revert path is one command. The user keeps the augmented note in git history; if the agent fails the M9-C re-run, revert. |
| **Common Voice yue download auth wall** | Low | Medium | Mozilla dropped the auth wall for v11+ public datasets. If a future version re-introduces auth, the user runs `huggingface-cli login` first. We don't bake the auth into the script. |
| **M9-E fine-tune is overfit to Common Voice yue speakers** | Medium | Medium | Common Voice yue is read speech (people reading prompted text), not conversational. Production Cantonese has more casual speech patterns. Mitigation: the user can record their own 30-min corpus (M9-E §"Self-recorded") and mix with Common Voice for Layer 2 v2. |
| **M9-C fixture is no longer the right acceptance test** | Low | Low | M9-C was designed for M9-D (Cantonese on whisper-base). If the fine-tune works, the M9-C live re-run passes. If the fine-tune overfits, M9-C still passes (the fixture is in the training distribution). We need a held-out test (user-recorded, ~30s) to verify personalisation. |

## 7. Acceptance tests

1. **Step 1 — `prepare_common_voice_yue` impl** —
   `pytest tests/voice/test_finetune_script.py -v`
   replaces the `test_prepare_common_voice_yue_is_stub`
   skip-or-pass test with a real end-to-end
   test against a 5-sample fixture.

2. **Step 2 — `WhisperHFASR` smoke** —
   `pytest tests/voice/test_whisper_hf.py -v` —
   8-10 tests covering model load, transcribe
   happy path, WER against a fixture, model_path
   error, language hint passthrough.

3. **Step 3 — no warning on `whisper_local`** —
   `pytest tests/voice/test_whisper_local.py -v` —
   the existing warning-emission tests are
   removed (the warning no longer exists); new
   tests assert that `whisper_local(model_path=...)`
   raises a clear `ValueError` ("use the
   `whisper_hf` backend for fine-tuned models").

4. **Step 4 — M9-C live re-run** — manual smoke,
   run `m9c_dryrun_infra.py` (or the live
   equivalent), assert the agent still completes
   the file_read task on `README.md` and replies
   in Cantonese.

5. **Step 5 — augmented note deletion** —
   `git diff scripts/m9c_voice_tools.py` should
   show ~16 lines removed. Manual smoke:
   re-run the M9-C live fixture; agent must
   still complete.

6. **No regression** — all 58 backend tests + 1
   skip from Sprint 19d still pass. All 63
   frontend vitest tests still pass.

## 8. Sign-off

- [x] **Track 20 scope agreed** — spec-only, no
      code is written in this sprint. The
      4-step rollout plan is captured for Sprint
      21+ implementation.
- [x] **Out-of-scope items confirmed** — actual
      `WhisperHFASR` impl, `prepare_common_voice_yue`
      fill-in, augmented system note removal,
      launchd supervisor all deferred.

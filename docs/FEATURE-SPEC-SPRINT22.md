# Feature Spec — Sprint 22: v0.1.4 land (WhisperHF + augmented-note removal + banner expiry)

> **Status:** DRAFT — proposed Sprint 22 scope.
> **This is a SPEC-ONLY sprint.** No code is written.
> Implementation lands in Sprint 23+ once the user
> runs the M9-E Layer 2 training session.
> **Scope:** 1-1.5 days wall clock when implemented
> (matches Sprint 20 §"Steps 2 + 3 + 5 cluster").
> **Predecessor:** Sprint 21 (commit `3353106`)
> shipped `prepare_common_voice_yue` impl + 5
> helper unit tests, completing Sprint 20 Step 1.
> **Depends on:** user-present training run
> (Sprint 19d §6 runbook, monitored by
> `finetune_whisper_yue_monitor.py`) producing
> a HF-format checkpoint under
> `~/.gundam-halo/models/whisper-yue-base/`.
> **Out of scope (deferred to 23+):** launchd /
> systemd supervisor; mlx-whisper inference;
> self-record corpus + Layer 2 v2.

---

## 0. Why this sprint exists

Sprint 20 (commit `ffc2624`) shipped the 4-step
rollout plan for v0.1.4. Sprint 21 (commit
`3353106`) shipped Step 1 (`prepare_common_voice_yue`
impl, 286 LoC + 5 helper unit tests). Step 4
(manual M9-C live re-run) is a user-driven
acceptance test, not a sprint. Steps 2 + 3 + 5
cluster into one sprint:

1. **Step 2 — `WhisperHFASR` backend.** v0.1.3
   already accepts `model_path` but `WhisperLocalASR`
   can't load HF-format directories. The
   `whisper_local.py:80-99` warmup emits a "Full
   support lands in v0.1.4" warning. v0.1.4
   ships the actual HF pipeline wrapper so the
   fine-tuned checkpoint can be loaded.

2. **Step 3 — warning removal.** Once `WhisperHFASR`
   exists, `whisper_local(model_path=...)` is no
   longer a valid combination. The v0.1.3 warning
   becomes a `ValueError` ("use the `whisper_hf`
   backend for fine-tuned models").

3. **Step 5 — augmented system note deletion.** The
   workaround in `m9c_voice_tools.py:187-192` (the
   "[system note for the agent: ...]" augmentation
   added in M9-D because Whisper base garbled
   Cantonese proper-noun tokens) becomes
   redundant once the fine-tune is good. Its
   deletion is the **observable acceptance test**
   for the fine-tune: if the agent still completes
   the M9-C fixture without the workaround, the
   fine-tune worked.

In addition to Sprint 20's three Steps, this spec
adds a fourth track:

4. **Track 4 — Sprint 17a upgrade-banner expiry.**
   Sprint 17a flipped `strict_wake_phrase` default
   False → True with a 7-day upgrade banner (frontend
   `localStorage` TTL) and a backend one-time
   `INFO` log line (`config.py:526-552`). The
   user has had >7 days to see the banner. v0.1.4
   ships the dead-code removal: the banner JSX,
   the `shouldShowUpgradeBanner` /
   `dismissUpgradeBanner` helpers, the
   `UPGRADE_BANNER_KEY` / `UPGRADE_BANNER_TTL_MS`
   constants, and the backend
   `_STRICT_WAKE_UPGRADE_LOGGED` flag + first-launch
   log block all go away. The `strict_wake_phrase`
   field itself stays — it's the new default, and
   users who want permissive mode can still set
   `strict_wake_phrase = false`.

This spec is a **handoff document**: it describes
the 4 tracks, the dependency graph, the test
plan, the WER acceptance criteria, and the
augmented-note deletion rollback path.

## 1. Goals

1. **Document the v0.1.4 landing plan** so Sprint
   23+ can implement it without re-deriving
   the design.
2. **Capture the acceptance test in code form**:
   the M9-C fixture must complete without the
   augmented system note. This is the single
   observable proof that the fine-tune worked.
3. **Pin the WER acceptance criterion** at < 20%
   on the held-out Common Voice yue test set
   (per M9-E §"Layer 2 acceptance").
4. **Remove dead upgrade code** from Sprint 17a
   (the 7-day banner was a temporary nudge, not
   a permanent feature).
5. **No code is written in this sprint.** Sprint
   22 is spec-only. The CHANGELOG entry is
   "Planned for v0.1.4".

## 2. Out of scope (deferred)

- **Actual `WhisperHFASR` implementation** —
  Sprint 23+ (1 day, per Sprint 20 §5
  file-by-file table: 200 LoC `whisper_hf.py`
  + 12 LoC factory branch + 25 LoC
  `whisper_local.py` cleanup + 250 LoC tests).
- **Augmented system note deletion** — Sprint 23+
  (1 hour, conditional on Step 2's user smoke
  test passing).
- **Sprint 17a upgrade-banner expiry removal** —
  Sprint 23+ (30 min, no conditional — the
  banner's 7-day TTL has already expired for
  all users; the code is just dead now).
- **launchd / systemd supervisor** — Sprint 23+
  per Sprint 19b §2.
- **Self-record corpus + Layer 2 v2** — per
  M9-E §"v0.1.3 Layer 2 plan".
- **mlx-whisper inference** — per M9-E §"Fine-tune
  tooling".
- **iOS / iPadOS** — per M9-E §"Out of scope".

## 3. User-facing behavior

This sprint is **invisible to the user**. The
cockpit still uses `WhisperLocalASR(base)` (or
`YuesubASR` if the user picked that). v0.1.4
ships the swap to `WhisperHFASR` and the user
just edits `~/.gundam-halo/config.toml` to
point at the new model directory. The M9-C
live re-run then verifies the fine-tune worked.

**Track 4 is also invisible**: the 7-day banner
has already auto-expired for any user who didn't
explicitly dismiss it. The code removal is
purely a dead-code cleanup; the user sees no
behavior change.

The one observable difference: the
`WhisperLocalASR` "model_path" warmup warning
(seen in the backend log on every startup if
`voice.asr.model_path` is set) goes away. If
the user *does* set `model_path` on a
`whisper_local` backend, they get a `ValueError`
at startup with a clear pointer to use
`whisper_hf` instead.

## 4. Architecture

### 4.1 The 4 tracks

#### Track 1 — `WhisperHFASR` backend

**New file**: `backend/app/voice/asr/whisper_hf.py`
(~200 LoC). Implements `ASRInterface`. The class
follows the same lazy-import + `ASRError` wrap
pattern as `YuesubASR` (see
`backend/app/voice/asr/yuesub.py:155-204`):

```python
def _import_transformers():
    try:
        from transformers import pipeline  # type: ignore
    except ImportError as e:
        raise ASRError(
            "transformers is required for WhisperHFASR. "
            "Install with: uv sync --extra voice-hf"
        ) from e
    return pipeline


class WhisperHFASR(ASRInterface):
    def __init__(
        self,
        model_path: str,
        language: str = "yue",
        device: str = "auto",
        compute_type: str = "auto",
    ):
        # Defaults aligned with v0.1.3 VoiceASRConfig.
        # model_path is REQUIRED (not optional like
        # WhisperLocalASR's model_path) — the
        # factory raises ValueError if empty.
        ...
        self._model_path = os.path.expanduser(model_path)
        self._language = language
        self._device = _resolve_device(device)
        self._compute_type = compute_type
        self._pipeline = None

    async def warmup(self) -> None:
        if self._pipeline is not None:
            return
        if not os.path.isdir(self._model_path):
            raise ASRError(
                f"WhisperHFASR.model_path does not exist: "
                f"{self._model_path!r}. The fine-tuned checkpoint "
                f"must be downloaded before switching to "
                f"backend='whisper_hf'."
            )
        pipeline = await asyncio.to_thread(
            self._build_pipeline
        )
        self._pipeline = pipeline

    def _build_pipeline(self):
        pipeline = _import_transformers()
        torch_dtype = _resolve_torch_dtype(self._compute_type)
        return pipeline(
            "automatic-speech-recognition",
            model=self._model_path,
            torch_dtype=torch_dtype,
            device=self._device,
        )

    async def transcribe(
        self, audio: bytes, sample_rate: int = 16000
    ) -> str:
        if self._pipeline is None:
            await self.warmup()
        # Convert int16 PCM bytes → numpy float32 [-1, 1]
        # (transformers expects float32; openai-whisper
        # did this internally).
        np_arr = _pcm_bytes_to_float32(audio)
        result = await asyncio.to_thread(
            self._pipeline,
            np_arr,
            generate_kwargs={
                "language": (
                    "cantonese" if self._language == "yue"
                    else self._language
                ),
                "task": "transcribe",
            },
        )
        return result["text"].strip()
```

**Key design choices**:

- **`language="cantonese"` mapping** — the HF
  `generate_kwargs` schema uses ISO 639-1 names,
  not Whisper's `yue` shorthand. The wrapper
  maps `yue` → `cantonese` so the existing
  `VoiceASRConfig.language` field (which uses
  `yue` to match Whisper / SenseVoice
  conventions) keeps working.
- **`asyncio.to_thread` for HF pipeline calls** —
  the HF pipeline is sync (not async), and the
  pipeline call can take 100-500ms on CPU. The
  same pattern is already in
  `app/voice/corrector/corrector.py` (the BERT
  corrector wraps sync calls in `to_thread`).
- **`torch_dtype` resolution** — `auto` defaults
  to float32 (parity with the training script).
  `float16` halves the residency at the cost of
  a small WER regression; `int8` is not
  supported by the HF pipeline (it's a
  transformers-level, not ONNX-level, quant).
- **`_resolve_device` helper** — maps
  `auto|cpu|cuda|mps` to `transformers.pipeline`'s
  `device` arg. `auto` checks `torch.backends.mps`
  first (Mac), then `cuda.is_available()`,
  falls back to `cpu`.

**Factory change** in
`backend/app/voice/asr/asr_factory.py` — add
the `whisper_hf` branch:

```python
if backend == "whisper_hf":
    # Lazy import: HF pipeline pulls in transformers +
    # torch (CPU + MPS wheels). The voice-hf extra
    # declares these deps. whisper_local / yuesub users
    # don't pay for them.
    from app.voice.asr.whisper_hf import WhisperHFASR

    if not config.model_path:
        raise ValueError(
            "voice.asr.model_path is required when "
            "backend='whisper_hf'. Set it in config.toml "
            "to the fine-tuned checkpoint directory, e.g.\n"
            'model_path = "~/.gundam-halo/models/whisper-yue-base/"'
        )

    return WhisperHFASR(
        model_path=config.model_path,
        language=config.language,
        device=config.device,
        compute_type=config.compute_type,
    )
```

The docstring on `create_asr`'s `ValueError`
(line 70) and the docstring on
`VoiceASRConfig.backend` (line 153) need to
be updated to list `whisper_hf` as a third
option.

#### Track 2 — `WhisperLocalASR` warning → `ValueError`

`backend/app/voice/asr/whisper_local.py:80-99`
emits a `logger.warning` if `model_path` is set
but the directory exists (HF format) or doesn't
exist at all. v0.1.4 ships a sharper contract:
`whisper_local` does **not** accept `model_path`
period. If the user passes it (and the
`asr_backend` is `whisper_local`), it's a
user-error — `ValueError` at warmup, not a
warning that the model silently falls back to
`model_size`.

**The change** (lines 80-99):

```python
# BEFORE (v0.1.3):
if self._model_path:
    expanded = os.path.expanduser(self._model_path)
    if os.path.isdir(expanded):
        logger.warning(
            f"voice.asr.model_path={...} is set "
            f"but WhisperLocalASR (openai-whisper backend) "
            f"cannot load HF-format directories. "
            f"Falling back to model_size={...}."
        )
    else:
        logger.warning(
            f"voice.asr.model_path={...} does not "
            f"exist on disk. Falling back to ..."
        )

# AFTER (v0.1.4):
if self._model_path:
    raise ValueError(
        f"WhisperLocalASR (openai-whisper backend) does "
        f"not support voice.asr.model_path. To load a "
        f"fine-tuned HF-format checkpoint, set "
        f"voice.asr.backend = 'whisper_hf' instead. "
        f"Got: voice.asr.model_path={self._model_path!r}."
    )
```

The `model_path` constructor parameter stays
(non-breaking: users who don't set it get the
old behavior). The contract shifts from
"silently ignored, with a warning" to
"hard error pointing at the right backend".

**Test change**:
`backend/tests/voice/test_whisper_local.py` —
there's no such file today. The 17 LoC test
file needs to be created with:

- `test_whisper_local_warmup_with_model_path_raises`
  — passing `model_path="/somewhere"` raises
  `ValueError` with a message that includes
  `whisper_hf`.
- `test_whisper_local_warmup_without_model_path_ok`
  — passing `model_path=""` (default) loads
  `whisper` as before.
- The 16 `test_voice_config_asr.py` cases that
  exercise `whisper_local` stay green
  (they don't pass `model_path`).

#### Track 3 — Augmented system note deletion

`backend/scripts/m9c_voice_tools.py:180-195`
contains the augmented-note workaround added
in M9-D. v0.1.4 ships its deletion, conditional
on the M9-C live re-run passing without it.

**The change** (lines 178-199):

```python
# BEFORE (v0.1.3):
async def native_react_voice_cb(sid: str, text: str) -> str | None:
    print(f"  [agent.run] in: {text!r}")
    # M9-C note: ASR may mangle the spoken query (whisper
    # base + Cantonese is lossy with proper-noun tokens).
    # To make M9-C's tool-calling path deterministic, we
    # augment the spoken text with an explicit instruction
    # + the absolute path of the README, so the LLM still
    # gets a clear "use file_read on /Users/kencheng/.../
    # README.md" directive even when ASR returned "Please
    # use the file read tool to read back and read me and
    # tell me the first line.".
    augmented = (
        f"{text}\n\n"
        "[system note for the agent: the user is asking "
        f"about the file {README_PATH!r}. Use the "
        "file_read tool to read it, then quote its "
        "first line. Reply in Cantonese.]"
    )
    ctx = AgentContext(...)
    result = await agent.run(augmented, context=ctx)

# AFTER (v0.1.4):
async def native_react_voice_cb(sid: str, text: str) -> str | None:
    print(f"  [agent.run] in: {text!r}")
    # M9-E Layer 2 acceptance: the fine-tuned model
    # handles Cantonese proper-noun tokens correctly,
    # so we no longer augment the spoken text with a
    # synthetic system note. The agent receives the
    # raw ASR transcript. If the agent fails the
    # M9-C fixture here, the fine-tune didn't work
    # and we need to revert this change.
    ctx = AgentContext(...)
    result = await agent.run(text, context=ctx)
```

**16 lines removed** (lines 179-195 inclusive;
the `augmented = (...)` block + the comment
header). The user comments out the deletion
in git history if the M9-C live re-run fails:

```bash
git revert <commit-hash-of-this-change>
```

The git revert is one command. The user keeps
the augmented note in git history; if the
agent fails the M9-C re-run, revert.

#### Track 4 — Sprint 17a upgrade-banner expiry

**Backend**:
`backend/app/core/config.py:33` (the
`_STRICT_WAKE_UPGRADE_LOGGED: bool = False`
module-level flag) and
`config.py:519-552` (the `if not _STRICT_WAKE_UPGRADE_LOGGED
...` block inside `load_config`).

The block emits a one-time INFO log line on
first launch (when the user has a `[voice]`
section but no `strict_wake_phrase` key). The
`_STRICT_WAKE_UPGRADE_LOGGED` module-level
flag prevents repeat emission within a process
(no expiry on disk — the flag resets on backend
restart).

Sprint 17a intended the banner to be visible
for 7 days, then the user would either accept
the new default or set the value explicitly.
Sprint 22 ships the dead-code removal: any
user who hasn't touched `strict_wake_phrase`
in their `config.toml` in >7 days is either
fine with the new default (no action needed)
or has uninstalled the app. Either way, the
log line is no longer useful.

**The change** (lines 33, 519-552):

```python
# BEFORE (v0.1.3):
_STRICT_WAKE_UPGRADE_LOGGED: bool = False

def load_config(home: Optional[Path] = None) -> Config:
    global _STRICT_WAKE_UPGRADE_LOGGED
    ...
    voice_section = toml_data.get("voice", {}) if toml_data else {}
    if (
        not _STRICT_WAKE_UPGRADE_LOGGED
        and isinstance(voice_section, dict)
        and "strict_wake_phrase" not in voice_section
    ):
        msg = "voice: strict_wake_phrase=True is now ..."
        logger.info(msg)
        print(f"[halo.config] {msg}")
        _STRICT_WAKE_UPGRADE_LOGGED = True

# AFTER (v0.1.4):
def load_config(home: Optional[Path] = None) -> Config:
    ...
    # (no more _STRICT_WAKE_UPGRADE_LOGGED flag,
    # no more first-launch INFO log line)
```

The `strict_wake_phrase` field itself stays —
it's the v0.1.3+ default. Users who want
permissive mode can set
`strict_wake_phrase = false` in
`~/.gundam-halo/config.toml`.

The `config.py:225-235` comment (the docstring
on `strict_wake_phrase`) gets updated to drop
the "mitigated by first-launch log line + 7-day
upgrade banner" sentence.

**Frontend**:
`frontend/src/routes/settings/VoiceTab.tsx:65-99`
+ the `showUpgradeBanner` state
(`VoiceTab.tsx:125`) + the useEffect that sets
it (`VoiceTab.tsx:168-172`) + the banner JSX
(`VoiceTab.tsx:278-300`).

The 7-day TTL is implemented via
`UPGRADE_BANNER_TTL_MS = 7 * 24 * 60 * 60 * 1000`
(line 66) and the
`halo.voice.strict-banner-dismissed-at`
`localStorage` key (line 65). The helpers
`shouldShowUpgradeBanner` (line 68) and
`dismissUpgradeBanner` (line 91) are
TS-private — not exported. The whole block
(35 lines + 50 lines of banner JSX + 5 lines
of state) goes away.

Sprint 22 spec marks these for deletion in
Sprint 23+.

### 4.2 WER acceptance criterion

Per M9-E §"Layer  acceptance" (and Sprint 20
§4.2, unchanged in Sprint 22):

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
      longer needed** (delete lines 180-195 of
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

**Sprint 22 addendum**: the WER gate is checked
**before** Track 3's augmented-note deletion
lands. The 1-hour workflow is:

1. User runs `scripts/finetune_whisper_yue.py`
   + `finetune_whisper_yue_monitor.py` (Sprint
   19d runbook). Monitor exits 0 on success.
2. User runs `tests/voice/test_whisper_yue.py` —
   asserts WER < 20% on the held-out fixture.
3. User runs the M9-C live re-run with the
   augmented note **still in place** (the v0.1.3
   code) and the new `whisper_hf` backend. If
   the agent completes the file_read task, the
   fine-tune is good.
4. User removes the augmented note (Track 3
   change) and re-runs M9-C. If the agent
   completes, **commit**. If the agent fails,
   `git revert` and decide whether to re-train
   or defer the sprint.

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

**`voice_ws.py:976`** (the `asr_backend` validation
list) gets `"whisper_hf"` added:

```python
if raw not in ("whisper_local", "yuesub", "whisper_hf"):
    raise HTTPException(
        status_code=400,
        detail=(
            f"`asr_backend` must be one of: whisper_local, "
            f"yuesub, whisper_hf (got {raw!r})"
        ),
    )
```

**Sprint 19b restart-scheduled flow** (already
wired) automatically fires when the user PATCHes
`asr_backend` from `whisper_local` to
`whisper_hf` via the Settings → Voice tab —
no extra work in voice_ws.

### 4.4 Dependency graph

```
+----------------------------------+
| Step 1: prepare_common_voice_yue |  ← Sprint 21 ✓ (commit 3353106)
| (180 LoC impl in finetune script) |
+----------------+-----------------+
                 v
+----------------------------------+
| Actual training run             |  ← User session, 3h+
| (Sprint 19d runbook + monitor)   |
+----------------+-----------------+
                 v
+----------------------------------+
| Step 2: WhisperHFASR backend     |  ← Sprint 23, 1 day
| (factory + impl + tests)         |    (Track 1)
+----------------+-----------------+
                 v
+----------------------------------+
| Step 3: remove warning           |  ← Sprint 23, 30 min
| (WhisperLocalASR cleanup)        |    (Track 2)
+----------------+-----------------+
                 v
+----------------------------------+
| Step 4: M9-C live re-run         |  ← User session, 5 min
| (acceptance test for the fine-tune)
+----------------+-----------------+
                 v
+----------------------------------+
| Step 5: delete augmented note   |  ← Sprint 23, 1 hour
| (m9c_voice_tools.py:180-195)     |    (Track 3, conditional on Step 4)
+----------------+-----------------+
                 v
+----------------------------------+
| Track 4: Sprint 17a banner      |  ← Sprint 23, 30 min
| expiry dead-code removal          |    (no conditional — banner TTL
+----------------+-----------------+     already expired)
                 v
+----------------------------------+
| Optional: supervisor             |  ← Sprint 24+ (deferred)
+----------------------------------+
```

Tracks 1 + 2 + 3 + 4 cluster naturally into
Sprint 23 (1.5 days total). Track 1 is the
chunks (1 day). Tracks 2 + 3 + 4 are 30 min +
1 hour + 30 min = 2 hours of small edits.
Sprint 23 is the implementation sprint; Sprint
22 (this spec) is the design freeze.

## 5. File-by-file change set (when Sprint 23+ lands)

| Path | Change | LoC est. |
|---|---|---|
| `backend/app/voice/asr/whisper_hf.py` | NEW. `WhisperHFASR` class implementing `ASRInterface` + `_import_transformers` + `_resolve_device` + `_resolve_torch_dtype` + `_pcm_bytes_to_float32` helpers | +200 / 0 |
| `backend/app/voice/asr/asr_factory.py` | Add `whisper_hf` branch + lazy import + `model_path` empty-check | +20 / 0 |
| `backend/app/voice/asr/whisper_local.py` | Replace the `model_path` warning (lines 80-99) with a `ValueError`. Drop the `_model_path` field's docstring note about "fully wired in v0.1.4". | 0 / -25 |
| `backend/app/core/config.py` | Remove the `_STRICT_WAKE_UPGRADE_LOGGED` flag (line 33) + the first-launch INFO block in `load_config` (lines 519-552) + drop the "mitigated by first-launch log line + 7-day upgrade banner" comment on `strict_wake_phrase` (line 230). | 0 / -45 |
| `backend/app/api/voice_ws.py` | Add `"whisper_hf"` to the `asr_backend` validation list (line 976) + update the error message (line 980). | +2 / -2 |
| `backend/tests/voice/test_whisper_hf.py` | NEW. 8-10 tests: model load, transcribe happy path, WER against fixture, model_path error, language yue→cantonese mapping, device auto-resolution, compute_type float16 path, missing `transformers` ImportError, lazy import isolation. | +250 / 0 |
| `backend/tests/voice/test_whisper_local.py` | NEW. 2-3 tests: `model_path` non-empty raises `ValueError`; `model_path=""` default loads as before; the error message references `whisper_hf`. | +50 / 0 |
| `backend/scripts/m9c_voice_tools.py` | Delete the augmented-note block (lines 180-195). Replace with a one-line M9-E Layer 2 comment. | 0 / -16 |
| `frontend/src/routes/settings/VoiceTab.tsx` | Remove `UPGRADE_BANNER_KEY` (line 65) + `UPGRADE_BANNER_TTL_MS` (line 66) + `shouldShowUpgradeBanner` (line 68-89) + `dismissUpgradeBanner` (line 91-99) + `showUpgradeBanner` state (line 125) + the useEffect branch that sets it (line 168-172) + the banner JSX (line 278-300). | 0 / -50 |
| `~/.gundam-halo/config.toml` | Update `[voice.asr]` block to `backend = "whisper_hf"` + `model_path = "~/.gundam-halo/models/whisper-yue-base/"` (one-time, manual) | +3 / -1 |
| `docs/CHANGELOG.md` | v0.1.4 release entry: model swap, M9-C acceptance, augmented-note removal, banner expiry dead-code | +80 / 0 |
| `docs/tickets/M9-E.md` | Mark Layer 2 acceptance boxes ✓ (or ✗ if WER > 20%) | +5 / -5 |
| `pyproject.toml` | Add `voice-hf` optional extra: `transformers>=4.40`, `torch` (CPU + MPS wheels; the user picks the index based on their Mac), `accelerate>=0.30`, `soundfile>=0.12` | +5 / 0 |

**Total**: ~615 LoC. ~1.5-2 days wall clock over
2 sprints (Sprint 22 = spec, Sprint 23 = impl).

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
| **Track 4 banner removal breaks someone's flow** | Low | Low | The 7-day TTL is already expired for everyone. The log line only fires on first launch (in-memory flag). Removing it doesn't change behavior for users who already have `strict_wake_phrase` in their config. The only affected user is one who installed 17a+ but never opened Settings → Voice in >7 days — that user already accepted the new default implicitly. |
| **`transformers` + `torch` install size** | Low | Low | `transformers` ~250MB + `torch` (CPU + MPS) ~600MB = ~850MB extra. The user's M-series Mac has gigabytes free; this is in line with the `voice-yuesub` extra (~2GB). No new wheel pinning concerns. |
| **Sprint 23 happens before training run finishes** | Medium | Medium | Sprint 22 ships a spec; Sprint 23 is the impl sprint. If the user hasn't run training by Sprint 23 start, Track 1's `WhisperHFASR` is still testable (with a placeholder HF-format checkpoint like `openai/whisper-tiny` downloaded via `huggingface-cli`). The acceptance test for the fine-tune (Track 3) is gated on the training run. |

## 7. Acceptance tests

1. **Track 1 — `WhisperHFASR` smoke** —
   `pytest tests/voice/test_whisper_hf.py -v` —
   8-10 tests covering model load, transcribe
   happy path, WER against a fixture, model_path
   error, language yue→cantonese mapping, device
   auto-resolution, compute_type float16 path,
   missing `transformers` ImportError, lazy import
   isolation (the test module imports
   `whisper_hf` without `transformers` installed —
   `ImportError` only fires on `warmup()`).
2. **Track 2 — `whisper_local` no warning** —
   `pytest tests/voice/test_whisper_local.py -v` —
   new file with 2-3 tests:
   - `test_whisper_local_warmup_with_model_path_raises`
     — passing `model_path="/somewhere"` raises
     `ValueError` referencing `whisper_hf`.
   - `test_whisper_local_warmup_without_model_path_ok`
     — passing `model_path=""` (default) loads
     `whisper` as before. This test uses the
     same `unittest.mock.patch("whisper.load_model")`
     pattern as the existing 16
     `test_voice_config_asr.py` cases.
   - The 16 existing `test_voice_config_asr.py`
     cases stay green (they don't pass
     `model_path`).
3. **Track 3 — M9-C live re-run** — manual smoke,
   run `m9c_dryrun_infra.py` (or the live
   equivalent), assert the agent still completes
   the file_read task on `README.md` and replies
   in Cantonese. **Run twice**: once with the
   augmented note (the v0.1.3 code) and once
   without. If both pass, commit the deletion.
   If only the v0.1.3 run passes, revert and
   decide whether to re-train.
4. **Track 4 — banner expiry dead-code removal** —
   `git diff config.py frontend/src/routes/settings/VoiceTab.tsx`
   should show the `_STRICT_WAKE_UPGRADE_LOGGED`
   flag + first-launch block + 4 helpers + banner
   JSX removed. Manual smoke: launch the app
   with a fresh `~/.gundam-halo/` (or back up
   the user's `config.toml`, delete it, relaunch
   with a missing `strict_wake_phrase` key) and
   confirm no INFO log line about the upgrade
   appears. Manual smoke 2: open
   Settings → Voice and confirm the banner is
   gone.
5. **No regression** — all 52 backend voice
   tests + 0 skip from Sprint 21 still pass.
   All 63 frontend vitest tests still pass.
   `pnpm tsc --noEmit` clean. `pnpm build`
   succeeds.

## 8. Sign-off

- [ ] **Track 1 scope agreed** — `WhisperHFASR`
      backend impl (200 LoC) + factory branch
      (20 LoC) + tests (250 LoC). No surprises.
- [ ] **Track 2 scope agreed** — `whisper_local`
      `model_path` becomes a hard `ValueError`
      (warning removed). 25 LoC removed.
- [ ] **Track 3 scope agreed** — augmented
      system note deletion (16 LoC removed)
      in `m9c_voice_tools.py`. Conditional on
      the M9-C live re-run passing without it.
- [ ] **Track 4 scope agreed** — Sprint 17a
      upgrade-banner expiry dead-code removal
      (45 LoC backend + 50 LoC frontend
      removed). No conditional.
- [ ] **Out-of-scope items confirmed** —
      launchd / systemd supervisor; mlx-whisper
      inference; self-record corpus + Layer 2 v2
      all deferred to Sprint 24+.

---

## Appendix A — Sprint 22 vs Sprint 20 scope delta

Sprint 20 (commit `ffc2624`) listed 3 Steps for
Sprint 22: Step 2 (WhisperHFASR), Step 3
(warning removal), Step 5 (augmented-note
deletion). Sprint 22 adds **Track 4** (Sprint
17a upgrade-banner expiry), which Sprint 20
didn't include. The reason: Sprint 20 was
written 2026-06-13, just after Sprint 17a's
banner shipped. Sprint 22 is written
2026-06-17, after 4 days — within the 7-day
TTL window, but the dead-code removal is
already on the cleanup backlog. Sprint 22
formalises the cleanup so the v0.1.4 release
ships a clean baseline.

If the user wants Sprint 22 to ship *only*
Sprint 20's 3 Steps, Track 4 can be deferred
to a "Sprint 25 cleanup" sprint with no
dependency on the training run.

## Appendix B — Test count evolution

| Sprint | New tests added | Total backend voice | Total frontend | Total LoC (delta) |
|---|---|---|---|---|
| 16 (wake + VoiceTab) | +8 | 8 | 8 | +400 |
| 17a (strict + sanitizer) | +12 | 20 | 20 | +600 |
| 17b Track A-F | +53 | 73 | 25 | +1100 |
| 18 (CyberWaveform mount) | +5 | 73 | 30 | +250 |
| 19a (fsmn-vad-online) | +8 | 81 | 30 | +180 |
| 19b (auto-restart) | +3 | 84 | 30 | +100 |
| 19c P1 (VAD events) | +3 | 87 | 30 | +150 |
| 19c P2 (always-on) | +6 | 87 | 36 | +200 |
| 19d prep (smoke) | +4 | 91 | 36 | +80 |
| 19d addendum (monitor) | +7 | 98 | 36 | +120 |
| 20 (spec-only) | 0 | 98 | 36 | +374 (spec) |
| 21 (prepare impl) | +5 (1 replaced) | 102 | 36 | +922 |
| **22 (this spec)** | 0 (spec-only) | 102 | 36 | **+490 (this spec)** |
| 23 (planned) | +10 to +13 | 112-115 | 36 | +615 |

Sprint 23's 10-13 new tests break down as:
- `test_whisper_hf.py`: 8-10 (Track 1)
- `test_whisper_local.py`: 2-3 (Track 2)

The frontend test count stays at 36 — Track 4's
banner removal drops 1 test (the implicit
"banner shows" assertion) but no new test is
needed (deletion tests aren't a thing; the
deletion is verified by `git diff` and the
manual smoke).

## Appendix C — `_STRICT_WAKE_UPGRADE_LOGGED` 紀律

`_STRICT_WAKE_UPGRADE_LOGGED` 係 a module-level
flag (not file-based), so it resets on backend
restart. The intent of Sprint 17a's "7-day
upgrade banner" was two-part:

1. **Frontend**: `localStorage` TTL with
   `UPGRADE_BANNER_TTL_MS = 7 * 24 * 60 * 60 * 1000`.
   The banner disappears 7 days after the user
   first sees it, even if they don't dismiss it.
2. **Backend**: one-time INFO log line on first
   launch. The flag prevents repeat emission
   within a process. The flag is per-process —
   a backend restart re-evaluates the condition
   and re-emits if the user still has no
   `strict_wake_phrase` key.

The backend design is **flawed in hindsight**:
the flag is per-process, not per-install, so a
user who restarts the backend 8 days after
install would still see the log line. The 7-day
TTL is only honored on the frontend. Sprint
22's Track 4 is the fix — remove the dead
backend code entirely.

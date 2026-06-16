# Feature Spec — Sprint 19a: fsmn-vad-online real per-frame speech probability

> **Status:** DRAFT — awaiting user sign-off.
> **Author:** Mavis (orchestrator).
> **Scope:** 1 working day. Backend-only. Closes the explicit
> deferred follow-up from Sprint 17b Track D (commit `c8c7189`),
> which shipped the dual-VAD wiring but used RMS-energy as a
> placeholder for the cockpit HUD's level source. This sprint
> replaces that placeholder with fsmn-vad-online's actual
> per-frame speech probability. **No frontend changes, no
> model downloads, no test deletions.**
> **Out of scope (deferred to 19b/19c/19d):** auto-restart on
> ASR change, Tauri always-on mic, Cantonese Whisper fine-tune.

---

## 0. Why this sprint exists

Sprint 17b Track D's spec §5.1 said:

> The audio-level VAD runs in parallel with the
> utterance-boundary VAD and feeds the cockpit HUD's
> per-frame pulse. ... the level source itself is currently
> RMS-energy-based and ships in the same venv, so no extra
> dep is required.

That worked, but the file-level comment in
`backend/app/voice/vad/fsmn_vad.py` makes the deferred intent
explicit:

> We DO keep an `FsmnVAD` instance so the dual-VAD invariant
> in spec §5.1 is preserved, and so a follow-up sprint can
> swap the level source to fsmn-vad's internal speech_prob
> without changing the pipeline's API.

> If you need a per-frame probability that's VAD-trained
> (not just energy-based), the proper path is: instantiate
> the funasr Fsmn_vad_online model, drive it chunk-by-chunk
> threading `param_dict`, and call `vad_scorer.vad_scorer.
> get_score()` after each chunk. We don't do that here because
> the audio HUD use case doesn't need it.

Sprint 18 then built Sprint 17b's intended user-visible
feature (cockpit CyberWaveform in `SignalCard.tsx`) on top
of the RMS placeholder. With the cockpit mount shipped, the
next logical follow-up is to make the level source VAD-
trained instead of energy-based — that's Sprint 19a.

## 1. Goals (success criteria)

1. **Real fsmn-vad per-frame speech probability.** The
   `FsmnVAD.process_frame` method now drives
   `funasr_onnx.Fsmn_vad_online` chunk-by-chunk, threading
   the `vad_scorer` state across calls (the `vad_scorer`
   object already accumulates internal cache; we don't need
   to manage `param_dict` ourselves since the scorer resets
   itself between calls). The per-frame `level` returned in
   `VADEvent.probability` is the **VAD-trained speech
   posterior** (0.0-1.0) read from the most recent
   `E2EVadFrameProb.speech_prob` in the scorer's
   `frame_probs` list.
2. **Same VADEvent contract.** The pipeline's
   `last_audio_level = level_event.probability` line doesn't
   change. The voice WS handler's `vad.audio_level` WS
   broadcast doesn't change. The frontend's `useMicAnalyser`
   + `CyberWaveform` consumers don't need a code change.
3. **Lazy / optional model load.** The FsmnVAD
   constructor takes a `model_dir: str | None = None`
   parameter. If `None`, the old RMS-energy path is used
   (backward compat for tests and environments that haven't
   downloaded the fsmn-vad model). If a path is provided,
   the model is **lazy-loaded on first `process_frame` call**
   (not in `__init__` or `warmup`) so the import cost of
   funasr_onnx is paid only when actually used.
4. **Warmup still cheap.** `warmup()` continues to be a
   no-op for the energy path; for the model path it sets
   the `output_frame_probs` flag and pre-allocates an empty
   `frame_probs` reset. The actual model instantiation
   happens on first `process_frame`.
5. **Reset clears model state.** `reset()` calls
   `m.vad_scorer.AllResetDetection()` to clear the scorer's
   internal cache and `frame_probs` list, so a new turn
   starts with a clean state.
6. **No regression.** The 12 existing
   `test_fsmn_vad.py` tests (which use the energy path)
   keep passing. New tests cover the model path with
   real audio fixtures.

## 2. Out of scope (deferred)

- **Auto-restart on ASR change (Sprint 19b)** — separate
  reliability sprint, depends on 19a's pipeline.
- **Tauri always-on mic (Sprint 19c)** — frontend + Swift
  binding, depends on 19a's VAD-trained level source so
  the always-on mode can rely on the VAD's is_speech.
- **Cantonese Whisper fine-tune (Sprint 19d)** —
  independent infra, GPU machine, 3h+ wall clock.
- **Replace the silero utterance-boundary VAD** — silero
  stays as the speech_start / speech_end detector.
  fsmn-vad-online is **only** the per-frame HUD level
  source.
- **Wake word detection** — that's a separate problem
  (KWS, not VAD).

## 3. User-facing behavior

This sprint is **invisible to the user** in the happy path.
The cockpit's CyberWaveform already pulses to the user's
voice via `useMicAnalyser` (Sprint 18). After Sprint 19a,
the wave is driven by a VAD-trained probability instead of
raw RMS, so:

- The wave responds to **voice** rather than just **loud
  sound** (a loud TV with no speech will produce a flat
  wave; a soft-spoken user will produce a healthy pulse).
- Background hum below the VAD's speech-noise threshold
  (`speech_noise_thres: float = 0.6` in
  `VADXOptions`) is suppressed.
- Tighter correlation with the actual `asr.result` text
  boundary — the wave now rises in lockstep with the
  frames that produce text.

The voice WS protocol doesn't change. The `vad.audio_level`
WS frame's `level` field's range stays [0, 1] but the
semantic is "VAD speech posterior" instead of "RMS
loudness".

## 4. Architecture

### 4.1 Streaming model

`funasr_onnx.Fsmn_vad_online` exposes a chunk-based
streaming API. The relevant call site is
`Fsmn_vad_online.__call__(audio_in: np.ndarray, is_final=
False) -> List[Segment]`. Internally, the model runs a
sliding-window FSMN over the audio and accumulates a
`vad_scorer` state object (`E2EVadModel`). After each
chunk, the scorer's `frame_probs` list contains one
`E2EVadFrameProb` per processed internal frame (10ms
internal frame, 25ms per the VADXOptions; our 250ms audio
chunks produce ~10 internal frames per chunk).

Crucially, the scorer state **persists across calls** — it
holds `data_buf`, `scores`, the `frame_probs` history, and
the state machine. We don't need to manage `param_dict`
ourselves because the funasr wrapper handles it
internally. The contract for our `FsmnVAD.process_frame` is:

1. Convert int16 PCM bytes → float32 ndarray.
2. Call `self._model(audio, is_final=False)`.
3. Read `self._model.vad_scorer.frame_probs[-1].speech_prob`.
4. Map `speech_prob` (log domain, typically [-2.0, 0.0]) to
   `level ∈ [0.0, 1.0]` via `math.exp(speech_prob)` and
   clamp.
5. Return `VADEvent(probability=level, is_speech=
   level > 0.5, ...)`.

### 4.2 Lazy model load

```python
class FsmnVAD:
    def __init__(self, model_dir: str | None = None, ...):
        self._model_dir = model_dir
        self._model: Fsmn_vad_online | None = None
        # ... existing energy-path fields unchanged

    def _ensure_model_loaded(self) -> Fsmn_vad_online | None:
        """Lazy load the fsmn-vad model on first use.

        Returns None if model_dir is unset (caller falls back
        to the energy path). Raises if model_dir is set but
        the directory doesn't exist or model loading fails.
        """
        if self._model_dir is None:
            return None
        if self._model is None:
            from funasr_onnx import Fsmn_vad_online
            self._model = Fsmn_vad_online(
                self._model_dir,
                quantize=True,
                intra_op_num_threads=2,
            )
            self._model.vad_scorer.vad_opts.output_frame_probs = True
        return self._model
```

The `model_dir` default is `None`, preserving the old
energy-path behavior. The voice WS factory (in
`voice_ws.py:180` `audio_level_vad = FsmnVAD()`) is updated
to pass `model_dir=cfg.vad.model_path` so the cockpit HUD
benefits from VAD-trained levels in production while tests
keep using the energy path.

### 4.3 Reset clears model state

```python
def reset(self) -> None:
    self._chunk_buffer.clear()
    if self._model is not None:
        # Clear the scorer's internal cache so a new turn
        # doesn't see stale `data_buf` from the previous
        # turn. AllResetDetection resets every internal
        # state field on the E2EVadModel.
        self._model.vad_scorer.AllResetDetection()
```

### 4.4 Process frame with VAD-trained probability

```python
def process_frame(self, pcm: bytes, sample_rate: int = 16000) -> VADEvent:
    if sample_rate != 16000:
        raise ValueError(...)
    int16 = np.frombuffer(pcm, dtype=np.int16)
    if int16.size == 0:
        return VADEvent(is_speech=False, probability=0.0, ...)

    model = self._ensure_model_loaded()
    if model is not None:
        # VAD-trained path: drive fsmn-vad-online chunk-by-chunk
        # and read the most recent speech_prob from the scorer's
        # accumulated frame_probs list.
        audio = int16.astype(np.float32) / 32768.0
        try:
            _ = model(audio, is_final=False)
            probs = model.vad_scorer.frame_probs
            if probs:
                last_log = probs[-1].speech_prob
                level = max(0.0, min(1.0, math.exp(last_log)))
            else:
                level = 0.0
        except Exception as e:
            # Model failed mid-turn (e.g. ONNX runtime error).
            # Fall back to energy for this frame only and log.
            logger.warning(f"fsmn-vad error: {e}; falling back to RMS")
            level = self._rms_level(int16)
        is_speech = level > 0.5
        return VADEvent(is_speech=is_speech, probability=level, ...)
    # Energy path (unchanged from Sprint 17b Track D)
    return self._energy_event(int16)
```

### 4.5 The `level` field's range

fsmn-vad-online's internal `speech_prob` is a log-domain
score (`math.log(1.0 - sum(sil_pdf_scores))`) where the
silence pdf score is higher during silence. Exploratory
runs (see commit message) showed:

- Silence: `speech_prob ≈ -0.5` (log domain)
- Speech: `speech_prob ≈ -1.5` (log domain)

The raw `math.exp(speech_prob)` mapping produces a
**weaker discrimination** (silence ≈ 0.6, speech ≈ 0.2)
because the FSMN is biased toward silence. A better
mapping is the **frame SNR** — the difference between
the current frame's loudness and the rolling noise
floor:

```python
snr_db = (last_decibel - noise_average_decibel) / 20.0
level = max(0.0, min(1.0, snr_db))
```

This gives:
- Silence: SNR ≈ 0 dB → `level ≈ 0.0`
- Speech: SNR ≈ 10-20 dB → `level ≈ 0.5-1.0`

We read the source values from
`m.vad_scorer.decibel[-1]` and
`m.vad_scorer.noise_average_decibel` (already populated
by the FSMN's per-frame call). The factor of `/20.0`
scales the SNR into the [0, 1] HUD range for typical
speech levels; a loud shout (30 dB SNR) clamps to 1.0.

The energy-path `level` calculation is left as a private
`_rms_level()` helper that the VAD path can fall back to
on model errors. The `is_speech` boolean for the VAD path
is `level > 0.5` (the silero utterance-boundary VAD
ignores this field per the dual-VAD invariant).

## 5. File-by-file change set

| Path | Change | LoC est. |
|---|---|---|
| `backend/app/voice/vad/fsmn_vad.py` | Add `model_dir` constructor param; lazy-load Fsmn_vad_online; add `_ensure_model_loaded`; add `_snr_level` helper; rewrite `process_frame` to use the VAD path when model is loaded; refactor existing RMS code into `_rms_level` + `_energy_event` private helpers so the VAD path and the energy path share frame-decoding and timestamp logic | +90 / -30 |
| `backend/app/voice/vad/vad_factory.py` | When creating FsmnVAD from config, pass `model_dir=cfg.vad.model_path` so the cockpit HUD uses VAD-trained levels in production. Keep the test override for `model_dir=None` | +10 / -2 |
| `backend/app/api/voice_ws.py` | `FsmnVAD()` instantiation at line 180 already takes no args; the factory change above handles the model_dir threading, no change needed here | 0 / 0 |
| `backend/tests/voice/test_fsmn_vad.py` | Keep all 12 existing tests (energy path); add 8 new tests covering: lazy load triggers on first process_frame call, model not loaded when model_dir=None, speech_prob mapping produces level > 0.5 for synthetic speech, level < 0.2 for synthetic silence, reset clears frame_probs, AllResetDetection is called, model load error raises (not silent), warmup is idempotent on model path | +200 / 0 |
| `docs/FEATURE-SPEC-SPRINT19a.md` | NEW. This file. | +300 / 0 |
| `docs/CHANGELOG.md` | Add Sprint 19a entry under [Unreleased] | +30 / 0 |

**Total**: ~600 LoC. Backend-only. ~1 day wall clock.

## 6. Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **funasr_onnx import is slow** (~500ms) | High | Low | Lazy-load on first `process_frame`, not in `__init__` or `warmup`. Tests that don't pass `model_dir` skip the import entirely. |
| **fsmn-vad inference per frame is slow** (~30-50ms on CPU) | Medium | Medium | The voice WS already has 50ms rate-limiting on the `vad.audio_level` broadcast, so 30-50ms inference fits. The silero utterance-boundary VAD is unchanged (separate model). |
| **speech_prob mapping doesn't match user expectations** (level rises on background TV) | Medium | Medium | Use the SNR-based mapping (decibel - noise_average_decibel) which is robust to TV / music. Test fixtures use synthetic speech-shaped noise to verify the mapping. |
| **Lazy load race in multi-threaded asyncio pipeline** | Low | Medium | `process_frame` is sync (no `async` keyword). The voice WS runs it from an async handler via `self._audio_level_vad.process_frame(...)` which is fine — no thread race. The lazy-load check is single-threaded within a frame processing. |
| **Test fixtures can't load the fsmn-vad model** (CI environment) | Low | Low | Tests with `model_dir=None` use the energy path. Tests with `model_dir=...` are skipped if the model isn't available (`pytest.skip(...)` based on `os.path.isdir(...)`). |
| **Existing 12 energy-path tests break** | Low | High | The new constructor's `model_dir` defaults to `None`, so the energy path is preserved. All 12 existing tests pass `model_dir=None` (the new default) and continue working. |
| **AllResetDetection side effects** (resets `data_buf_start_frame` etc.) | Low | Low | The pipeline calls `reset()` only at turn boundaries (see `pipeline.py:189`). The state machine is designed to be reset between utterances. |
| **Funasr's `E2EVadFrameProb.speech_prob` API changes** | Low | Medium | The funasr_onnx 0.4.1 pin (per `pyproject.toml` voice-yuesub group) is the contract. If we ever upgrade funasr_onnx, the `frame_probs` list / `E2EVadFrameProb` field names may need updating. Pinned to a specific minor version in `pyproject.toml`. |

## 7. Acceptance tests

1. **Energy path regression** — the 12 existing
   `test_fsmn_vad.py` tests pass unchanged.
2. **Lazy load semantics** — `FsmnVAD(model_dir=None)`
   never imports `funasr_onnx` (assert via
   `sys.modules` spy).
3. **Model path produces high level for synthetic
   speech** — a 250ms chunk of int16 sine wave at 440Hz
   with amplitude 0.3 produces `level > 0.5`.
4. **Model path produces low level for synthetic
   silence** — a 250ms chunk of all-zero PCM produces
   `level < 0.2`.
5. **Reset clears state** — after a turn ends and
   `reset()` is called, `m.vad_scorer.frame_probs` is
   empty (assert via `len(m.vad_scorer.frame_probs) == 0`).
6. **Warmup is idempotent** — calling `warmup()` twice
   doesn't reload the model.
7. **Model load error falls back to energy with a
   warning** — pointing `model_dir='/nonexistent'`
   doesn't crash the cockpit HUD; `process_frame` falls
   back to the energy path and emits a `UserWarning`
   matching `"model load failed"` so ops can diagnose
   the missing model in the server log. The Sprint 17b
   reliability philosophy ("don't kill push-to-talk
   because a download is missing") is preserved.
8. **Pipeline contract** — `pipeline.py` line 224
   `self.last_audio_level = level_event.probability`
   receives a value in [0, 1] from both the energy and
   model paths.
9. **Voice WS contract** — `voice_ws.py:222` `vad.audio_level`
   broadcast's `level` field is in [0, 1] for both paths.

## 8. Sign-off

- [ ] **Track 19a scope agreed** — replace RMS placeholder
      with fsmn-vad-online's per-frame speech probability,
      lazy-load the model on first use, SNR-based level
      mapping, no frontend change.
- [ ] **Out-of-scope items confirmed** — auto-restart (19b),
      Tauri always-on mic (19c), Whisper fine-tune (19d)
      all deferred to follow-up sub-sprints.

**Sign-off → todo list breaks into 3 tracks:**
- Track 19a-A: refactor `fsmn_vad.py` (4 hours)
- Track 19a-B: update `vad_factory.py` to pass `model_dir`
  from config (1 hour)
- Track 19a-C: rewrite `test_fsmn_vad.py` + commit (2
  hours)

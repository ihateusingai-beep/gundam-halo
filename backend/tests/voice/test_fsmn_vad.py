"""Sprint 17b Track D + Sprint 19a: tests for the FsmnVAD audio-level VAD.

The FsmnVAD class is the second VAD in the dual-VAD pipeline
(see docs/FEATURE-SPEC-SPRINT17b.md §5.1). It produces a
per-frame audio level (0.0-1.0) that drives the cockpit
HUD's pulse.

Sprint 17b used RMS energy with log compression as the
level source (a placeholder). Sprint 19a replaces that
placeholder with fsmn-vad-online's actual per-frame speech
probability (frame SNR — see docs/FEATURE-SPEC-SPRINT19a.md
§4.5). The model is **lazy-loaded** on first process_frame
call, and falls back to the RMS path if `model_dir` is
None or the model fails to load.

These tests verify:
  - The energy-path contract (Sprint 17b): probability in
    [0, 1], silence returns near-zero, loud noise returns
    higher, energy_floor tunable, warmup idempotent, reset
    clears state, factory wiring.
  - The Sprint 19a VAD-trained path: lazy load, model
    load error raises, SNR mapping produces high level
    for synthetic speech and low for silence, reset calls
    AllResetDetection, warmup is idempotent on the model
    path.
"""
from __future__ import annotations

import numpy as np
import pytest


# ---------------------------------------------------------------------------
# 1. Per-frame level computation
# ---------------------------------------------------------------------------


def test_fsmn_vad_silence_returns_zero():
    """All-zero PCM returns probability=0.0 (no energy)."""
    from app.voice.vad.fsmn_vad import FsmnVAD

    v = FsmnVAD()
    silence = np.zeros(16000, dtype=np.int16).tobytes()
    e = v.process_frame(silence, sample_rate=16000)
    assert e.probability == 0.0
    assert e.is_speech is False


def test_fsmn_vad_loud_noise_returns_substantial_level():
    """Random noise at ~30% RMS returns a probability in the
    0.4-0.9 range (log compression scales conversational
    speech to this band)."""
    from app.voice.vad.fsmn_vad import FsmnVAD

    v = FsmnVAD()
    rng = np.random.default_rng(42)
    # Random noise at 30% of int16 range → RMS ≈ 0.30
    audio = (rng.standard_normal(16000) * 0.3 * 32768).astype(np.int16).tobytes()
    e = v.process_frame(audio, sample_rate=16000)
    assert 0.4 < e.probability < 0.9
    assert e.is_speech is True


def test_fsmn_vad_probability_in_unit_range_for_various_levels():
    """For RMS values from very quiet to very loud, the
    probability must stay in [0, 1]."""
    from app.voice.vad.fsmn_vad import FsmnVAD

    v = FsmnVAD()
    rng = np.random.default_rng(0)
    for scale in (0.001, 0.01, 0.1, 0.3, 0.6, 1.0):
        audio = (rng.standard_normal(16000) * scale * 32768).astype(np.int16).tobytes()
        e = v.process_frame(audio, sample_rate=16000)
        assert 0.0 <= e.probability <= 1.0, (
            f"scale={scale} → probability={e.probability}"
        )


def test_fsmn_vad_rejects_non_16khz():
    """VADInterface contract: 16kHz is the only supported rate."""
    from app.voice.vad.fsmn_vad import FsmnVAD

    v = FsmnVAD()
    audio = np.zeros(16000, dtype=np.int16).tobytes()
    with pytest.raises(ValueError, match="16kHz"):
        v.process_frame(audio, sample_rate=48_000)


def test_fsmn_vad_empty_frame():
    """Empty audio bytes are handled gracefully (no crash,
    probability=0, is_speech=False)."""
    from app.voice.vad.fsmn_vad import FsmnVAD

    v = FsmnVAD()
    e = v.process_frame(b"", sample_rate=16000)
    assert e.probability == 0.0
    assert e.is_speech is False


def test_fsmn_vad_energy_floor_tunable():
    """energy_floor controls the silence threshold. With
    floor=0.1, a quiet tone (RMS=0.05) reports is_speech=False;
    with floor=0.01, it reports True."""
    from app.voice.vad.fsmn_vad import FsmnVAD

    rng = np.random.default_rng(7)
    # Quiet tone at 5% RMS
    audio = (rng.standard_normal(16000) * 0.05 * 32768).astype(np.int16).tobytes()

    strict = FsmnVAD(energy_floor=0.1)
    e = strict.process_frame(audio, sample_rate=16000)
    assert e.is_speech is False  # below floor

    lenient = FsmnVAD(energy_floor=0.01)
    e = lenient.process_frame(audio, sample_rate=16000)
    assert e.is_speech is True  # above floor
    # Probability is the same either way (the level source is
    # independent of the energy_floor threshold).
    assert e.probability > 0.0


# ---------------------------------------------------------------------------
# 2. Lifecycle (warmup + reset)
# ---------------------------------------------------------------------------


def test_fsmn_vad_warmup_is_idempotent():
    """warmup() is a no-op for the energy path but must still
    be idempotent (callable multiple times without error)."""
    import asyncio

    from app.voice.vad.fsmn_vad import FsmnVAD

    v = FsmnVAD()
    asyncio.run(v.warmup())
    asyncio.run(v.warmup())  # second call should not raise
    assert v._warmed_up is True


def test_fsmn_vad_reset_clears_state():
    """reset() returns the VAD to a clean state. The energy
    path has no state to clear, but the call must succeed
    and a follow-up process_frame must work the same as
    before the reset."""
    from app.voice.vad.fsmn_vad import FsmnVAD

    v = FsmnVAD()
    audio = np.zeros(16000, dtype=np.int16).tobytes()
    e1 = v.process_frame(audio, sample_rate=16000)
    v.reset()
    e2 = v.process_frame(audio, sample_rate=16000)
    assert e1.probability == e2.probability


# ---------------------------------------------------------------------------
# 3. Factory wiring
# ---------------------------------------------------------------------------


def test_factory_creates_fsmn_vad_when_backend_set():
    """`create_vad(backend='fsmn')` returns an FsmnVAD instance."""
    from app.core.config import VoiceVADConfig
    from app.voice.vad.fsmn_vad import FsmnVAD
    from app.voice.vad.vad_factory import create_vad

    cfg = VoiceVADConfig(backend="fsmn")
    vad = create_vad(cfg)
    assert isinstance(vad, FsmnVAD)


def test_factory_creates_silero_when_backend_default():
    """Sprint 16 default (silero) is unaffected by Sprint 17b."""
    from app.core.config import VoiceVADConfig
    from app.voice.vad.silero_vad import SileroVAD
    from app.voice.vad.vad_factory import create_vad

    cfg = VoiceVADConfig(backend="silero")
    vad = create_vad(cfg)
    assert isinstance(vad, SileroVAD)


def test_factory_rejects_unknown_backend():
    """Unknown backend name raises ValueError with a helpful message."""
    from app.core.config import VoiceVADConfig
    from app.voice.vad.vad_factory import create_vad

    cfg = VoiceVADConfig(backend="webrtc")
    with pytest.raises(ValueError, match="Unknown VAD backend"):
        create_vad(cfg)


# ---------------------------------------------------------------------------
# 4. VoicePipeline dual-VAD wiring
# ---------------------------------------------------------------------------


def test_pipeline_exposes_last_audio_level_after_feed_frame():
    """When constructed with audio_level_vad, the pipeline
    updates `last_audio_level` on every feed_frame call.
    Without audio_level_vad, the field stays 0.0."""
    import asyncio
    from unittest.mock import MagicMock

    from app.voice.pipeline import VoicePipeline
    from app.voice.vad.fsmn_vad import FsmnVAD

    boundary_vad = MagicMock()
    boundary_vad.process_frame.return_value = MagicMock(
        is_speech=False, probability=0.0, timestamp_ms=0
    )

    level_vad = FsmnVAD()
    pipeline = VoicePipeline(
        vad=boundary_vad,
        asr=MagicMock(),
        audio_level_vad=level_vad,
    )
    # Quiet tone (RMS ~ 0.05) — under default energy_floor=0.005
    # the level is still measurable as a small but nonzero
    # value.
    rng = np.random.default_rng(0)
    audio = (rng.standard_normal(16000) * 0.05 * 32768).astype(np.int16).tobytes()
    asyncio.run(pipeline.feed_frame(audio))
    # Pipeline starts in IDLE so feed_frame returns early —
    # but per the dual-VAD wiring, audio_level_vad is still
    # consulted in the IDLE state. last_audio_level should
    # reflect the quiet tone.
    assert 0.0 < pipeline.last_audio_level < 0.5


# ---------------------------------------------------------------------------
# Sprint 19a: VAD-trained path (model mode)
# ---------------------------------------------------------------------------

# These tests exercise the VAD-trained level source
# (Sprint 19a). They use the real fsmn-vad-online model
# from `~/.gundam-halo/models/iic/speech_fsmn_vad_zh-cn-
# 16k-common-pytorch` and are skipped if the model isn't
# available locally. CI environments without the model
# fall back to the energy path tests above.

import os

FSMN_VAD_MODEL_DIR = os.path.expanduser(
    "~/.gundam-halo/models/iic/speech_fsmn_vad_zh-cn-16k-common-pytorch"
)


@pytest.fixture
def model_vad():
    """FsmnVAD wired to the real fsmn-vad-online model.

    Skips the test if the model isn't downloaded locally.
    Use `scripts/setup-yuesub-models.sh` to fetch it.
    """
    from app.voice.vad.fsmn_vad import FsmnVAD

    if not os.path.isdir(FSMN_VAD_MODEL_DIR):
        pytest.skip(
            f"fsmn-vad model not at {FSMN_VAD_MODEL_DIR} — "
            "run scripts/setup-yuesub-models.sh"
        )
    return FsmnVAD(model_dir=FSMN_VAD_MODEL_DIR)


def test_fsmn_vad_lazy_load_does_not_import_funasr_when_model_dir_none():
    """Sprint 19a: `FsmnVAD(model_dir=None)` must NOT pay
    the funasr_onnx import cost. We assert that
    `funasr_onnx` is not in sys.modules after
    instantiation."""
    import sys

    # Drop the module so we can prove it stays out of sys.modules
    sys.modules.pop("funasr_onnx", None)
    from app.voice.vad.fsmn_vad import FsmnVAD

    v = FsmnVAD(model_dir=None)
    assert "funasr_onnx" not in sys.modules, (
        "FsmnVAD(model_dir=None) should not import funasr_onnx"
    )
    # Sanity: process_frame in energy mode doesn't load it either
    import numpy as np
    audio = np.zeros(4000, dtype=np.int16).tobytes()
    v.process_frame(audio)
    assert "funasr_onnx" not in sys.modules


def test_fsmn_vad_lazy_load_triggers_on_first_process_frame(model_vad):
    """Sprint 19a: the model is loaded on the first
    process_frame call, not in __init__. We assert
    model_vad._model is not None after one frame."""
    assert model_vad._model is None  # not yet loaded
    import numpy as np
    audio = np.zeros(4000, dtype=np.int16).tobytes()
    model_vad.process_frame(audio)
    assert model_vad._model is not None
    # Re-confirm the model is the fsmn-vad-online class
    assert "Fsmn_vad_online" in type(model_vad._model).__name__


def test_fsmn_vad_synthetic_speech_produces_high_level(model_vad):
    """Sprint 19a: a 250ms chunk of synthetic speech
    (200Hz + 400Hz sines, amplitude 0.3) drives the SNR
    level above 0.5 once the noise floor settles.

    We feed 4 chunks of silence first to let the FSMN
    accumulate a noise floor estimate, then 4 chunks of
    synthetic speech. The 4th speech chunk should be
    distinctly louder than the silence baseline.
    """
    import numpy as np
    sr = 16000
    frame_samples = 4000
    t = np.arange(frame_samples) / sr
    speech = (0.3 * np.sin(2 * np.pi * 200 * t) + 0.3 * np.sin(2 * np.pi * 400 * t)).astype(np.float32)
    silence = np.zeros(frame_samples, dtype=np.float32)

    # 4 silence chunks to settle noise floor
    for _ in range(4):
        model_vad.process_frame((silence * 32768).astype(np.int16).tobytes())
    # 4 speech chunks — the 4th should be high
    levels = []
    for _ in range(4):
        e = model_vad.process_frame((speech * 32768).astype(np.int16).tobytes())
        levels.append(e.probability)
    # The last speech frame should be at or near the top
    # of the [0, 1] range (clamped SNR for a 200+400Hz
    # tone at 0.3 amplitude).
    assert levels[-1] > 0.5, f"expected high level for synthetic speech, got {levels}"


def test_fsmn_vad_synthetic_silence_produces_low_level(model_vad):
    """Sprint 19a: a 250ms chunk of synthetic silence
    produces a level below 0.2 once the noise floor
    settles."""
    import numpy as np
    frame_samples = 4000
    silence = np.zeros(frame_samples, dtype=np.float32)

    # 6 silence chunks — the 6th should be at the noise
    # floor (level ≈ 0).
    levels = []
    for _ in range(6):
        e = model_vad.process_frame((silence * 32768).astype(np.int16).tobytes())
        levels.append(e.probability)
    assert levels[-1] < 0.2, f"expected low level for silence, got {levels}"


def test_fsmn_vad_reset_clears_scorer_state(model_vad):
    """Sprint 19a: reset() calls AllResetDetection, so
    the scorer's frame_probs list returns to empty."""
    import numpy as np
    audio = np.zeros(4000, dtype=np.int16).tobytes()
    model_vad.process_frame(audio)  # loads model + populates state
    assert len(model_vad._model.vad_scorer.frame_probs) > 0
    model_vad.reset()
    assert len(model_vad._model.vad_scorer.frame_probs) == 0
    assert len(model_vad._model.vad_scorer.decibel) == 0


def test_fsmn_vad_warmup_idempotent_on_model_path(model_vad):
    """Sprint 19a: warmup() is safe to call twice. The
    second call must not reload the ONNX bundle."""
    import asyncio
    asyncio.run(model_vad.warmup())
    model = model_vad._model
    asyncio.run(model_vad.warmup())
    assert model_vad._model is model, "warmup() should not reload the model"


def test_fsmn_vad_model_load_error_falls_back_to_energy(tmp_path, caplog):
    """Sprint 19a: pointing model_dir at a non-existent
    path falls back to the energy path with a warning
    log, NOT a hard crash. The cockpit HUD relies on
    this for availability — the model file is a
    download, not a system dependency, so a transient
    download failure shouldn't kill the push-to-talk
    UX. The warning is surfaced to the server log so
    ops can diagnose the missing model.

    We use `caplog` (not `pytest.warns`) because the
    fallback logs via `logger.warning`, not Python's
    `warnings` module. caplog captures the log record
    and lets us assert the message.

    Spec §6 risk "Test fixtures can't load the fsmn-vad
    model" applies here too: in production this code
    path keeps the cockpit alive when the user's
    `~/.gundam-halo/models/iic/...` symlink is broken.
    """
    import logging
    from app.voice.vad.fsmn_vad import FsmnVAD

    v = FsmnVAD(model_dir=str(tmp_path / "nonexistent"))
    import numpy as np
    audio = np.zeros(4000, dtype=np.int16).tobytes()
    with caplog.at_level(logging.WARNING, logger="app.voice.vad.fsmn_vad"):
        e = v.process_frame(audio)
    # The fallback to energy MUST succeed (returns a
    # valid VADEvent in [0, 1]) and emit a warning so
    # ops can see the model isn't where we expected.
    assert e.probability == 0.0  # silence in, zero out
    assert e.is_speech is False
    # We never loaded the model
    assert v._model is None
    # And the warning is in the log
    assert any(
        "model load failed" in record.message
        for record in caplog.records
    ), f"expected 'model load failed' warning, got: {[r.message for r in caplog.records]}"


def test_fsmn_vad_factory_passes_model_dir():
    """Sprint 19a: `create_vad(backend='fsmn')` passes
    `config.model_path` to FsmnVAD as `model_dir`, so
    production deployments get the VAD-trained level
    source while tests can opt out with
    `FsmnVAD(model_dir=None)`."""
    import os
    from unittest.mock import patch
    from app.voice.vad import vad_factory
    from app.voice.vad.fsmn_vad import FsmnVAD

    # Capture the FsmnVAD instance built by the factory
    captured: dict = {}
    real_init = FsmnVAD.__init__

    def spy_init(self, *args, **kwargs):
        captured["kwargs"] = kwargs
        real_init(self, *args, **kwargs)

    with patch.object(FsmnVAD, "__init__", spy_init):
        cfg = type("Cfg", (), {
            "backend": "fsmn",
            "model_path": "/fake/path/to/model",
        })()
        vad_factory.create_vad(config=cfg)

    assert captured["kwargs"].get("model_dir") == "/fake/path/to/model", (
        f"factory should pass model_path as model_dir; got {captured['kwargs']}"
    )

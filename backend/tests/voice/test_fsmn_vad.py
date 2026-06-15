"""Sprint 17b Track D: tests for the FsmnVAD audio-level VAD.

The FsmnVAD class is the second VAD in the dual-VAD pipeline
(see docs/FEATURE-SPEC-SPRINT17b.md §5.1). It produces a
per-frame audio level (0.0-1.0) that drives the cockpit
HUD's pulse. The current implementation uses RMS energy with
log compression; a follow-up sprint will swap to fsmn-vad's
actual per-frame speech probability.

These tests verify the contract (probability in [0, 1],
silence returns near-zero, loud noise returns higher) and
the factory wiring (`create_vad(backend='fsmn')` returns
FsmnVAD).
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

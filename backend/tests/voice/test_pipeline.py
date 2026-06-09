"""Tests for the voice pipeline state machine.

Uses FakeVAD / FakeASR — no real Silero / Whisper required.
Run: cd backend && uv run pytest tests/voice/ -v
"""

from __future__ import annotations

import pytest
from app.voice.pipeline import TurnState, VoicePipeline

from tests.voice.fakes import FakeASR, FakeVAD


def _silence_frame(size: int = 8000) -> bytes:
    """8000 bytes of PCM silence (250ms at 16kHz, all zero)."""
    return b"\x00" * size


def _speech_frame(size: int = 8000) -> bytes:
    """8000 bytes of fake 'speech' (non-zero PCM)."""
    return b"\x10" * size


@pytest.mark.asyncio
async def test_pipeline_warmup_calls_both_engines():
    vad = FakeVAD()
    asr = FakeASR()
    p = VoicePipeline(vad=vad, asr=asr)
    await p.warmup()
    assert vad.warmup_called
    assert asr.warmup_called


@pytest.mark.asyncio
async def test_speech_then_silence_produces_asr_text():
    """End-to-end: speech frame → silence → end → ASR result."""
    vad = FakeVAD()
    asr = FakeASR(default_text="open Safari please")
    # min_speech_ms=0 so the test doesn't have to sleep for real wall-clock
    # time to satisfy the duration gate (FakeVAD has no clock).
    p = VoicePipeline(
        vad=vad, asr=asr, min_silence_ms=10, min_speech_ms=0
    )

    await p.warmup()
    await p.begin_turn("sess-1")

    # 3 speech frames
    vad.set_speech(True, probability=0.9)
    for _ in range(3):
        await p.feed_frame(_speech_frame())

    # Switch to silence
    vad.set_speech(False, probability=0.1)
    for _ in range(5):  # 5 * 250ms = 1.25s of silence (> min_silence_ms)
        await p.feed_frame(_silence_frame())

    result = await p.finalize_turn("sess-1")
    assert result is not None
    assert result.asr_text == "open Safari please"
    assert result.session_id == "sess-1"
    assert len(asr.transcribe_calls) == 1
    assert p.state == TurnState.IDLE


@pytest.mark.asyncio
async def test_no_speech_discards_turn():
    """If user never spoke, finalize returns None."""
    vad = FakeVAD(default_is_speech=False, default_probability=0.1)
    asr = FakeASR()
    p = VoicePipeline(vad=vad, asr=asr, min_speech_ms=100, min_silence_ms=10)

    await p.warmup()
    await p.begin_turn("sess-x")
    for _ in range(5):
        await p.feed_frame(_silence_frame())
    result = await p.finalize_turn("sess-x")
    assert result is None
    # ASR should NOT be called when nothing was said
    assert len(asr.transcribe_calls) == 0


@pytest.mark.asyncio
async def test_too_short_speech_is_dropped():
    """Speech < min_speech_ms is dropped (cough, click, etc.)."""
    vad = FakeVAD()
    asr = FakeASR()
    p = VoicePipeline(
        vad=vad, asr=asr, min_speech_ms=1000, min_silence_ms=10
    )

    await p.warmup()
    await p.begin_turn("sess-y")

    # 1 frame of speech (250ms < 1000ms min)
    vad.set_speech(True, probability=0.9)
    await p.feed_frame(_speech_frame())

    # 1 frame of silence to end
    vad.set_speech(False, probability=0.1)
    await p.feed_frame(_silence_frame())

    result = await p.finalize_turn("sess-y")
    assert result is None


@pytest.mark.asyncio
async def test_reset_clears_state():
    vad = FakeVAD()
    asr = FakeASR()
    p = VoicePipeline(vad=vad, asr=asr)
    await p.warmup()
    await p.begin_turn("sess-z")
    p.reset()
    assert p.state == TurnState.IDLE
    assert p.buffered_audio_bytes == 0
    assert vad.reset_called >= 1


@pytest.mark.asyncio
async def test_agent_callback_invoked_with_asr_text():
    """Pipeline should call the registered callback with (sid, text)."""
    vad = FakeVAD()
    asr = FakeASR(default_text="what's the weather")
    received: list[tuple[str, str]] = []

    async def cb(sid: str, text: str) -> str:
        received.append((sid, text))
        return f"reply-to: {text}"

    p = VoicePipeline(
        vad=vad,
        asr=asr,
        on_user_text=cb,
        min_silence_ms=10,
        min_speech_ms=0,
    )
    await p.warmup()
    await p.begin_turn("sess-q")

    vad.set_speech(True, probability=0.9)
    await p.feed_frame(_speech_frame())
    vad.set_speech(False, probability=0.1)
    for _ in range(3):
        await p.feed_frame(_silence_frame())

    result = await p.finalize_turn("sess-q")
    assert result is not None
    assert received == [("sess-q", "what's the weather")]
    assert result.agent_reply == "reply-to: what's the weather"


@pytest.mark.asyncio
async def test_cancel_resets_pipeline():
    vad = FakeVAD()
    asr = FakeASR()
    p = VoicePipeline(vad=vad, asr=asr)
    await p.warmup()
    await p.begin_turn("sess-c")
    vad.set_speech(True, probability=0.9)
    await p.feed_frame(_speech_frame())
    assert p.state == TurnState.SPEECH_DETECTED
    p.reset()
    assert p.state == TurnState.IDLE
    assert p.buffered_audio_bytes == 0


@pytest.mark.asyncio
async def test_ignores_frames_outside_turn():
    """Frames received before begin_turn or after finalize are dropped."""
    vad = FakeVAD()
    asr = FakeASR()
    p = VoicePipeline(vad=vad, asr=asr)
    await p.warmup()

    # No turn active — should be ignored
    await p.feed_frame(_speech_frame())
    assert p.state == TurnState.IDLE
    assert vad.frames_processed == 0  # VAD should not even be called

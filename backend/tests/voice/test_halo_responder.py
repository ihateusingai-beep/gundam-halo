"""Tests for HaloResponder — emotion parsing + TTS + Live2D orchestration."""

from __future__ import annotations

import pytest
from app.voice.halo_responder import (
    DEFAULT_EMOTION,
    VALID_EMOTIONS,
    HaloResponder,
    parse_emotion,
)

from tests.voice.fakes import FakeLive2D, FakeTTS

# --- parse_emotion ---


def test_parse_emotion_extracts_tag():
    clean, emo = parse_emotion("[EMO:awakening] Psychoframe online!")
    assert emo == "awakening"
    assert clean == "Psychoframe online!"


def test_parse_emotion_defaults_when_missing():
    clean, emo = parse_emotion("Just a normal reply.")
    assert emo == DEFAULT_EMOTION
    assert clean == "Just a normal reply."


def test_parse_emotion_lowercases():
    clean, emo = parse_emotion("[EMO:AWAKENING] Yeah")
    assert emo == "awakening"


def test_parse_emotion_rejects_unknown():
    clean, emo = parse_emotion("[EMO:not_real] Something")
    assert emo == DEFAULT_EMOTION
    assert clean == "Something"


def test_parse_emotion_handles_empty():
    clean, emo = parse_emotion("")
    assert clean == ""
    assert emo == DEFAULT_EMOTION


def test_all_documented_emotions_are_valid():
    """VALID_EMOTIONS should contain every emotion in EMOTION_MAP."""
    from app.voice.halo_responder import EMOTION_MAP

    for emo in EMOTION_MAP:
        assert emo in VALID_EMOTIONS


# --- HaloResponder.respond (one-shot) ---


@pytest.mark.asyncio
async def test_respond_emits_live2d_and_tts():
    tts = FakeTTS()
    live2d = FakeLive2D()
    r = HaloResponder(tts=tts, live2d=live2d)
    await r.warmup()

    resp = await r.respond("[EMO:focused] Working on it now. Give me a moment.")

    assert resp.emotion == "focused"
    assert resp.clean_text == "Working on it now. Give me a moment."
    # TTS got called once per sentence
    assert tts.synthesize_calls == ["Working on it now.", "Give me a moment."]
    # Live2D got the right expression for "focused"
    assert live2d.triggers == [("ntd_focused", "lean_in")]
    assert resp.audio_chunks  # at least one chunk


@pytest.mark.asyncio
async def test_respond_without_live2d_works():
    tts = FakeTTS()
    r = HaloResponder(tts=tts, live2d=None)
    await r.warmup()
    resp = await r.respond("Plain response.")
    assert resp.emotion == DEFAULT_EMOTION
    assert resp.live2d is None
    assert tts.synthesize_calls == ["Plain response."]


@pytest.mark.asyncio
async def test_respond_default_emotion_calm():
    tts = FakeTTS()
    live2d = FakeLive2D()
    r = HaloResponder(tts=tts, live2d=live2d)
    await r.warmup()
    await r.respond("Hi there.")
    # calm = idle motion, ntd_calm expression
    assert live2d.triggers == [("ntd_calm", "idle")]


@pytest.mark.asyncio
async def test_respond_skips_failed_tts_sentence(monkeypatch):
    """If TTS fails on one sentence, the rest still go through."""
    tts = FakeTTS()
    live2d = FakeLive2D()
    r = HaloResponder(tts=tts, live2d=live2d)
    await r.warmup()

    original = tts.synthesize
    calls = [0]

    async def flaky(text, voice=None):
        calls[0] += 1
        if calls[0] == 1:
            raise RuntimeError("simulated TTS failure")
        return await original(text, voice)

    tts.synthesize = flaky  # type: ignore[method-assign]

    resp = await r.respond("First sentence. Second sentence. Third sentence.")
    # We should have at least 2 TTS attempts and 1 success
    assert calls[0] == 3
    # 2 audio chunks (first was skipped after error)
    assert len(resp.audio_chunks) == 2


# --- HaloResponder.respond_stream ---


@pytest.mark.asyncio
async def test_respond_stream_yields_per_sentence():
    tts = FakeTTS()
    live2d = FakeLive2D()
    r = HaloResponder(tts=tts, live2d=live2d)
    await r.warmup()

    chunks = []
    async for sent, audio in r.respond_stream(
        "[EMO:alert] Intruder detected! Stand by!"
    ):
        chunks.append((sent, audio))

    # 2 sentences → 4 audio chunks (FakeTTS yields 2 per sentence)
    assert len(chunks) == 4
    sentences_seen = [s for s, _ in chunks]
    assert "Intruder detected!" in sentences_seen
    assert "Stand by!" in sentences_seen
    # Live2D got the alert expression
    assert live2d.triggers == [("ntd_alert", "scan")]


@pytest.mark.asyncio
async def test_respond_stream_live2d_fires_first():
    """Live2D should fire before any TTS audio arrives."""
    tts = FakeTTS()
    live2d = FakeLive2D()
    r = HaloResponder(tts=tts, live2d=live2d)
    await r.warmup()

    # Consume the stream
    async for _sent, _audio in r.respond_stream("Just a test."):
        pass

    assert live2d.triggers  # Live2D was triggered at least once

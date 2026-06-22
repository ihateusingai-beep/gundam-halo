"""Tests for the /ws/voice endpoint with TTS streaming (M2).

These tests use FakeTTS / FakeLive2D so they don't need a real
Edge-TTS connection or a real Live2D model.
"""

from __future__ import annotations

import json

import pytest
from app.api import voice_ws, ws_protocol
from app.core import config as _config_module
from app.core.registry import ToolRegistry
from app.voice.halo_responder import HaloResponder
from fastapi.testclient import TestClient

from tests.voice.fakes import FakeASR, FakeLive2D, FakeTTS, FakeVAD


@pytest.fixture
def voice_m2_app(monkeypatch):
    """Build a fresh app with voice + TTS + Live2D fakes injected."""
    from app.main import create_app

    # Fakes for input pipeline
    fake_vad = FakeVAD()
    fake_asr = FakeASR(default_text="fake-asr-text")

    # Fakes for output
    fake_tts = FakeTTS(default_audio=b"\xff\xfb\x90\x00FAKE_MP3_HALO")
    fake_live2d = FakeLive2D()

    # Patch the VAD/ASR factories
    from app.voice.asr import asr_factory
    from app.voice.vad import vad_factory
    monkeypatch.setattr(vad_factory, "create_vad", lambda config=None: fake_vad)
    monkeypatch.setattr(asr_factory, "create_asr", lambda config=None: fake_asr)
    monkeypatch.setattr(ws_protocol, "create_vad", lambda config=None: fake_vad)
    monkeypatch.setattr(ws_protocol, "create_asr", lambda config=None: fake_asr)

    # Build a HaloResponder with the fakes and inject it
    responder = HaloResponder(tts=fake_tts, live2d=fake_live2d)
    voice_ws.set_responder(responder)

    # Register a fake agent callback that yields sentence-sized chunks.
    # M15: callback contract is now an async iterator of sentences.
    from typing import AsyncIterator

    async def fake_agent(sid: str, text: str) -> AsyncIterator[str]:
        # Two sentences — the first carries the emotion tag so the
        # responder can detect it and strip it from the displayed text.
        yield f"[EMO:focused] Agent reply to: {text}."
        yield "Done."

    voice_ws.set_agent_callback(fake_agent)

    cfg = _config_module.get_config()
    original = cfg.voice.enabled
    cfg.voice.enabled = True
    # NOTE: do NOT clear ToolRegistry here. Sprint 32 P0-1 eagerly
    # imports 22 tools at app.tools.__init__.py import time so the
    # registry is populated with the full default tool set. Clearing
    # it would wipe the 22 eager-imported tools and break downstream
    # tests that rely on `default_tools()` returning the full set
    # (e.g. tests/tools/test_builder.py).
    try:
        app = create_app()
        yield app, fake_vad, fake_asr, fake_tts, fake_live2d
    finally:
        cfg.voice.enabled = original
        voice_ws.set_agent_callback(None)
        voice_ws.set_responder(None)
        # NOTE: do NOT clear ToolRegistry here (see comment
        # at the fixture entry).


@pytest.fixture
def voice_m2_client(voice_m2_app):
    app, *_ = voice_m2_app
    return TestClient(app)


def _drain_until(ws, predicate, max_messages=20, timeout=2.0):
    """Receive messages until predicate(msg) is true or we hit a limit.

    `ws.receive()` returns raw `{"type": "websocket.send", "text": ...}`
    envelopes. We unwrap to the parsed JSON message dict.

    starlette's WebSocketTestSession doesn't have a timeout, so we use
    a thread pool to enforce one (see agent memory note).
    """
    import concurrent.futures

    received = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        for _ in range(max_messages):
            try:
                future = ex.submit(ws.receive)
                raw = future.result(timeout=timeout)
            except concurrent.futures.TimeoutError:
                break
            msg = _unwrap(raw)
            received.append(msg)
            try:
                if predicate(msg):
                    return received
            except Exception:
                pass
    return received


def _drain_n_text(n, ws, timeout=2.0):
    """Receive up to *n* JSON text messages with hard timeouts.

    Skips binary frames silently (we just need the text protocol).
    """
    import concurrent.futures

    out = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        while len(out) < n:
            try:
                future = ex.submit(ws.receive)
                raw = future.result(timeout=timeout)
            except concurrent.futures.TimeoutError:
                break
            msg = _unwrap(raw)
            if msg is None:
                continue
            if msg.get("type") == "websocket.disconnect":
                break
            out.append(msg)
    return out


def _unwrap(raw: dict) -> dict | None:
    """Unwrap a starlette TestClient `receive()` envelope to a dict message.

    `ws.receive()` returns one of:
      {"type": "websocket.send", "text": "..."}    (server → client text)
      {"type": "websocket.send", "bytes": b"..."}   (server → client binary)
      {"type": "websocket.disconnect", ...}         (client disconnected)
    """
    if not isinstance(raw, dict):
        return None
    t = raw.get("type")
    if t == "websocket.send":
        text = raw.get("text")
        if text is None:
            # Binary frame — caller may want to skip these
            return {"type": "binary", "bytes": raw.get("bytes", b"")}
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"type": "text_raw", "text": text}
    return raw


def test_hello_includes_tts_live2d_flags(voice_m2_client):
    """M2: voice.hello should advertise tts_enabled / live2d_enabled."""
    with voice_m2_client.websocket_connect("/ws/voice") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "voice.hello"
        assert msg["data"]["tts_enabled"] is True
        assert msg["data"]["live2d_enabled"] is True


def test_voice_text_streams_tts_audio(voice_m2_app, voice_m2_client):
    """voice.text → agent → agent.message → tts.audio (binary) → tts.end."""
    _app, _vad, _asr, fake_tts, fake_live2d = voice_m2_app

    with voice_m2_client.websocket_connect("/ws/voice") as ws:
        # hello
        hello = ws.receive_json()
        assert hello["type"] == "voice.hello"

        # send text
        ws.send_text(json.dumps({
            "type": "voice.text",
            "session_id": "m2-test-1",
            "text": "open Safari",
        }))

        # Drain all messages — agent.message, tts.start, then binary
        # chunks (tts.audio), then tts.end. We just want enough text
        # frames to verify the protocol.
        messages = _drain_n_text(10, ws, timeout=2.0)

    types = [m.get("type") for m in messages if isinstance(m, dict)]
    assert "agent.message" in types
    # The agent reply should have its emotion tag stripped
    agent_msg = next(
        m for m in messages
        if isinstance(m, dict) and m.get("type") == "agent.message"
    )
    assert agent_msg["data"]["emotion"] == "focused"
    assert "Agent reply to: open Safari" in agent_msg["data"]["text"]
    assert "[EMO:" not in agent_msg["data"]["text"]  # tag stripped

    # TTS was called
    assert fake_tts.synthesize_calls or fake_tts.stream_calls
    # Live2D was triggered
    assert ("ntd_focused", "lean_in") in fake_live2d.triggers


def test_voice_text_no_responder_still_works(monkeypatch, voice_m2_app):
    """When responder is not configured, agent.message still goes out."""
    voice_ws.set_responder(None)
    _app, _vad, _asr, fake_tts, fake_live2d = voice_m2_app

    with TestClient(_app) as client:
        with client.websocket_connect("/ws/voice") as ws:
            ws.receive_json()  # hello (tts_enabled=False now)
            ws.send_text(json.dumps({
                "type": "voice.text",
                "session_id": "m2-no-tts",
                "text": "ping",
            }))

            messages = _drain_until(
                ws,
                lambda m: isinstance(m, dict)
                and m.get("type") == "agent.message",
                max_messages=10,
                timeout=2.0,
            )

    types = [m.get("type") for m in messages if isinstance(m, dict)]
    assert "agent.message" in types
    # No TTS was called
    assert fake_tts.synthesize_calls == []


def test_voice_text_ping_pong_still_works(voice_m2_client):
    """Control frames still work alongside M2 streaming."""
    with voice_m2_client.websocket_connect("/ws/voice") as ws:
        ws.receive_json()  # hello
        ws.send_text(json.dumps({"type": "ping"}))
        msg = ws.receive_json()
        assert msg["type"] == "pong"

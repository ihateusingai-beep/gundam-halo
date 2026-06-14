"""Tests for the /ws/voice endpoint using FastAPI TestClient.

Verifies the WebSocket protocol:
- hello frame on connect
- voice.begin / audio frames / voice.end cycle
- asr.result and agent.message come back
- voice.text bypass works

We monkey-patch the VAD/ASR factories with fakes so the WS handler
doesn't need real Silero/Whisper models on disk.
"""

from __future__ import annotations

import json

import pytest
from app.api import voice_ws
from app.core import config as _config_module
from app.core.registry import ToolRegistry
from fastapi.testclient import TestClient

from tests.voice.fakes import FakeASR, FakeVAD


@pytest.fixture
def voice_enabled_app(monkeypatch):
    """Build a fresh app with voice enabled + fakes injected.

    We reset ToolRegistry before each app build so the second `create_app`
    call doesn't trip the duplicate-registration guard. We also patch
    the ASR/VAD factories to return fakes.
    """
    from app.main import create_app

    # Inject fakes into the voice factories (patch both the source
    # modules and the names imported in voice_ws)
    fake_vad = FakeVAD()
    fake_asr = FakeASR(default_text="fake-asr-text")

    from app.voice.asr import asr_factory
    from app.voice.vad import vad_factory
    from app.voice.tts import tts_factory
    from app.voice.live2d import live2d_factory
    monkeypatch.setattr(vad_factory, "create_vad", lambda config=None: fake_vad)
    monkeypatch.setattr(asr_factory, "create_asr", lambda config=None: fake_asr)
    # Also patch TTS / Live2D so the default _build_responder()
    # doesn't try to instantiate real Edge TTS in CI. Returning
    # None makes voice_ws skip TTS entirely.
    monkeypatch.setattr(tts_factory, "create_tts", lambda config=None: None)
    monkeypatch.setattr(live2d_factory, "create_live2d", lambda config=None: None)
    # voice_ws imports these via `from app.voice.asr.asr_factory import create_asr`
    # so the bound name lives on voice_ws itself:
    monkeypatch.setattr(voice_ws, "create_vad", lambda config=None: fake_vad)
    monkeypatch.setattr(voice_ws, "create_asr", lambda config=None: fake_asr)
    monkeypatch.setattr(voice_ws, "create_tts", lambda config=None: None)
    monkeypatch.setattr(voice_ws, "create_live2d", lambda config=None: None)

    cfg = _config_module.get_config()
    original = cfg.voice.enabled
    cfg.voice.enabled = True
    # Reset responder so cross-test pollution from voice_m2_app
    # (which sets a FakeTTS responder) doesn't leak in. Also
    # explicitly clear so the default _build_responder doesn't
    # instantiate a real Edge TTS in CI.
    voice_ws.set_responder(None)
    ToolRegistry.clear()  # reset accumulated state from module-level halo_app
    try:
        app = create_app()
        yield app, fake_vad, fake_asr
    finally:
        cfg.voice.enabled = original
        voice_ws.set_agent_callback(None)
        voice_ws.set_responder(None)
        ToolRegistry.clear()


@pytest.fixture
def voice_client(voice_enabled_app):
    """A TestClient bound to a fresh app (voice enabled)."""
    app, _vad, _asr = voice_enabled_app
    return TestClient(app)


def test_voice_status_endpoint(voice_client):
    """GET /voice/status returns the voice config snapshot."""
    resp = voice_client.get("/voice/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["enabled"] is True
    assert data["vad"]["backend"] == "silero"
    assert data["asr"]["backend"] == "whisper_local"


def test_voice_text_bypass_returns_agent_message(voice_client):
    """voice.text frame triggers the agent callback without ASR.
    M15: callback now yields sentence-sized chunks (async iterator).
    """
    from typing import AsyncIterator

    async def fake_agent(sid: str, text: str) -> AsyncIterator[str]:
        # Two sentences — first one is incremental, last is final
        yield f"echo part 1 of: {text}"
        yield f"echo part 2 of: {text}"

    voice_ws.set_agent_callback(fake_agent)

    with voice_client.websocket_connect("/ws/voice") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "voice.hello"

        ws.send_text(json.dumps({
            "type": "voice.text",
            "session_id": "test-1",
            "text": "hello there",
        }))

        # M15 streaming protocol: with responder wired (default
        # _build_responder hits Edge TTS), the server emits
        #   live2d.trigger
        #   tts.start
        #   agent.message (is_final=False)  ← sentence 1
        #   tts.audio (+ binary)
        #   agent.message (is_final=False)  ← sentence 2
        #   tts.audio (+ binary)
        #   agent.message (is_final=True)
        #   tts.end
        #   voice.turn_ended
        # We only assert the agent.message frames (the protocol under
        # test). Other frames (live2d, tts.*) are skipped over.
        agent_messages: list[dict] = []
        for _ in range(8):  # bound the loop
            try:
                msg = ws.receive_json()
            except Exception:
                break
            if msg.get("type") == "agent.message":
                agent_messages.append(msg)
            elif msg.get("type") == "voice.turn_ended":
                break

    assert len(agent_messages) == 3, f"expected 3 agent.message frames, got {len(agent_messages)}: {agent_messages}"
    # First: incremental, single sentence
    assert agent_messages[0]["data"]["text"] == "echo part 1 of: hello there"
    assert agent_messages[0]["data"]["is_final"] is False
    # Second: incremental, accumulated
    assert agent_messages[1]["data"]["text"] == "echo part 1 of: hello there echo part 2 of: hello there"
    assert agent_messages[1]["data"]["is_final"] is False
    # Third: final
    assert agent_messages[2]["data"]["is_final"] is True
    assert agent_messages[2]["data"]["text"] == "echo part 1 of: hello there echo part 2 of: hello there"


def test_voice_text_without_callback_returns_asr_result(voice_client):
    """When no agent callback is set, voice.text echoes as asr.result."""
    voice_ws.set_agent_callback(None)
    with voice_client.websocket_connect("/ws/voice") as ws:
        ws.receive_json()  # hello

        ws.send_text(json.dumps({
            "type": "voice.text",
            "text": "just echo me",
        }))

        msg = ws.receive_json()
        assert msg["type"] == "asr.result"
        assert msg["data"]["text"] == "just echo me"


def test_ping_pong(voice_client):
    with voice_client.websocket_connect("/ws/voice") as ws:
        ws.receive_json()  # hello
        ws.send_text(json.dumps({"type": "ping"}))
        msg = ws.receive_json()
        assert msg["type"] == "pong"


def test_invalid_json_returns_error(voice_client):
    with voice_client.websocket_connect("/ws/voice") as ws:
        ws.receive_json()  # hello
        ws.send_text("not valid json {{{")
        msg = ws.receive_json()
        assert msg["type"] == "voice.error"
        assert msg["data"]["error"] == "invalid_json"


def test_unknown_message_type_returns_error(voice_client):
    with voice_client.websocket_connect("/ws/voice") as ws:
        ws.receive_json()  # hello
        ws.send_text(json.dumps({"type": "nonsense"}))
        msg = ws.receive_json()
        assert msg["type"] == "voice.error"
        assert "unknown_type" in msg["data"]["error"]


def test_voice_end_without_active_turn_returns_error(voice_client):
    with voice_client.websocket_connect("/ws/voice") as ws:
        ws.receive_json()  # hello
        ws.send_text(json.dumps({"type": "voice.end"}))
        msg = ws.receive_json()
        assert msg["type"] == "voice.error"
        assert msg["data"]["error"] == "no_active_turn"

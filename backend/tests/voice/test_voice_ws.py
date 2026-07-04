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
from app.api import voice_ws, ws_protocol
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
    monkeypatch.setattr(ws_protocol, "create_vad", lambda config=None: fake_vad)
    monkeypatch.setattr(ws_protocol, "create_asr", lambda config=None: fake_asr)
    monkeypatch.setattr(ws_protocol, "create_tts", lambda config=None: None)
    monkeypatch.setattr(ws_protocol, "create_live2d", lambda config=None: None)

    cfg = _config_module.get_config()
    original = cfg.voice.enabled
    cfg.voice.enabled = True
    # Reset responder so cross-test pollution from voice_m2_app
    # (which sets a FakeTTS responder) doesn't leak in. Also
    # explicitly clear so the default _build_responder doesn't
    # instantiate a real Edge TTS in CI.
    voice_ws.set_responder(None)
    # NOTE: do NOT clear ToolRegistry here. Sprint 32 P0-1 eagerly
    # imports 22 tools at app.tools.__init__.py import time so the
    # registry is populated with the full default tool set. Clearing
    # it would wipe the 22 eager-imported tools and break downstream
    # tests that rely on `default_tools()` returning the full set
    # (e.g. tests/tools/test_builder.py).
    try:
        app = create_app()
        yield app, fake_vad, fake_asr
    finally:
        cfg.voice.enabled = original
        voice_ws.set_agent_callback(None)
        voice_ws.set_responder(None)
        # NOTE: do NOT clear ToolRegistry here (see comment
        # at the fixture entry).


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
    Sprint 17a: the test now uses a wake phrase so the strict-mode
    default (True) does not discard the turn.
    """
    from typing import AsyncIterator

    async def fake_agent(sid: str, text: str) -> AsyncIterator[str]:
        # Two sentences — first one is incremental, last is final.
        # Sprint 56 R5: the callback contract is `AsyncIterator[str] |
        # None` returned from the awaited callback. We yield in a
        # sync helper and return it, so the outer `await fake_agent`
        # resolves to the async iterator.
        async def _aiter():
            yield f"echo part 1 of: {text}"
            yield f"echo part 2 of: {text}"
        return _aiter()

    voice_ws.set_agent_callback(fake_agent)

    with voice_client.websocket_connect("/ws/voice") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "voice.hello"

        ws.send_text(json.dumps({
            "type": "voice.text",
            "session_id": "test-1",
            "text": "Unicorn, hello there",
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

    # Sprint 17a: the wake-phrase detector strips "Unicorn," from
    # the front, so the agent sees "hello there" (the rest of the
    # phrase). Echo it back so the assertion below matches the
    # stripped form.
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


# ---------------------------------------------------------------------------
# Sprint 17a: strict wake-phrase mode
# ---------------------------------------------------------------------------
#
# The /voice/config endpoint exposes a `strict_wake_phrase` bool
# (default True post-Sprint 17a). When strict mode is on and a
# voice turn's ASR transcript does not start with a recognized
# wake phrase, the server should:
#   - still emit `asr.result` (so the cockpit shows what was heard)
#   - skip the agent invocation entirely
#   - emit `voice.turn_ended` with `discarded: true` and
#     `reason: "no_wake_phrase"`
#
# The matching wake-phrase path (turn is processed normally) is
# covered by the existing test_voice_text_bypass_returns_agent_message
# test (which uses "hello there" — no wake phrase — and only
# passes because strict mode is currently False in CI; we
# explicitly flip it on/off in the new tests below).


def _set_strict(cfg_value: bool) -> None:
    """Helper: flip the global voice config's strict_wake_phrase
    flag in-memory for the duration of a test. The test fixture
    restores the original value on teardown (see voice_enabled_app)."""
    cfg = _config_module.get_config()
    cfg.voice.strict_wake_phrase = cfg_value


def test_voice_text_strict_mode_discards_no_wake(voice_client):
    """Strict mode ON + text without wake phrase → discarded.

    The server should still emit `asr.result` (so the cockpit
    transcript shows the text) and then immediately a
    `voice.turn_ended` with discarded=true and reason
    "no_wake_phrase". NO agent.message frames should follow.
    """
    from typing import AsyncIterator

    agent_invocations: list[tuple[str, str]] = []

    async def should_not_run(sid: str, text: str) -> AsyncIterator[str]:
        agent_invocations.append((sid, text))
        async def _aiter():
            yield f"echo {text}"
        return _aiter()

    voice_ws.set_agent_callback(should_not_run)
    _set_strict(True)
    try:
        with voice_client.websocket_connect("/ws/voice") as ws:
            ws.receive_json()  # hello

            ws.send_text(json.dumps({
                "type": "voice.text",
                "text": "what's the weather in Hong Kong",
            }))

            frames: list[dict] = []
            # Bound the receive loop — strict-discard path is short.
            for _ in range(5):
                msg = ws.receive_json()
                frames.append(msg)
                if msg.get("type") == "voice.turn_ended":
                    break
    finally:
        _set_strict(False)
        voice_ws.set_agent_callback(None)

    # We expect: asr.result (wake_triggered=false) + voice.turn_ended
    # (discarded=true, reason="no_wake_phrase").
    types = [f["type"] for f in frames]
    assert "asr.result" in types, f"missing asr.result in {types}"
    assert "voice.turn_ended" in types, f"missing voice.turn_ended in {types}"
    # And the agent must NOT have been invoked.
    assert agent_invocations == [], (
        f"agent should not be invoked in strict mode without wake, "
        f"but was called with: {agent_invocations}"
    )
    ended = next(f for f in frames if f["type"] == "voice.turn_ended")
    assert ended["data"]["discarded"] is True
    assert ended["data"]["reason"] == "no_wake_phrase"
    # asr.result should report wake_triggered=False.
    asr = next(f for f in frames if f["type"] == "asr.result")
    assert asr["data"]["wake_triggered"] is False


def test_voice_text_strict_mode_allows_wake_phrase(voice_client):
    """Strict mode ON + wake phrase present → agent runs normally."""
    from typing import AsyncIterator

    agent_invocations: list[tuple[str, str]] = []

    async def fake_agent(sid: str, text: str) -> AsyncIterator[str]:
        agent_invocations.append((sid, text))
        async def _aiter():
            yield f"echo: {text}"
        return _aiter()

    voice_ws.set_agent_callback(fake_agent)
    _set_strict(True)
    try:
        with voice_client.websocket_connect("/ws/voice") as ws:
            ws.receive_json()  # hello

            ws.send_text(json.dumps({
                "type": "voice.text",
                "text": "Unicorn, what's the weather",
            }))

            frames: list[dict] = []
            for _ in range(10):
                try:
                    msg = ws.receive_json()
                except Exception:
                    break
                frames.append(msg)
                if msg.get("type") == "voice.turn_ended":
                    break
    finally:
        _set_strict(False)
        voice_ws.set_agent_callback(None)

    # Agent should have been called with the STRIPPED text (no
    # wake phrase prefix), so the LLM sees a clean command.
    assert len(agent_invocations) == 1, (
        f"expected 1 agent invocation, got {len(agent_invocations)}"
    )
    sid, text = agent_invocations[0]
    assert text == "what's the weather", (
        f"expected stripped text, got {text!r}"
    )
    # voice.turn_ended should be discarded=False, reason=None.
    ended = next(f for f in frames if f["type"] == "voice.turn_ended")
    assert ended["data"]["discarded"] is False
    assert ended["data"].get("reason") in (None, "null"), (
        f"expected reason=null, got {ended['data'].get('reason')!r}"
    )


def test_voice_text_strict_off_allows_no_wake(voice_client):
    """Strict mode OFF (permissive) + no wake phrase → agent runs
    (legacy behavior, Sprint 16). The flag defaults to True after
    Sprint 17a, so we explicitly flip it off here."""
    from typing import AsyncIterator

    agent_invocations: list[tuple[str, str]] = []

    async def fake_agent(sid: str, text: str) -> AsyncIterator[str]:
        agent_invocations.append((sid, text))
        async def _aiter():
            yield f"echo: {text}"
        return _aiter()

    voice_ws.set_agent_callback(fake_agent)
    _set_strict(False)
    try:
        with voice_client.websocket_connect("/ws/voice") as ws:
            ws.receive_json()  # hello
            ws.send_text(json.dumps({
                "type": "voice.text",
                "text": "what's the weather in Hong Kong",
            }))
            for _ in range(10):
                try:
                    msg = ws.receive_json()
                except Exception:
                    break
                if msg.get("type") == "voice.turn_ended":
                    break
    finally:
        _set_strict(True)  # restore default
        voice_ws.set_agent_callback(None)

    assert len(agent_invocations) == 1
    assert agent_invocations[0][1] == "what's the weather in Hong Kong"


def test_get_voice_config_includes_strict_flag(voice_client):
    """GET /voice/config returns strict_wake_phrase alongside wake_phrases."""
    _set_strict(True)
    try:
        resp = voice_client.get("/voice/config")
        assert resp.status_code == 200
        data = resp.json()
        assert "wake_phrases" in data
        assert data["strict_wake_phrase"] is True
    finally:
        _set_strict(False)
        resp = voice_client.get("/voice/config")
        assert resp.json()["strict_wake_phrase"] is False


def test_put_voice_config_persists_strict_flag(voice_client, tmp_path):
    """PUT /voice/config accepts strict_wake_phrase and persists it.

    We pass a custom `home` config_path by writing a temp file
    and pointing the config at it. We use the in-memory config
    directly for the round-trip — the toml persistence is
    exercised by the existing Sprint 16 tests for wake_phrases.
    """
    _set_strict(True)
    try:
        resp = voice_client.put("/voice/config", json={
            "wake_phrases": ["Unicorn", "NTD", "gundam", "獨角獸", "高達"],
            "strict_wake_phrase": False,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["strict_wake_phrase"] is False
        assert data["wake_phrases"] == ["Unicorn", "NTD", "gundam", "獨角獸", "高達"]
        assert data["persisted"] is True

        # GET should now reflect the new value.
        get_resp = voice_client.get("/voice/config")
        assert get_resp.json()["strict_wake_phrase"] is False

        # And the missing-field validation rejects the request.
        bad = voice_client.put("/voice/config", json={
            "wake_phrases": ["Unicorn"],
        })
        assert bad.status_code == 400
        assert "strict_wake_phrase" in bad.json()["detail"]
    finally:
        _set_strict(True)  # restore default

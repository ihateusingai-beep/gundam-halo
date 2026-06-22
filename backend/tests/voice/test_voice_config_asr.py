"""Sprint 18 Track B: PUT /voice/config now accepts asr_backend
and asr_corrector, validates them, persists to config.toml, and
flips an in-process restart_required flag.

Tests:
  1. PUT without asr fields (legacy payload) still works
  2. PUT with asr_backend change sets restart_required=True
  3. PUT with asr_corrector change sets restart_required=True
  4. PUT with same asr values doesn't flip restart_required
  5. PUT with invalid asr_backend returns 400
  6. PUT with invalid asr_corrector returns 400
  7. GET /voice/config reflects the restart_required flag
  8. config.toml actually has the new [voice.asr] keys
  9. _voice_restart_required_flag() returns the right value
 10. A non-asr PUT clears any stale restart flag

The `voice_enabled_app` + `voice_client` fixtures are duplicated
from `test_voice_ws.py` rather than imported — pytest doesn't
auto-share fixtures across test modules, and refactoring them
into a conftest.py would touch working 17b code for no benefit
in Sprint 18. The duplication is intentional and isolated to
this file.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from app.api import restart_handler, voice_ws, ws_protocol
from app.core import config as _config_module
from app.core.registry import ToolRegistry
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Fixtures — duplicated from test_voice_ws.py. See module docstring.
# ---------------------------------------------------------------------------

@pytest.fixture
def voice_enabled_app(monkeypatch):
    """Build a fresh app with voice enabled + fakes injected."""
    from app.main import create_app
    from app.voice.asr import asr_factory
    from app.voice.asr.asr_factory import create_asr
    from app.voice.live2d import live2d_factory
    from app.voice.live2d.live2d_factory import create_live2d
    from app.voice.tts import tts_factory
    from app.voice.tts.tts_factory import create_tts
    from app.voice.vad import vad_factory
    from app.voice.vad.vad_factory import create_vad

    from tests.voice.fakes import FakeASR, FakeVAD

    fake_vad = FakeVAD()
    fake_asr = FakeASR(default_text="fake-asr-text")

    monkeypatch.setattr(vad_factory, "create_vad", lambda config=None: fake_vad)
    monkeypatch.setattr(asr_factory, "create_asr", lambda config=None: fake_asr)
    monkeypatch.setattr(tts_factory, "create_tts", lambda config=None: None)
    monkeypatch.setattr(live2d_factory, "create_live2d", lambda config=None: None)
    # ws_protocol imports these by name — patch the bound name on
    # the ws_protocol module too so the in-process create_app
    # uses fakes. (Sprint 32 P1.1 split voice_ws into ws_protocol +
    # voice_config_api + voice_pipeline_handler + restart_handler;
    # the imports now live in ws_protocol.)
    monkeypatch.setattr(ws_protocol, "create_vad", lambda config=None: fake_vad)
    monkeypatch.setattr(ws_protocol, "create_asr", lambda config=None: fake_asr)
    monkeypatch.setattr(ws_protocol, "create_tts", lambda config=None: None)
    monkeypatch.setattr(ws_protocol, "create_live2d", lambda config=None: None)

    cfg = _config_module.get_config()
    original = cfg.voice.enabled
    cfg.voice.enabled = True
    voice_ws.set_responder(None)
    # NOTE: do NOT clear ToolRegistry here. Sprint 32 P0-1 eagerly
    # imports 22 tools at app.tools.__init__.py import time so the
    # registry is populated with the full default tool set. Clearing
    # it would wipe the 22 eager-imported tools and break downstream
    # tests that rely on `default_tools()` returning the full set
    # (e.g. tests/tools/test_builder.py). The `create_vad` /
    # `create_asr` / `create_tts` / `create_live2d` monkeypatches
    # above are sufficient for this test's voice-config contract
    # verification — we don't need a clean ToolRegistry to test
    # PUT /voice/config.
    try:
        app = create_app()
        yield app, fake_vad, fake_asr
    finally:
        cfg.voice.enabled = original
        voice_ws.set_agent_callback(None)
        voice_ws.set_responder(None)


@pytest.fixture
def voice_client(voice_enabled_app):
    """A TestClient bound to a fresh app (voice enabled)."""
    app, _vad, _asr = voice_enabled_app
    return TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _set_asr(backend: str, corrector: str) -> None:
    """Set the in-memory config's asr backend + corrector so the
    next PUT can diff against a known value. Also clears the
    in-process restart_required flag so each test starts clean.

    Note: we intentionally do NOT reset _config to None here.
    The cached in-memory config is what subsequent get_config()
    calls return, and resetting it would force a reload from
    disk on every call. The disk reload would pick up the real
    ~/.gundam-halo/config.toml which may have been mutated by
    an earlier test that wrote there (the [voice.asr] section
    added by test_put_voice_config_persists_asr_to_toml is in
    tmp_path so it doesn't pollute, but if it did, a disk reload
    in a later test would either (a) read the polluted file and
    crash with TOMLDecodeError if it had stale content, or
    (b) silently override the in-memory test state).

    Trade-off: tests share the in-memory config. We re-assert
    the known good values in every test's setup via _set_asr()
    so the diff against the PUT's payload is well-defined.
    """
    cfg = _config_module.get_config()
    cfg.voice.asr.backend = backend
    cfg.voice.asr.corrector = corrector
    restart_handler._voice_restart_required = False


def _reset_home_to_tmp(monkeypatch, tmp_path: Path) -> Path:
    """Point cfg.home at tmp_path so config.toml writes don't
    pollute the real ~/.gundam-halo/config.toml. Returns the
    tmp_path for convenience."""
    cfg = _config_module.get_config()
    monkeypatch.setattr(cfg, "home", tmp_path)
    return tmp_path


def _reset_config_cache() -> None:
    """Force the next get_config() call to reload from disk.

    Call this in finally blocks after writes to tmp_path so a
    later test doesn't accidentally reload the real
    ~/.gundam-halo/config.toml (which may have been mutated by
    a previous test in this process). For Sprint 18 we don't
    write to the real path, but the defense-in-depth is cheap.
    """
    _config_module._config = None


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_put_voice_config_legacy_payload_still_works(voice_client, monkeypatch, tmp_path):
    """A PUT with only the original 17a fields (no asr fields)
    succeeds and returns restart_required=False (we didn't touch
    the asr fields)."""
    cfg = _config_module.get_config()
    cfg.voice.strict_wake_phrase = True
    _set_asr(backend="whisper_local", corrector="bert")
    _reset_home_to_tmp(monkeypatch, tmp_path)
    try:
        resp = voice_client.put("/voice/config", json={
            "wake_phrases": ["Unicorn", "NTD"],
            "strict_wake_phrase": True,
        })
        assert resp.status_code == 200
        data = resp.json()
        # Legacy payload: no asr change → no restart banner.
        assert data["restart_required"] is False
        assert data["asr_backend"] == "whisper_local"
        assert data["asr_corrector"] == "bert"
    finally:
        _set_asr(backend="whisper_local", corrector="bert")


def test_put_voice_config_asr_backend_change_flips_restart(voice_client, monkeypatch, tmp_path):
    """Changing asr_backend from whisper_local → yuesub sets
    restart_required=True in the response and persists to disk."""
    cfg = _config_module.get_config()
    cfg.voice.strict_wake_phrase = True
    _set_asr(backend="whisper_local", corrector="bert")
    _reset_home_to_tmp(monkeypatch, tmp_path)
    try:
        resp = voice_client.put("/voice/config", json={
            "wake_phrases": ["Unicorn"],
            "strict_wake_phrase": True,
            "asr_backend": "yuesub",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["asr_backend"] == "yuesub"
        assert data["restart_required"] is True
        # The flag should also be readable via the helper so the
        # next GET /voice/config returns it.
        assert restart_handler._voice_restart_required_flag() is True
    finally:
        _set_asr(backend="whisper_local", corrector="bert")
        restart_handler._voice_restart_required = False


def test_put_voice_config_asr_corrector_change_flips_restart(voice_client, monkeypatch, tmp_path):
    """Changing asr_corrector from bert → opencc sets
    restart_required=True."""
    cfg = _config_module.get_config()
    cfg.voice.strict_wake_phrase = True
    _set_asr(backend="whisper_local", corrector="bert")
    _reset_home_to_tmp(monkeypatch, tmp_path)
    try:
        resp = voice_client.put("/voice/config", json={
            "wake_phrases": ["Unicorn"],
            "strict_wake_phrase": True,
            "asr_corrector": "opencc",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["asr_corrector"] == "opencc"
        assert data["restart_required"] is True
    finally:
        _set_asr(backend="whisper_local", corrector="bert")
        restart_handler._voice_restart_required = False


def test_put_voice_config_same_asr_value_does_not_flip_restart(voice_client, monkeypatch, tmp_path):
    """Sending asr_backend="yuesub" when the current value is
    already "yuesub" does NOT flip restart_required (no actual
    change happened)."""
    cfg = _config_module.get_config()
    cfg.voice.strict_wake_phrase = True
    _set_asr(backend="yuesub", corrector="opencc")
    _reset_home_to_tmp(monkeypatch, tmp_path)
    try:
        resp = voice_client.put("/voice/config", json={
            "wake_phrases": ["Unicorn"],
            "strict_wake_phrase": True,
            "asr_backend": "yuesub",
            "asr_corrector": "opencc",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["restart_required"] is False
    finally:
        _set_asr(backend="whisper_local", corrector="bert")
        restart_handler._voice_restart_required = False


def test_put_voice_config_invalid_asr_backend_returns_400(voice_client, monkeypatch, tmp_path):
    """An unknown asr_backend value (e.g. "whisper_giant") returns
    a 400 with a clear error message."""
    cfg = _config_module.get_config()
    cfg.voice.strict_wake_phrase = True
    _set_asr(backend="whisper_local", corrector="bert")
    _reset_home_to_tmp(monkeypatch, tmp_path)
    try:
        resp = voice_client.put("/voice/config", json={
            "wake_phrases": ["Unicorn"],
            "strict_wake_phrase": True,
            "asr_backend": "whisper_giant",
        })
        assert resp.status_code == 400
        detail = resp.json()["detail"]
        assert "asr_backend" in detail
        assert "whisper_giant" in detail
    finally:
        _set_asr(backend="whisper_local", corrector="bert")


def test_put_voice_config_invalid_asr_corrector_returns_400(voice_client, monkeypatch, tmp_path):
    """An unknown asr_corrector value returns 400."""
    cfg = _config_module.get_config()
    cfg.voice.strict_wake_phrase = True
    _set_asr(backend="whisper_local", corrector="bert")
    _reset_home_to_tmp(monkeypatch, tmp_path)
    try:
        resp = voice_client.put("/voice/config", json={
            "wake_phrases": ["Unicorn"],
            "strict_wake_phrase": True,
            "asr_corrector": "transformer",  # not a real corrector
        })
        assert resp.status_code == 400
        detail = resp.json()["detail"]
        assert "asr_corrector" in detail
        assert "transformer" in detail
    finally:
        _set_asr(backend="whisper_local", corrector="bert")


def test_put_voice_config_non_string_asr_backend_returns_400(voice_client, monkeypatch, tmp_path):
    """A non-string asr_backend (e.g. a list) returns 400."""
    cfg = _config_module.get_config()
    cfg.voice.strict_wake_phrase = True
    _set_asr(backend="whisper_local", corrector="bert")
    _reset_home_to_tmp(monkeypatch, tmp_path)
    try:
        resp = voice_client.put("/voice/config", json={
            "wake_phrases": ["Unicorn"],
            "strict_wake_phrase": True,
            "asr_backend": ["yuesub"],
        })
        assert resp.status_code == 400
        assert "string" in resp.json()["detail"].lower()
    finally:
        _set_asr(backend="whisper_local", corrector="bert")


def test_get_voice_config_reflects_restart_required_flag(voice_client, monkeypatch, tmp_path):
    """After a PUT that flips restart_required=True, the next
    GET /voice/config returns restart_required=True."""
    cfg = _config_module.get_config()
    cfg.voice.strict_wake_phrase = True
    _set_asr(backend="whisper_local", corrector="bert")
    _reset_home_to_tmp(monkeypatch, tmp_path)
    try:
        # First PUT: change asr_backend → restart_required=true
        resp = voice_client.put("/voice/config", json={
            "wake_phrases": ["Unicorn"],
            "strict_wake_phrase": True,
            "asr_backend": "yuesub",
        })
        assert resp.status_code == 200
        assert resp.json()["restart_required"] is True

        # GET should now report the same flag
        get_resp = voice_client.get("/voice/config")
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["restart_required"] is True
        assert data["asr_backend"] == "yuesub"
    finally:
        _set_asr(backend="whisper_local", corrector="bert")
        restart_handler._voice_restart_required = False


def test_put_voice_config_clears_stale_restart_flag(voice_client, monkeypatch, tmp_path):
    """A PUT that does NOT change asr fields clears any stale
    restart_required flag. The dashboard should not keep nagging
    the user after they restart or change their mind."""
    cfg = _config_module.get_config()
    cfg.voice.strict_wake_phrase = True
    _set_asr(backend="whisper_local", corrector="bert")
    _reset_home_to_tmp(monkeypatch, tmp_path)
    try:
        # 1) Set the flag via an asr change
        restart_handler._voice_restart_required = True
        assert restart_handler._voice_restart_required_flag() is True

        # 2) PUT with no asr fields, same wake_phrases + strict
        resp = voice_client.put("/voice/config", json={
            "wake_phrases": ["Unicorn", "NTD"],
            "strict_wake_phrase": True,
        })
        assert resp.status_code == 200
        # The flag should now be cleared (no asr change in this PUT)
        assert restart_handler._voice_restart_required_flag() is False
        data = resp.json()
        assert data["restart_required"] is False
    finally:
        _set_asr(backend="whisper_local", corrector="bert")
        restart_handler._voice_restart_required = False


def test_put_voice_config_persists_asr_to_toml(voice_client, monkeypatch, tmp_path):
    """A PUT with asr_backend + asr_corrector writes the new
    [voice.asr] section to config.toml on disk."""
    cfg = _config_module.get_config()
    cfg.voice.strict_wake_phrase = True
    _set_asr(backend="whisper_local", corrector="bert")
    _reset_home_to_tmp(monkeypatch, tmp_path)
    config_path = tmp_path / "config.toml"
    try:
        # Seed config.toml with a [voice] section + [voice.asr] section
        # so the replace logic targets the existing block (not the
        # "append new section" branch).
        config_path.write_text(
            "[voice]\n"
            "wake_phrases = [\"Unicorn\"]\n"
            "strict_wake_phrase = true\n"
            "\n"
            "[voice.asr]\n"
            "backend = \"whisper_local\"\n"
            "corrector = \"bert\"\n",
            encoding="utf-8",
        )

        resp = voice_client.put("/voice/config", json={
            "wake_phrases": ["Unicorn"],
            "strict_wake_phrase": True,
            "asr_backend": "yuesub",
            "asr_corrector": "opencc",
        })
        assert resp.status_code == 200
        assert resp.json()["persisted"] is True

        text = config_path.read_text(encoding="utf-8")
        # The [voice.asr] section should now have the new values
        assert 'backend = "yuesub"' in text
        assert 'corrector = "opencc"' in text
        # Old values should be gone
        assert 'backend = "whisper_local"' not in text
        assert 'corrector = "bert"' not in text
        # The unrelated [voice] key should be intact
        assert 'strict_wake_phrase = true' in text
    finally:
        _set_asr(backend="whisper_local", corrector="bert")
        restart_handler._voice_restart_required = False


# ---------------------------------------------------------------------------
# Sprint 19b: auto-restart on ASR change
# ---------------------------------------------------------------------------

def test_put_asr_change_returns_restart_scheduled_true(voice_client, monkeypatch, tmp_path):
    """Sprint 19b: a PUT that flips restart_required=True
    also returns restart_scheduled=True in the response
    and sets the in-process _restart_scheduled flag.
    The schedule_restart() call is a no-op in this test
    because we don't have a running asyncio event loop
    (TestClient is sync). The important behaviors are
    the response field and the flag."""
    from app.core import restart as restart_mod

    cfg = _config_module.get_config()
    cfg.voice.strict_wake_phrase = True
    _set_asr(backend="whisper_local", corrector="bert")
    _reset_home_to_tmp(monkeypatch, tmp_path)
    try:
        # Clear the restart flag before the test
        restart_mod._set_restart_scheduled(False, reason="test_setup")
        assert restart_mod.is_restart_scheduled() is False

        resp = voice_client.put("/voice/config", json={
            "wake_phrases": ["Unicorn"],
            "strict_wake_phrase": True,
            "asr_backend": "yuesub",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["restart_required"] is True
        # The response also includes restart_scheduled
        assert data["restart_scheduled"] is True
        # And the in-process flag is set
        assert restart_mod.is_restart_scheduled() is True
    finally:
        _set_asr(backend="whisper_local", corrector="bert")
        restart_handler._voice_restart_required = False
        restart_mod._set_restart_scheduled(False, reason="test_cleanup")


def test_put_wake_phrases_only_returns_restart_scheduled_false(voice_client, monkeypatch, tmp_path):
    """Sprint 19b: a PUT that doesn't change asr fields
    (e.g. just updates wake_phrases) returns
    restart_scheduled=False and clears any pending
    restart flag."""
    from app.core import restart as restart_mod

    cfg = _config_module.get_config()
    cfg.voice.strict_wake_phrase = True
    _set_asr(backend="whisper_local", corrector="bert")
    _reset_home_to_tmp(monkeypatch, tmp_path)
    try:
        # Simulate a stale restart flag from a previous test
        restart_mod._set_restart_scheduled(True, reason="stale_sim")
        assert restart_mod.is_restart_scheduled() is True

        resp = voice_client.put("/voice/config", json={
            "wake_phrases": ["Unicorn", "NTD"],
            "strict_wake_phrase": True,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["restart_required"] is False
        assert data["restart_scheduled"] is False
        # Stale flag is cleared
        assert restart_mod.is_restart_scheduled() is False
    finally:
        _set_asr(backend="whisper_local", corrector="bert")
        restart_handler._voice_restart_required = False
        restart_mod._set_restart_scheduled(False, reason="test_cleanup")


def test_schedule_restart_module_is_importable_and_handles_no_loop(caplog):
    """Sprint 19b: schedule_restart() can be called
    without a running event loop (e.g. in a sync
    context). The function logs a warning instead of
    raising — the PUT response will still report
    restart_scheduled=true so the user can manually
    restart if the in-process exec isn't available."""
    import logging
    from app.core import restart as restart_mod

    # Make sure no loop is running in this test
    try:
        import asyncio
        asyncio.get_running_loop()
        pytest.skip("a running event loop is already attached")
    except RuntimeError:
        pass

    restart_mod._set_restart_scheduled(False, reason="test_setup")
    with caplog.at_level(logging.WARNING, logger="app.core.restart"):
        # Should not raise even without a running loop
        restart_mod.schedule_restart(delay_s=0.1, reason="test")
    assert any(
        "no running asyncio loop" in record.message
        for record in caplog.records
    ), f"expected warning, got: {[r.message for r in caplog.records]}"
    # In the no-loop path, the flag is set BEFORE the
    # schedule_restart call (by the caller in
    # put_voice_config), so the flag here stays False
    # because schedule_restart only sets it via
    # _set_restart_scheduled in the running-loop path.
    # The caller in voice_ws.py is the one that flips
    # the flag, not schedule_restart itself.
    assert restart_mod.is_restart_scheduled() is False
    # Cleanup
    restart_mod._set_restart_scheduled(False, reason="test_cleanup")


# ---------------------------------------------------------------------------
# Sprint 19c: always_on_mic runtime-tunable
# ---------------------------------------------------------------------------


def test_put_voice_config_persists_always_on_mic(voice_client, monkeypatch, tmp_path):
    """Sprint 19c: PUT with always_on_mic=true writes
    the value to config.toml and the GET response
    reflects it. The field is runtime-tunable (no
    restart_required flip)."""
    cfg = _config_module.get_config()
    cfg.voice.strict_wake_phrase = True
    cfg.voice.always_on_mic = False
    _reset_home_to_tmp(monkeypatch, tmp_path)
    config_path = tmp_path / "config.toml"
    try:
        # Seed config.toml with a [voice] section so the
        # strict_wake_phrase / always_on_mic sub matches
        # target the existing block.
        config_path.write_text(
            "[voice]\n"
            "wake_phrases = [\"Unicorn\"]\n"
            "strict_wake_phrase = true\n",
            encoding="utf-8",
        )

        resp = voice_client.put("/voice/config", json={
            "wake_phrases": ["Unicorn"],
            "strict_wake_phrase": True,
            "always_on_mic": True,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["always_on_mic"] is True
        # always_on_mic is runtime-tunable — no restart
        assert data["restart_required"] is False
        assert data["restart_scheduled"] is False
        assert data["persisted"] is True

        # GET reflects the new value
        get_resp = voice_client.get("/voice/config")
        assert get_resp.json()["always_on_mic"] is True

        # config.toml has the new line
        text = config_path.read_text(encoding="utf-8")
        assert "always_on_mic = true" in text
    finally:
        cfg.voice.always_on_mic = False


def test_put_voice_config_always_on_mic_validation(voice_client, monkeypatch, tmp_path):
    """Sprint 19c: a non-bool always_on_mic value
    returns 400. The dashboard's radio group is
    controlled, but a hand-crafted PUT could send
    anything — we validate before applying."""
    cfg = _config_module.get_config()
    cfg.voice.strict_wake_phrase = True
    _reset_home_to_tmp(monkeypatch, tmp_path)
    try:
        resp = voice_client.put("/voice/config", json={
            "wake_phrases": ["Unicorn"],
            "strict_wake_phrase": True,
            "always_on_mic": "yes",  # not a bool
        })
        assert resp.status_code == 400
        assert "always_on_mic" in resp.json()["detail"]
    finally:
        cfg.voice.always_on_mic = False


def test_get_voice_config_includes_always_on_mic(voice_client):
    """Sprint 19c: the GET /voice/config response
    includes the always_on_mic field so the dashboard
    can hydrate its radio on mount."""
    cfg = _config_module.get_config()
    cfg.voice.always_on_mic = True
    try:
        resp = voice_client.get("/voice/config")
        assert resp.status_code == 200
        assert "always_on_mic" in resp.json()
        assert resp.json()["always_on_mic"] is True
    finally:
        cfg.voice.always_on_mic = False

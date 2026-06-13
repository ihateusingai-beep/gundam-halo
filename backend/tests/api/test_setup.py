"""Tests for the M13 setup wizard API (11 endpoints + boot detection).

Covers:
- GET  /api/setup/state     — boot detection
- POST /api/setup/start     — begin wizard
- POST /api/setup/llm       — paste key, secrets_store write, test LLM
- POST /api/setup/voice-asr — model path validation
- POST /api/setup/voice-tts — voice + rate
- POST /api/setup/theme     — 8 themes enum
- POST /api/setup/tailscale — hostname + reachability
- POST /api/setup/smoke     — text + voice round-trip
- POST /api/setup/finish    — mark finished
- POST /api/setup/skip      — mark skipped, config still minimal
- POST /api/setup/reset     — wipe state, leave config

Security assertions (per M13 §"Backend TOML write strategy"):
- secrets_store receives the raw API key (so .env gets it)
- TOML is updated to reference the env var NAME, never the raw key
- Response payload never echoes the raw key
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
import respx
import tomlkit
from app.core import config as config_mod
from app.core.secrets_store import SECRET_KEYS, get_secret_store, reset_secret_store
from app.core.setup_state import ALLOWED_THEMES
from app.main import create_app
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def halo_home(tmp_path: Path) -> Path:
    """Per-test HALO_HOME. The conftest.py autouse fixture already
    points HALO_HOME at tmp_path."""
    return tmp_path


@pytest.fixture(autouse=True)
def _isolate_secrets():
    """Wipe managed secrets before and after each test for isolation."""
    leaked = []
    for k in SECRET_KEYS:
        if k in os.environ:
            leaked.append(k)
            del os.environ[k]
    yield
    for k in SECRET_KEYS:
        os.environ.pop(k, None)
    reset_secret_store()


@pytest.fixture
def client(halo_home: Path):
    """TestClient with fresh app + secrets store + config."""
    reset_secret_store()
    config_mod._config = None
    os.environ["HALO_HOME"] = str(halo_home)
    app = create_app()
    with TestClient(app) as c:
        yield c
    reset_secret_store()
    config_mod._config = None


# LLM models endpoint used by the setup/llm test_connection
MOCK_MODELS_URL = "https://api.minimax.io/v1/models"
MOCK_CHAT_URL = "https://api.minimax.io/v1/chat/completions"


# ---------------------------------------------------------------------------
# GET /api/setup/state — boot detection
# ---------------------------------------------------------------------------


class TestSetupStateEndpoint:
    def test_state_on_fresh_clone(self, client, halo_home):
        """Fresh HALO_HOME (no config.toml) → needs_setup, step 1."""
        r = client.get("/api/setup/state")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "needs_setup"
        assert data["current_step"] == 1
        assert data["completed_steps"] == []
        assert "no config.toml" in data["reason"]

    def test_state_reflects_persisted_finished(self, client, halo_home, monkeypatch):
        """If the user has finished AND config is valid, state shows ready."""
        state_path = halo_home / "setup_state.json"
        state_path.write_text(json.dumps({
            "version": 1,
            "status": "ready",
            "current_step": 7,
            "completed_steps": [1, 2, 3, 4, 5, 6, 7],
            "finished_at": "2026-06-13T10:00:00+00:00",
            "skipped": False,
            "reason": "wizard finished",
        }))
        # Also need a real config that passes detection
        cfg_path = halo_home / "config.toml"
        with open(cfg_path, "w", encoding="utf-8") as f:
            tomlkit.dump(
                {
                    "user": {"default_theme": "gundam-ntd"},
                    "llm": {
                        "provider": "minimax",
                        "api_key_env": "MINIMAX_API_KEY",
                        "base_url": "https://api.minimax.io/v1",
                        "default_model": "MiniMax-M2",
                    },
                    "server": {"require_tailscale": False},
                    "voice": {
                        "enabled": True,
                        "asr": {"model_size": "base"},
                        "tts": {"voice": "zh-HK-HiuMaanNeural"},
                    },
                },
                f,
            )
        monkeypatch.setenv("MINIMAX_API_KEY", "sk-test")
        r = client.get("/api/setup/state")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ready"
        assert data["current_step"] == 7

    def test_state_detected_overrides_persisted(self, client, halo_home):
        """If persisted says ready but live config is missing LLM,
        detection wins (current_step becomes 2)."""
        # Persisted state says ready
        (halo_home / "setup_state.json").write_text(json.dumps({
            "version": 1,
            "status": "ready",
            "current_step": 7,
        }))
        # But live config has no LLM key (and we wipe env)
        cfg_path = halo_home / "config.toml"
        with open(cfg_path, "w", encoding="utf-8") as f:
            tomlkit.dump(
                {
                    "user": {"name": "Test", "default_theme": "gundam-ntd"},
                    "llm": {"provider": "minimax", "api_key_env": "MINIMAX_API_KEY"},
                    "voice": {"enabled": False},
                    "server": {"require_tailscale": False},
                },
                f,
            )
        os.environ.pop("MINIMAX_API_KEY", None)
        r = client.get("/api/setup/state")
        data = r.json()
        assert data["status"] == "needs_setup"
        assert data["current_step"] == 2  # LLM step

    def test_state_with_voice_on_but_no_asr_returns_step_3(
        self, client, halo_home, monkeypatch
    ):
        """Voice is required (per Q3) — ASR missing → step 3."""
        cfg_path = halo_home / "config.toml"
        with open(cfg_path, "w", encoding="utf-8") as f:
            tomlkit.dump(
                {
                    "user": {"name": "Test", "default_theme": "gundam-ntd"},
                    "llm": {
                        "provider": "minimax",
                        "api_key_env": "MINIMAX_API_KEY",
                        "base_url": "https://api.minimax.io/v1",
                        "default_model": "MiniMax-M2",
                    },
                    "server": {"require_tailscale": False},
                    "voice": {
                        "enabled": True,
                        "asr": {"model_size": "", "model_path": ""},
                        "tts": {"voice": "zh-HK-HiuMaanNeural"},
                    },
                },
                f,
            )
        monkeypatch.setenv("MINIMAX_API_KEY", "sk-test")
        r = client.get("/api/setup/state")
        data = r.json()
        assert data["status"] == "needs_setup"
        assert data["current_step"] == 3


# ---------------------------------------------------------------------------
# POST /api/setup/start
# ---------------------------------------------------------------------------


class TestSetupStart:
    def test_start_sets_started_at(self, client, halo_home):
        r = client.post("/api/setup/start")
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["current_step"] == 1
        assert data["completed_steps"] == []
        assert data["started_at"] is not None
        # State file was written
        assert (halo_home / "setup_state.json").exists()


# ---------------------------------------------------------------------------
# POST /api/setup/llm
# ---------------------------------------------------------------------------


class TestSetupLLM:
    RAW_KEY = "sk-supersecret-key-for-testing-12345"

    def _post_llm(self, client, **overrides):
        body = {
            "provider": "minimax",
            "api_key": self.RAW_KEY,
            "base_url": "https://api.minimax.io/v1",
            "default_model": "MiniMax-M2",
            "fallback_model": "MiniMax-M2",
        }
        body.update(overrides)
        return client.post("/api/setup/llm", json=body)

    @respx.mock
    def test_llm_step_success_writes_secrets_and_toml(
        self, client, halo_home
    ):
        """Happy path: 200 from /v1/models → key in secrets_store,
        TOML updated with env-var name, state advances to step 3."""
        respx.get(MOCK_MODELS_URL).mock(
            return_value=httpx.Response(
                200, json={"data": [{"id": "MiniMax-M2"}]}
            )
        )
        r = self._post_llm(client)
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["next_step"] == 3
        assert data["completed_steps"] == [2]
        assert data["stored_env"] == "MINIMAX_API_KEY"

        # 1. Raw key is in secrets_store (os.environ + .env)
        store = get_secret_store()
        assert store.get("MINIMAX_API_KEY") == self.RAW_KEY
        env_text = (halo_home / ".env").read_text()
        assert self.RAW_KEY in env_text

        # 2. TOML has api_key_env, NOT the raw key
        toml_text = (halo_home / "config.toml").read_text()
        assert "api_key_env" in toml_text
        assert "MINIMAX_API_KEY" in toml_text
        # Grep for the raw key — must not appear
        assert self.RAW_KEY not in toml_text

        # 3. State file advanced
        state = json.loads((halo_home / "setup_state.json").read_text())
        assert state["current_step"] == 3
        assert 2 in state["completed_steps"]

    @respx.mock
    def test_llm_step_response_never_echoes_raw_key(self, client, halo_home):
        """The response payload must NOT include the raw API key."""
        respx.get(MOCK_MODELS_URL).mock(
            return_value=httpx.Response(200, json={"data": []})
        )
        r = self._post_llm(client)
        body_text = r.text
        assert self.RAW_KEY not in body_text

    @respx.mock
    def test_llm_step_401_returns_invalid_key_error(self, client, halo_home):
        """401 from provider → error response, no secrets write, no TOML write."""
        respx.get(MOCK_MODELS_URL).mock(
            return_value=httpx.Response(401, text="Unauthorized")
        )
        r = self._post_llm(client)
        data = r.json()
        assert data["ok"] is False
        assert data["errors"][0]["field"] == "api_key"
        assert data["errors"][0]["code"] == "invalid_key"

        # No secrets written
        store = get_secret_store()
        assert not store.is_configured("MINIMAX_API_KEY")
        # No config.toml created
        assert not (halo_home / "config.toml").exists()

    @respx.mock
    def test_llm_step_404_falls_back_to_chat_completions(
        self, client, halo_home
    ):
        """Some providers 404 on /v1/models — wizard should fall back
        to a 1-token chat completion."""
        respx.get(MOCK_MODELS_URL).mock(
            return_value=httpx.Response(404, text="not found")
        )
        respx.post(MOCK_CHAT_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "choices": [
                        {"message": {"role": "assistant", "content": "PONG"}}
                    ]
                },
            )
        )
        r = self._post_llm(client)
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        # Raw key landed in secrets_store
        assert get_secret_store().get("MINIMAX_API_KEY") == self.RAW_KEY

    @respx.mock
    def test_llm_step_timeout_returns_timeout_error(self, client, halo_home):
        """Provider unreachable / timeout → clear error code."""
        respx.get(MOCK_MODELS_URL).mock(
            side_effect=httpx.TimeoutException("timed out")
        )
        r = self._post_llm(client)
        data = r.json()
        assert data["ok"] is False
        assert data["errors"][0]["code"] == "timeout"

    def test_llm_step_rejects_unknown_provider(self, client, halo_home):
        """provider=unknown → 422 from pydantic validator."""
        r = self._post_llm(client, provider="bogus-llm")
        assert r.status_code == 422

    def test_llm_step_rejects_empty_key(self, client, halo_home):
        """Empty api_key → 422 from pydantic."""
        r = self._post_llm(client, api_key="")
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# POST /api/setup/voice-asr
# ---------------------------------------------------------------------------


class TestSetupVoiceASR:
    def test_voice_asr_step_writes_voice_section(self, client, halo_home):
        """Step 3 writes [voice.asr] and flips voice.enabled=true."""
        r = client.post(
            "/api/setup/voice-asr",
            json={
                "backend": "whisper_local",
                "model_size": "base",
                "model_path": "",
                "language": "auto",
                "device": "auto",
                "compute_type": "auto",
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["next_step"] == 4
        assert 3 in data["completed_steps"]

        # TOML was written
        toml_text = (halo_home / "config.toml").read_text()
        assert "[voice.asr]" in toml_text or "voice" in toml_text
        assert "whisper_local" in toml_text
        assert "enabled = true" in toml_text or "enabled=true" in toml_text

    def test_voice_asr_validates_explicit_model_path_exists(
        self, client, halo_home
    ):
        """If model_path is set, the directory must exist."""
        r = client.post(
            "/api/setup/voice-asr",
            json={
                "backend": "whisper_local",
                "model_size": "base",
                "model_path": "/nonexistent/path/that/should/not/exist",
            },
        )
        data = r.json()
        assert data["ok"] is False
        assert data["errors"][0]["field"] == "model_path"
        assert data["errors"][0]["code"] == "model_invalid"

    def test_voice_asr_accepts_real_model_path(self, client, halo_home, tmp_path):
        """A real existing directory is accepted."""
        # Create a real directory
        model_dir = tmp_path / "whisper-yue-base"
        model_dir.mkdir()
        r = client.post(
            "/api/setup/voice-asr",
            json={
                "backend": "whisper_local",
                "model_size": "base",
                "model_path": str(model_dir),
            },
        )
        data = r.json()
        assert data["ok"] is True

    def test_voice_asr_rejects_unknown_backend(self, client, halo_home):
        r = client.post(
            "/api/setup/voice-asr",
            json={"backend": "bogus-backend", "model_size": "base"},
        )
        assert r.status_code == 422

    def test_voice_asr_rejects_unknown_model_size(self, client, halo_home):
        r = client.post(
            "/api/setup/voice-asr",
            json={"backend": "whisper_local", "model_size": "bogus"},
        )
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# POST /api/setup/voice-tts
# ---------------------------------------------------------------------------


class TestSetupVoiceTTS:
    def test_voice_tts_step_writes_tts_section(self, client, halo_home):
        r = client.post(
            "/api/setup/voice-tts",
            json={
                "backend": "edge",
                "voice": "zh-HK-HiuMaanNeural",
                "rate": "+5%",
                "pitch": "+0Hz",
                "volume": "+0%",
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["next_step"] == 5

        toml_text = (halo_home / "config.toml").read_text()
        assert "zh-HK-HiuMaanNeural" in toml_text

    def test_voice_tts_rejects_empty_voice(self, client, halo_home):
        r = client.post(
            "/api/setup/voice-tts",
            json={"backend": "edge", "voice": ""},
        )
        data = r.json()
        assert data["ok"] is False
        assert data["errors"][0]["field"] == "voice"

    def test_voice_tts_rejects_unknown_backend(self, client, halo_home):
        r = client.post(
            "/api/setup/voice-tts",
            json={"backend": "bogus-tts", "voice": "x"},
        )
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# POST /api/setup/theme
# ---------------------------------------------------------------------------


class TestSetupTheme:
    def test_theme_step_writes_user_default_theme(self, client, halo_home):
        r = client.post("/api/setup/theme", json={"theme": "gundam-god"})
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["next_step"] == 6

        toml_text = (halo_home / "config.toml").read_text()
        assert "gundam-god" in toml_text
        assert "[user]" in toml_text

    def test_theme_step_rejects_unknown_theme(self, client, halo_home):
        """Only the 8 ALLOWED_THEMES are valid."""
        r = client.post(
            "/api/setup/theme", json={"theme": "gundam-not-real"}
        )
        assert r.status_code == 422

    def test_theme_step_accepts_all_8_themes(self, client, halo_home):
        """All 8 frontend theme IDs should pass validation."""
        for theme in ALLOWED_THEMES:
            r = client.post("/api/setup/theme", json={"theme": theme})
            assert r.status_code == 200, f"theme {theme!r} should be valid"


# ---------------------------------------------------------------------------
# POST /api/setup/tailscale
# ---------------------------------------------------------------------------


class TestSetupTailscale:
    def test_tailscale_step_writes_server_section(self, client, halo_home):
        with patch(
            "app.api.setup.is_tailscale_reachable", return_value=True
        ):
            r = client.post(
                "/api/setup/tailscale",
                json={"hostname": "gundam-halo", "require_tailscale": True},
            )
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["next_step"] == 7
        assert data["reachable"] is True

        toml_text = (halo_home / "config.toml").read_text()
        assert "gundam-halo" in toml_text
        assert "require_tailscale" in toml_text

    def test_tailscale_step_surfaces_unreachable(self, client, halo_home):
        """If ping fails, response includes reachable=False (no error)."""
        with patch(
            "app.api.setup.is_tailscale_reachable", return_value=False
        ):
            r = client.post(
                "/api/setup/tailscale",
                json={"hostname": "gundam-halo", "require_tailscale": False},
            )
        data = r.json()
        assert data["ok"] is True
        assert data["reachable"] is False


# ---------------------------------------------------------------------------
# POST /api/setup/smoke
# ---------------------------------------------------------------------------


class TestSetupSmoke:
    MOCK_CHAT_URL = "https://api.minimax.io/v1/chat/completions"

    def test_smoke_step_success(self, client, halo_home, monkeypatch):
        """Both text + voice checks pass → ok=True."""
        # Pre-seed config to a "ready" state
        cfg_path = halo_home / "config.toml"
        with open(cfg_path, "w", encoding="utf-8") as f:
            tomlkit.dump(
                {
                    "user": {"name": "T", "default_theme": "gundam-ntd"},
                    "llm": {
                        "provider": "minimax",
                        "api_key_env": "MINIMAX_API_KEY",
                        "base_url": "https://api.minimax.io/v1",
                        "default_model": "MiniMax-M2",
                    },
                    "server": {"require_tailscale": False},
                    "voice": {
                        "enabled": True,
                        "asr": {"model_size": "base", "model_path": ""},
                        "tts": {"voice": "zh-HK-HiuMaanNeural"},
                    },
                },
                f,
            )
        monkeypatch.setenv("MINIMAX_API_KEY", "sk-test")

        with respx.mock:
            respx.post(self.MOCK_CHAT_URL).mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "choices": [
                            {"message": {"role": "assistant", "content": "PONG"}}
                        ]
                    },
                )
            )
            r = client.post("/api/setup/smoke")
        data = r.json()
        assert data["ok"] is True
        assert data["text_ok"] is True
        assert data["voice_ok"] is True
        assert data["text_error"] is None
        assert data["voice_error"] is None

    def test_smoke_step_text_failure_surfaces_error(
        self, client, halo_home, monkeypatch
    ):
        """If text chat returns 401, smoke surfaces the error code."""
        cfg_path = halo_home / "config.toml"
        with open(cfg_path, "w", encoding="utf-8") as f:
            tomlkit.dump(
                {
                    "user": {"name": "T", "default_theme": "gundam-ntd"},
                    "llm": {
                        "provider": "minimax",
                        "api_key_env": "MINIMAX_API_KEY",
                        "base_url": "https://api.minimax.io/v1",
                        "default_model": "MiniMax-M2",
                    },
                    "server": {"require_tailscale": False},
                    "voice": {
                        "enabled": True,
                        "asr": {"model_size": "base"},
                        "tts": {"voice": "x"},
                    },
                },
                f,
            )
        monkeypatch.setenv("MINIMAX_API_KEY", "sk-test")
        with respx.mock:
            respx.post(self.MOCK_CHAT_URL).mock(
                return_value=httpx.Response(401, text="unauthorized")
            )
            r = client.post("/api/setup/smoke")
        data = r.json()
        assert data["ok"] is False
        assert data["text_ok"] is False
        assert data["text_error"] == "http_401"

    def test_smoke_step_voice_disabled_reports_voice_error(
        self, client, halo_home, monkeypatch
    ):
        """Voice disabled in config → voice check fails with voice_disabled."""
        cfg_path = halo_home / "config.toml"
        with open(cfg_path, "w", encoding="utf-8") as f:
            tomlkit.dump(
                {
                    "user": {"name": "T", "default_theme": "gundam-ntd"},
                    "llm": {
                        "provider": "minimax",
                        "api_key_env": "MINIMAX_API_KEY",
                        "base_url": "https://api.minimax.io/v1",
                        "default_model": "MiniMax-M2",
                    },
                    "server": {"require_tailscale": False},
                    "voice": {"enabled": False},
                },
                f,
            )
        monkeypatch.setenv("MINIMAX_API_KEY", "sk-test")
        with respx.mock:
            respx.post(self.MOCK_CHAT_URL).mock(
                return_value=httpx.Response(
                    200,
                    json={"choices": [{"message": {"content": "PONG"}}]},
                )
            )
            r = client.post("/api/setup/smoke")
        data = r.json()
        assert data["ok"] is False
        assert data["voice_ok"] is False
        assert data["voice_error"] == "voice_disabled"


# ---------------------------------------------------------------------------
# POST /api/setup/finish
# ---------------------------------------------------------------------------


class TestSetupFinish:
    def test_finish_blocked_when_incomplete(self, client, halo_home, monkeypatch):
        """If config doesn't pass compute_setup_state(), finish is blocked."""
        cfg_path = halo_home / "config.toml"
        with open(cfg_path, "w", encoding="utf-8") as f:
            tomlkit.dump(
                {
                    "user": {"default_theme": "gundam-ntd"},
                    "llm": {
                        "provider": "minimax",
                        "api_key_env": "MINIMAX_API_KEY",
                        "base_url": "https://api.minimax.io/v1",
                        "default_model": "MiniMax-M2",
                    },
                    "server": {"require_tailscale": False},
                    "voice": {"enabled": False},  # voice off → not ready
                },
                f,
            )
        os.environ.pop("MINIMAX_API_KEY", None)
        r = client.post("/api/setup/finish")
        data = r.json()
        assert data["ok"] is False
        assert data["errors"][0]["code"] == "incomplete"

    def test_finish_success_marks_state_ready(self, client, halo_home, monkeypatch):
        """If config is fully populated, finish marks the wizard done."""
        cfg_path = halo_home / "config.toml"
        with open(cfg_path, "w", encoding="utf-8") as f:
            tomlkit.dump(
                {
                    "user": {"default_theme": "gundam-ntd"},
                    "llm": {
                        "provider": "minimax",
                        "api_key_env": "MINIMAX_API_KEY",
                        "base_url": "https://api.minimax.io/v1",
                        "default_model": "MiniMax-M2",
                    },
                    "server": {"require_tailscale": False},
                    "voice": {
                        "enabled": True,
                        "asr": {"model_size": "base"},
                        "tts": {"voice": "zh-HK-HiuMaanNeural"},
                    },
                },
                f,
            )
        monkeypatch.setenv("MINIMAX_API_KEY", "sk-test")
        r = client.post("/api/setup/finish")
        data = r.json()
        assert data["ok"] is True
        assert data["redirect"] == "/"
        assert data["status"] == "ready"
        assert data["finished_at"] is not None
        assert 7 in data["completed_steps"]


# ---------------------------------------------------------------------------
# POST /api/setup/skip
# ---------------------------------------------------------------------------


class TestSetupSkip:
    def test_skip_writes_minimal_config(self, client, halo_home):
        """On a fresh install, skip creates a config.toml so the
        backend can start (with sensible defaults)."""
        r = client.post("/api/setup/skip")
        data = r.json()
        assert data["ok"] is True
        assert data["redirect"] == "/"
        assert data["skipped"] is True

        # A config.toml exists now
        cfg_path = halo_home / "config.toml"
        assert cfg_path.exists()
        with open(cfg_path, encoding="utf-8") as f:
            cfg = tomlkit.load(f)
        assert "llm" in cfg
        assert cfg["llm"]["api_key_env"] == "MINIMAX_API_KEY"
        assert cfg["voice"]["enabled"] is False

    def test_skip_state_remains_needs_setup(self, client, halo_home):
        """Per M13 Q1, skip does NOT reach 'ready'. The dashboard
        will still show missing-fields warnings."""
        r = client.post("/api/setup/skip")
        data = r.json()
        # skipped=True + status=needs_setup
        assert data["skipped"] is True
        assert data["status"] == "needs_setup"
        # Reason explains why
        assert "skipped" in data["reason"].lower()

    def test_skip_does_not_overwrite_existing_config(self, client, halo_home):
        """If config.toml already exists, skip leaves it alone."""
        cfg_path = halo_home / "config.toml"
        with open(cfg_path, "w", encoding="utf-8") as f:
            tomlkit.dump(
                {"llm": {"provider": "openai"}},  # Note: openai, not minimax
                f,
            )
        client.post("/api/setup/skip")
        # Config still has the user's existing provider choice
        with open(cfg_path, encoding="utf-8") as f:
            cfg = tomlkit.load(f)
        assert cfg["llm"]["provider"] == "openai"


# ---------------------------------------------------------------------------
# POST /api/setup/reset
# ---------------------------------------------------------------------------


class TestSetupReset:
    def test_reset_wipes_state_but_preserves_config(self, client, halo_home):
        """Reset clears setup_state.json but config.toml stays intact."""
        # First, write both files
        cfg_path = halo_home / "config.toml"
        with open(cfg_path, "w", encoding="utf-8") as f:
            tomlkit.dump(
                {"llm": {"provider": "minimax", "api_key_env": "MINIMAX_API_KEY"}},
                f,
            )
        state_path = halo_home / "setup_state.json"
        state_path.write_text(json.dumps({
            "version": 1,
            "status": "ready",
            "current_step": 7,
            "completed_steps": [1, 2, 3, 4, 5, 6, 7],
        }))

        r = client.post("/api/setup/reset")
        data = r.json()
        assert data["ok"] is True
        assert data["current_step"] == 1
        assert data["status"] == "needs_setup"
        # The state file now has the fresh default (still exists, but
        # the wizard restarts at step 1)
        assert state_path.exists()
        new_state = json.loads(state_path.read_text())
        assert new_state["status"] == "needs_setup"
        assert new_state["current_step"] == 1
        assert new_state["completed_steps"] == []
        # Config is still here
        assert cfg_path.exists()


# ---------------------------------------------------------------------------
# Cross-cutting security assertions
# ---------------------------------------------------------------------------


class TestTOMLSecurity:
    """The whole point of the wizard: raw API keys NEVER end up in TOML."""

    RAW_KEY = "sk-test-very-secret-key-1234567890"

    @respx.mock
    def test_raw_key_never_in_toml_after_llm_step(self, client, halo_home):
        """Run the full LLM step and assert the raw key is NOT in TOML
        under any section (grep)."""
        respx.get(MOCK_MODELS_URL).mock(
            return_value=httpx.Response(200, json={"data": []})
        )
        r = client.post(
            "/api/setup/llm",
            json={
                "provider": "minimax",
                "api_key": self.RAW_KEY,
                "base_url": "https://api.minimax.io/v1",
                "default_model": "MiniMax-M2",
            },
        )
        assert r.status_code == 200

        # The TOML must NOT contain the raw key, nor any "sk-" prefix
        toml_text = (halo_home / "config.toml").read_text()
        assert self.RAW_KEY not in toml_text
        # And no "sk-" prefix substring anywhere
        assert "sk-" not in toml_text, (
            f"raw key prefix 'sk-' found in TOML:\n{toml_text}"
        )
        # The env var name is referenced, not the key
        assert "api_key_env" in toml_text
        assert "MINIMAX_API_KEY" in toml_text

    @respx.mock
    def test_raw_key_only_in_secrets_store_after_llm_step(
        self, client, halo_home
    ):
        """The raw key should live in .env (SecretStore) and nowhere else."""
        respx.get(MOCK_MODELS_URL).mock(
            return_value=httpx.Response(200, json={"data": []})
        )
        client.post(
            "/api/setup/llm",
            json={
                "provider": "minimax",
                "api_key": self.RAW_KEY,
                "base_url": "https://api.minimax.io/v1",
                "default_model": "MiniMax-M2",
            },
        )

        # 1. In secrets_store (os.environ)
        assert os.environ.get("MINIMAX_API_KEY") == self.RAW_KEY

        # 2. In .env file
        env_text = (halo_home / ".env").read_text()
        assert self.RAW_KEY in env_text
        assert "MINIMAX_API_KEY" in env_text

        # 3. NOT in TOML
        toml_text = (halo_home / "config.toml").read_text()
        assert self.RAW_KEY not in toml_text

        # 4. NOT in state file
        if (halo_home / "setup_state.json").exists():
            state_text = (halo_home / "setup_state.json").read_text()
            assert self.RAW_KEY not in state_text


# ---------------------------------------------------------------------------
# Voice default ON — the spec says steps 3+4 are required, voice is
# defaulted to on.
# ---------------------------------------------------------------------------


class TestVoiceDefault:
    """Per M13 Q3, voice is REQUIRED to finish. The wizard defaults
    voice.enabled = true and refuses to advance past step 2/3/4 with
    voice off."""

    @respx.mock
    def test_voice_asr_step_enables_voice(self, client, halo_home):
        """Step 3 (voice-asr) flips voice.enabled to true."""
        # Start with voice off
        (halo_home / "config.toml").write_text("")  # empty file
        client.post(
            "/api/setup/voice-asr",
            json={
                "backend": "whisper_local",
                "model_size": "base",
                "model_path": "",
            },
        )
        toml_text = (halo_home / "config.toml").read_text()
        assert "enabled = true" in toml_text or "enabled=true" in toml_text

    def test_voice_tts_step_enables_voice(self, client, halo_home):
        """Step 4 (voice-tts) also flips voice.enabled to true."""
        (halo_home / "config.toml").write_text("")
        client.post(
            "/api/setup/voice-tts",
            json={
                "backend": "edge",
                "voice": "zh-HK-HiuMaanNeural",
            },
        )
        toml_text = (halo_home / "config.toml").read_text()
        assert "enabled = true" in toml_text or "enabled=true" in toml_text

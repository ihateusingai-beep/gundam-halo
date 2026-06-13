"""Tests for app.core.setup_state — detection + persistence.

Covers:
- compute_setup_state() under each scenario
- load_setup_state / save_setup_state round-trip + atomic write
- reset_setup_state wipes the file but preserves config.toml
- is_tailscale_reachable() never raises, returns False on missing tool
- SetupState dataclass to_dict / from_dict round-trip
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest
import tomlkit
from app.core.setup_state import (
    ALLOWED_THEMES,
    STATE_FILENAME,
    STATE_VERSION,
    SetupState,
    compute_setup_state,
    is_tailscale_reachable,
    load_setup_state,
    now_iso,
    reset_setup_state,
    save_setup_state,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def halo_home(tmp_path: Path) -> Path:
    """An empty HALO_HOME in tmp_path (autouse fixture in conftest
    already redirected HALO_HOME here)."""
    return tmp_path


@pytest.fixture
def clean_env(monkeypatch):
    """Wipe MiniMax key env var so the tests start deterministic."""
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    yield
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)


def _write_minimal_config(home: Path, **overrides) -> Path:
    """Write a minimal config.toml to *home* with optional field overrides.

    Returns the config path. The config it writes satisfies
    compute_setup_state() = "ready" (llm key via env, voice on with
    ASR + TTS, no tailscale required). The caller can override any
    field to simulate a "missing" state.
    """
    cfg_path = home / "config.toml"
    cfg = {
        "user": {"name": "Tester", "default_theme": "gundam-ntd"},
        "llm": {
            "provider": "minimax",
            "api_key_env": "MINIMAX_API_KEY",
            "base_url": "https://api.minimax.io/v1",
            "default_model": "MiniMax-M2",
            "fallback_model": "MiniMax-M2",
        },
        "server": {
            "host": "0.0.0.0",
            "port": 8765,
            "log_level": "INFO",
            "require_tailscale": False,
            "tailscale_hostname": "gundam-halo",
        },
        "voice": {
            "enabled": True,
            "asr": {
                "backend": "whisper_local",
                "model_size": "base",
                "model_path": "",
                "language": "auto",
                "device": "auto",
                "compute_type": "auto",
            },
            "tts": {
                "backend": "edge",
                "voice": "zh-HK-HiuMaanNeural",
                "rate": "+0%",
                "pitch": "+0Hz",
                "volume": "+0%",
            },
        },
    }
    # Apply overrides using a deep merge
    for section, fields in overrides.items():
        for k, v in fields.items():
            if isinstance(v, dict) and k in cfg.get(section, {}):
                cfg[section][k].update(v)
            else:
                cfg.setdefault(section, {})[k] = v

    with open(cfg_path, "w", encoding="utf-8") as f:
        tomlkit.dump(cfg, f)
    return cfg_path


# ---------------------------------------------------------------------------
# compute_setup_state() — detection logic
# ---------------------------------------------------------------------------


class TestComputeSetupState:
    def test_no_config_toml_returns_needs_setup_step_1(self, halo_home, clean_env):
        """No config.toml → needs_setup, step 1 (welcome)."""
        state = compute_setup_state(halo_home)
        assert state.status == "needs_setup"
        assert state.current_step == 1
        assert "no config.toml" in state.reason

    def test_config_present_but_no_llm_key_returns_step_2(self, halo_home, clean_env):
        """Config exists but llm key is missing → step 2 (LLM)."""
        _write_minimal_config(halo_home, llm={"api_key_env": "MISSING_KEY"})
        # Make sure MISSING_KEY isn't in env
        os.environ.pop("MISSING_KEY", None)
        state = compute_setup_state(halo_home)
        assert state.status == "needs_setup"
        assert state.current_step == 2
        assert "llm.api_key" in state.reason

    def test_config_with_api_key_env_var_present_returns_ready(
        self, halo_home, clean_env, monkeypatch
    ):
        """If the api_key_env is set in os.environ, count it as configured."""
        _write_minimal_config(halo_home)
        monkeypatch.setenv("MINIMAX_API_KEY", "sk-test-key")
        # config singleton was loaded before we set the env — re-detect
        # by reloading.
        state = compute_setup_state(halo_home)
        assert state.status == "ready", state.reason

    def test_full_config_returns_ready(self, halo_home, clean_env, monkeypatch):
        """All required fields set + voice on → ready."""
        _write_minimal_config(halo_home)
        monkeypatch.setenv("MINIMAX_API_KEY", "sk-test-key")
        state = compute_setup_state(halo_home)
        assert state.status == "ready"

    def test_voice_on_but_no_asr_returns_step_3(
        self, halo_home, clean_env, monkeypatch
    ):
        """voice.enabled = true but ASR model not configured → step 3."""
        _write_minimal_config(
            halo_home, voice={"asr": {"model_size": "", "model_path": ""}}
        )
        monkeypatch.setenv("MINIMAX_API_KEY", "sk-test-key")
        state = compute_setup_state(halo_home)
        assert state.status == "needs_setup"
        assert state.current_step == 3
        assert "voice.asr" in state.reason

    def test_voice_disabled_returns_step_3(self, halo_home, clean_env, monkeypatch):
        """voice.enabled = false → flag missing (step 3) so the wizard
        can re-enable it. Per M13 Q3, voice is required to finish."""
        _write_minimal_config(halo_home, voice={"enabled": False})
        monkeypatch.setenv("MINIMAX_API_KEY", "sk-test-key")
        state = compute_setup_state(halo_home)
        assert state.status == "needs_setup"
        assert state.current_step == 3
        assert "voice.enabled" in state.reason

    def test_voice_on_but_no_tts_voice_returns_step_4(
        self, halo_home, clean_env, monkeypatch
    ):
        """ASR present but TTS voice empty → step 4."""
        _write_minimal_config(halo_home, voice={"tts": {"voice": ""}})
        monkeypatch.setenv("MINIMAX_API_KEY", "sk-test-key")
        state = compute_setup_state(halo_home)
        assert state.status == "needs_setup"
        assert state.current_step == 4
        assert "voice.tts" in state.reason

    def test_tailscale_required_but_unreachable_returns_step_6(
        self, halo_home, clean_env, monkeypatch
    ):
        """server.require_tailscale = true and tailscale can't be
        reached → step 6 (tutorial / install link)."""
        _write_minimal_config(halo_home, server={"require_tailscale": True})
        monkeypatch.setenv("MINIMAX_API_KEY", "sk-test-key")
        with patch(
            "app.core.setup_state.is_tailscale_reachable", return_value=False
        ):
            state = compute_setup_state(halo_home)
        assert state.status == "needs_setup"
        assert state.current_step == 6
        assert "server.tailscale" in state.reason

    def test_tailscale_required_and_reachable_returns_ready(
        self, halo_home, clean_env, monkeypatch
    ):
        """Tailscale required + reachable → ready."""
        _write_minimal_config(halo_home, server={"require_tailscale": True})
        monkeypatch.setenv("MINIMAX_API_KEY", "sk-test-key")
        with patch(
            "app.core.setup_state.is_tailscale_reachable", return_value=True
        ):
            state = compute_setup_state(halo_home)
        assert state.status == "ready"

    def test_tailscale_optional_even_if_unreachable(
        self, halo_home, clean_env, monkeypatch
    ):
        """server.require_tailscale = false (default) → no tailscale
        check, even if tailscale ping would fail."""
        _write_minimal_config(halo_home)  # default require_tailscale=False
        monkeypatch.setenv("MINIMAX_API_KEY", "sk-test-key")
        # No patch on is_tailscale_reachable — it should not be called.
        state = compute_setup_state(halo_home)
        assert state.status == "ready"

    def test_malformed_config_returns_needs_setup(self, halo_home, clean_env):
        """Malformed TOML → needs_setup, step 1, with error reason."""
        cfg_path = halo_home / "config.toml"
        cfg_path.write_text("this is = not valid toml [[[")
        state = compute_setup_state(halo_home)
        assert state.status == "needs_setup"
        assert state.current_step == 1
        # reason should mention a parse error
        assert "parse" in state.reason or "config" in state.reason


# ---------------------------------------------------------------------------
# is_tailscale_reachable() — never raises
# ---------------------------------------------------------------------------


class TestIsTailscaleReachable:
    def test_returns_false_if_tailscale_not_on_path(self, monkeypatch):
        """When `tailscale` isn't on $PATH, return False without raising."""
        # shutil.which returns None if not found; force it.
        with patch("app.core.setup_state.shutil.which", return_value=None):
            assert is_tailscale_reachable() is False

    def test_returns_false_on_subprocess_failure(self, monkeypatch):
        """When tailscale binary exists but ping fails, return False."""
        with patch(
            "app.core.setup_state.shutil.which", return_value="/usr/bin/tailscale"
        ):
            fake_result = type("R", (), {"returncode": 1})()
            with patch(
                "app.core.setup_state.subprocess.run", return_value=fake_result
            ):
                assert is_tailscale_reachable() is False

    def test_returns_true_on_successful_ping(self, monkeypatch):
        """Exit code 0 → reachable."""
        with patch(
            "app.core.setup_state.shutil.which", return_value="/usr/bin/tailscale"
        ):
            fake_result = type("R", (), {"returncode": 0})()
            with patch(
                "app.core.setup_state.subprocess.run", return_value=fake_result
            ):
                assert is_tailscale_reachable() is True

    def test_returns_false_on_timeout(self, monkeypatch):
        """subprocess.TimeoutExpired → False."""
        with patch(
            "app.core.setup_state.shutil.which", return_value="/usr/bin/tailscale"
        ):
            import subprocess as sp

            def raise_timeout(*a, **kw):
                raise sp.TimeoutExpired(cmd="tailscale", timeout=5)

            with patch(
                "app.core.setup_state.subprocess.run", side_effect=raise_timeout
            ):
                assert is_tailscale_reachable() is False


# ---------------------------------------------------------------------------
# Persistence — load / save / reset
# ---------------------------------------------------------------------------


class TestPersistence:
    def test_load_returns_default_when_no_file(self, halo_home):
        """No setup_state.json → default needs_setup state."""
        s = load_setup_state(halo_home)
        assert s.status == "needs_setup"
        assert s.current_step == 1
        assert "no setup_state.json" in s.reason

    def test_save_then_load_round_trips(self, halo_home):
        """save_setup_state → load_setup_state returns equivalent state."""
        s = SetupState(
            status="needs_setup",
            current_step=3,
            completed_steps=[1, 2],
            started_at="2026-06-13T10:00:00+00:00",
            reason="test",
        )
        save_setup_state(halo_home, s)
        loaded = load_setup_state(halo_home)
        assert loaded.status == "needs_setup"
        assert loaded.current_step == 3
        assert loaded.completed_steps == [1, 2]
        assert loaded.started_at == "2026-06-13T10:00:00+00:00"
        assert loaded.reason == "test"

    def test_save_creates_dir_if_missing(self, halo_home):
        """If the home dir doesn't exist, save_setup_state creates it."""
        sub = halo_home / "subdir" / "deeper"
        s = SetupState(status="ready", current_step=7)
        save_setup_state(sub, s)
        assert (sub / STATE_FILENAME).exists()
        loaded = load_setup_state(sub)
        assert loaded.status == "ready"

    def test_load_returns_default_on_malformed_json(self, halo_home):
        """Malformed JSON file → default state (no exception)."""
        (halo_home / STATE_FILENAME).write_text("{ not valid json")
        s = load_setup_state(halo_home)
        assert s.status == "needs_setup"
        assert "unreadable" in s.reason

    def test_load_is_resilient_to_unexpected_types(self, halo_home):
        """Garbage types in the file → defensive defaults."""
        (halo_home / STATE_FILENAME).write_text(
            json.dumps(
                {
                    "version": "not-a-number",
                    "status": None,
                    "current_step": "1",
                    "completed_steps": "not-a-list",
                }
            )
        )
        s = load_setup_state(halo_home)
        # Should not raise; values should be coerced
        assert s.status == "needs_setup"
        assert s.current_step == 1
        assert s.completed_steps == []

    def test_atomic_write_no_leftover_tmp(self, halo_home):
        """save_setup_state doesn't leave .tmp files behind."""
        save_setup_state(halo_home, SetupState(status="ready", current_step=7))
        leftovers = [
            p for p in halo_home.iterdir() if p.name.startswith(".setup_state.")
        ]
        assert not leftovers, f"leftover tmp files: {leftovers}"

    def test_reset_wipes_state_file(self, halo_home):
        """reset_setup_state deletes the file and writes a fresh default."""
        # First, save a "finished" state
        save_setup_state(halo_home, SetupState(status="ready", current_step=7))
        assert (halo_home / STATE_FILENAME).exists()
        # Reset
        fresh = reset_setup_state(halo_home)
        assert fresh.status == "needs_setup"
        assert fresh.current_step == 1
        # A fresh file should exist (reset writes a new default)
        assert (halo_home / STATE_FILENAME).exists()
        # And it should be the default
        reloaded = load_setup_state(halo_home)
        assert reloaded.status == "needs_setup"

    def test_reset_preserves_config_toml(self, halo_home):
        """Per M13 §"Reset wizard", config.toml must NOT be deleted."""
        _write_minimal_config(halo_home)
        cfg_path = halo_home / "config.toml"
        assert cfg_path.exists()
        reset_setup_state(halo_home)
        # Config is still there
        assert cfg_path.exists()


# ---------------------------------------------------------------------------
# SetupState dataclass
# ---------------------------------------------------------------------------


class TestSetupStateDataclass:
    def test_to_dict_shape(self):
        s = SetupState(
            status="needs_setup",
            current_step=3,
            completed_steps=[1, 2, 2],  # dupes — should be deduped
        )
        d = s.to_dict()
        assert d["version"] == STATE_VERSION
        assert d["status"] == "needs_setup"
        assert d["current_step"] == 3
        assert d["completed_steps"] == [1, 2]  # deduped + sorted
        assert d["started_at"] is None
        assert d["finished_at"] is None
        assert d["skipped"] is False

    def test_from_dict_with_garbage(self):
        """Defensive parsing — non-dict input → defaults."""
        s = SetupState.from_dict(None)  # type: ignore[arg-type]
        assert s.status == "needs_setup"
        assert s.current_step == 1

    def test_from_dict_with_partial_data(self):
        s = SetupState.from_dict({"status": "ready", "skipped": True})
        assert s.status == "ready"
        assert s.skipped is True
        assert s.current_step == 1  # default

    def test_now_iso_is_utc(self):
        """now_iso() returns a string with timezone info."""
        s = now_iso()
        assert isinstance(s, str)
        assert "T" in s
        # ISO 8601 with explicit timezone offset (e.g. +00:00 or Z)
        assert s.endswith("+00:00") or s.endswith("Z")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestConstants:
    def test_allowed_themes_has_8_entries(self):
        assert len(ALLOWED_THEMES) == 8
        assert "gundam-ntd" in ALLOWED_THEMES  # default
        # Sanity: no duplicates
        assert len(set(ALLOWED_THEMES)) == 8

    def test_state_filename_is_setup_state_json(self):
        assert STATE_FILENAME == "setup_state.json"

    def test_state_version_is_1(self):
        assert STATE_VERSION == 1

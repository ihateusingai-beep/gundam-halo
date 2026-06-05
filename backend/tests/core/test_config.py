"""Tests for the config loader."""
import os
import pytest

from app.core.config import (
    Config,
    LLMConfig,
    MacControlConfig,
    SecurityConfig,
    ServerConfig,
    TelegramConfig,
    UserConfig,
    get_config,
    load_config,
    reset_config,
)


def test_default_config():
    cfg = load_config()
    assert isinstance(cfg, Config)
    assert cfg.user.name == "User"
    assert cfg.user.default_theme == "gundam-ntd"
    assert cfg.llm.provider == "minimax"
    assert cfg.llm.base_url == "https://api.MiniMax.chat/v1"
    assert cfg.llm.default_model == "MiniMax-M3"
    assert cfg.server.port == 8765
    assert "git" in cfg.mac.shell_allowlist
    assert "open" in cfg.mac.shell_allowlist


def test_env_override(tmp_path, monkeypatch):
    """Env vars should override TOML values."""
    monkeypatch.setenv("HALO_HOME", str(tmp_path))
    monkeypatch.setenv("HALO_PORT", "9999")
    monkeypatch.setenv("MINIMAX_API_KEY", "test-key-123")
    monkeypatch.setenv("HALO_LOG_LEVEL", "DEBUG")

    reset_config()
    cfg = load_config()

    assert cfg.server.port == 9999
    assert cfg.llm.api_key == "test-key-123"
    assert cfg.server.log_level == "DEBUG"
    assert str(cfg.home).startswith(str(tmp_path))


def test_get_config_singleton():
    reset_config()
    c1 = get_config()
    c2 = get_config()
    assert c1 is c2

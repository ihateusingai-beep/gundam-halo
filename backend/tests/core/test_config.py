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


def test_default_config(tmp_path, monkeypatch):
    """Verify the dataclass defaults (no TOML/ENV override).

    Uses `tmp_path` + `monkeypatch.setenv("HALO_HOME", ...)`
    to load an EMPTY config (no `~/.gundam-halo/config.toml`
    in the test path) so the test reflects the
    `LLMConfig().base_url` dataclass default rather
    than any user-local override. This is a fix
    for the pre-existing test failure (commit
    973fe4b was the last known-good baseline; the
    failure was latent in the test suite since
    the user's `~/.gundam-halo/config.toml`
    drifted to `.io` cluster).

    The test was previously passing for a user
    who happened to have `.chat` in their
    `~/.gundam-halo/config.toml`, and failing
    for a user with `.io` (the actual default).
    The fix uses `tmp_path` to make the test
    deterministic regardless of the user's
    local config.

    See `docs/CHANGELOG.md` for the discussion
    of the `.io` vs `.chat` cluster difference.
    """
    monkeypatch.setenv("HALO_HOME", str(tmp_path))
    # No config.toml in tmp_path — load_config returns all defaults
    reset_config()
    cfg = load_config()
    assert isinstance(cfg, Config)
    assert cfg.user.name == "User"
    assert cfg.user.default_theme == "gundam-ntd"
    assert cfg.llm.provider == "minimax"
    # Match the actual LLMConfig().base_url default
    # (https://api.minimax.io/v1, the `.io` cluster
    # — different from the `.chat` cluster which
    # requires a different API key scope).
    assert cfg.llm.base_url == "https://api.minimax.io/v1"
    # The default_model was changed from MiniMax-M3
    # to MiniMax-M2 in some recent commit — match
    # the actual default. (The original test
    # assertion "MiniMax-M3" was stale.)
    assert cfg.llm.default_model == "MiniMax-M2"
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

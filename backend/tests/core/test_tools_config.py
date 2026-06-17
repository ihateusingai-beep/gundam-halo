"""Tests for the ToolsConfig dataclass + loader (Sprint 28/29).

Per `docs/FEATURE-SPEC-SPRINT28.md` §4.1 + §4.2.

Test categories:
  1. Sub-config defaults (5 sub-configs × multiple fields)
  2. _load_sub_config helper (generic sub-config loader)
  3. _load_tools_config (4 sub-configs + TOML loading)
  4. Config root + cfg.tools.<name> accessor

The tests use the existing `reset_config()` fixture
to ensure a clean singleton between tests.
"""
from __future__ import annotations

import os
import textwrap

import pytest

from app.core.config import (
    Config,
    FlightFinderConfig,
    SendMessageConfig,
    ToolsConfig,
    WebSearchConfig,
    YouTubeSummarizeConfig,
    get_config,
    load_config,
    reset_config,
)


# ---------------------------------------------------------------------------
# 1. Sub-config defaults
# ---------------------------------------------------------------------------


class TestSubConfigDefaults:
    def test_web_search_defaults(self):
        cfg = WebSearchConfig()
        assert cfg.enabled is True
        assert cfg.max_results == 5
        assert cfg.summary_max_chars == 800
        assert cfg.request_timeout_s == 10.0

    def test_youtube_summarize_defaults(self):
        cfg = YouTubeSummarizeConfig()
        assert cfg.enabled is True
        assert cfg.max_transcript_chars == 12_000
        assert cfg.summary_max_chars == 800

    def test_flight_finder_defaults(self):
        cfg = FlightFinderConfig()
        assert cfg.enabled is True
        # No other fields — the URL builder doesn't need them
        # in v0.1.5+ (Sprint 27 spec §4.2 Track 27.3).

    def test_send_message_default_disabled(self):
        """The one opt-in default: send_message is
        `enabled = False` because pyautogui is fragile
        (Sprint 27 spec §4.2 Track 27.4)."""
        cfg = SendMessageConfig()
        assert cfg.enabled is False
        assert cfg.default_platform == "whatsapp"

    def test_tools_config_instantiates_all_4_sub_configs(self):
        cfg = ToolsConfig()
        assert isinstance(cfg.web_search, WebSearchConfig)
        assert isinstance(cfg.youtube_summarize, YouTubeSummarizeConfig)
        assert isinstance(cfg.flight_finder, FlightFinderConfig)
        assert isinstance(cfg.send_message, SendMessageConfig)


# ---------------------------------------------------------------------------
# 2. _load_sub_config helper
# ---------------------------------------------------------------------------


class TestLoadSubConfigHelper:
    def test_load_sub_config_with_empty_dict(self):
        from app.core.config import _load_sub_config

        result = _load_sub_config({}, WebSearchConfig)
        assert result == WebSearchConfig()  # all defaults

    def test_load_sub_config_with_full_dict(self):
        from app.core.config import _load_sub_config

        result = _load_sub_config(
            {"enabled": False, "max_results": 10},
            WebSearchConfig,
        )
        assert result.enabled is False
        assert result.max_results == 10
        # Unspecified fields fall back to defaults
        assert result.summary_max_chars == 800
        assert result.request_timeout_s == 10.0

    def test_load_sub_config_with_unknown_fields_ignored(self):
        """Extra fields in the TOML section that don't
        match a dataclass field are silently ignored
        (forward-compatibility for older configs)."""
        from app.core.config import _load_sub_config

        result = _load_sub_config(
            {"enabled": True, "future_field": "ignored"},
            WebSearchConfig,
        )
        assert result.enabled is True

    def test_load_sub_config_preserves_field_order(self):
        """The helper iterates dataclasses.fields() in
        declaration order. This is a property of
        Python dataclasses — fields are returned in
        the order they're declared in the class body.
        A new field added to the bottom of a
        sub-config dataclass is correctly read from
        TOML."""
        from app.core.config import _load_sub_config

        result = _load_sub_config(
            {"max_results": 3},
            WebSearchConfig,
        )
        assert result.max_results == 3
        # All other fields default
        assert result.enabled is True


# ---------------------------------------------------------------------------
# 3. _load_tools_config (TOML loading)
# ---------------------------------------------------------------------------


class TestLoadToolsConfig:
    def test_load_tools_config_empty_toml(self, tmp_path, monkeypatch):
        """toml_data = {} returns all defaults."""
        monkeypatch.setenv("HALO_HOME", str(tmp_path))
        # No config.toml in tmp_path
        reset_config()
        cfg = load_config()
        assert isinstance(cfg.tools, ToolsConfig)
        assert cfg.tools.web_search.enabled is True
        assert cfg.tools.send_message.enabled is False

    def test_load_tools_config_partial_override(
        self, tmp_path, monkeypatch
    ):
        """Setting one field in [tools.*] overrides
        that field; others stay default."""
        config_path = tmp_path / "config.toml"
        config_path.write_text(textwrap.dedent("""
            [tools.web_search]
            max_results = 10
            request_timeout_s = 20.0
        """).strip())
        monkeypatch.setenv("HALO_HOME", str(tmp_path))
        reset_config()
        cfg = load_config()
        assert cfg.tools.web_search.max_results == 10
        assert cfg.tools.web_search.request_timeout_s == 20.0
        # Other fields stay default
        assert cfg.tools.web_search.enabled is True
        assert cfg.tools.web_search.summary_max_chars == 800
        # Other tools stay default
        assert cfg.tools.send_message.enabled is False
        assert cfg.tools.youtube_summarize.enabled is True

    def test_load_tools_config_send_message_override(
        self, tmp_path, monkeypatch
    ):
        """Setting [tools.send_message] enabled = true
        flips the default to True (user opts in)."""
        config_path = tmp_path / "config.toml"
        config_path.write_text(textwrap.dedent("""
            [tools.send_message]
            enabled = true
            default_platform = "telegram"
        """).strip())
        monkeypatch.setenv("HALO_HOME", str(tmp_path))
        reset_config()
        cfg = load_config()
        assert cfg.tools.send_message.enabled is True
        assert cfg.tools.send_message.default_platform == "telegram"

    def test_load_tools_config_all_disabled(
        self, tmp_path, monkeypatch
    ):
        """Setting all 4 enabled = false returns
        ToolsConfig with all 4 sub-configs disabled.
        (Simulates a paranoid enterprise deployment.)"""
        config_path = tmp_path / "config.toml"
        config_path.write_text(textwrap.dedent("""
            [tools.web_search]
            enabled = false
            [tools.youtube_summarize]
            enabled = false
            [tools.flight_finder]
            enabled = false
            [tools.send_message]
            enabled = false
        """).strip())
        monkeypatch.setenv("HALO_HOME", str(tmp_path))
        reset_config()
        cfg = load_config()
        assert cfg.tools.web_search.enabled is False
        assert cfg.tools.youtube_summarize.enabled is False
        assert cfg.tools.flight_finder.enabled is False
        assert cfg.tools.send_message.enabled is False

    def test_load_tools_config_missing_tools_section(
        self, tmp_path, monkeypatch
    ):
        """A config.toml that doesn't have a [tools]
        section at all returns all defaults."""
        config_path = tmp_path / "config.toml"
        config_path.write_text(textwrap.dedent("""
            [llm]
            provider = "minimax"
        """).strip())
        monkeypatch.setenv("HALO_HOME", str(tmp_path))
        reset_config()
        cfg = load_config()
        assert isinstance(cfg.tools, ToolsConfig)
        # All defaults
        assert cfg.tools.web_search.enabled is True
        assert cfg.tools.send_message.enabled is False

    def test_load_tools_config_unknown_sub_section_ignored(
        self, tmp_path, monkeypatch
    ):
        """An unknown [tools.bogus] section is silently
        ignored — no error, no BogusConfig instantiation."""
        config_path = tmp_path / "config.toml"
        config_path.write_text(textwrap.dedent("""
            [tools.bogus]
            enabled = false
            [tools.web_search]
            max_results = 7
        """).strip())
        monkeypatch.setenv("HALO_HOME", str(tmp_path))
        reset_config()
        cfg = load_config()
        assert cfg.tools.web_search.max_results == 7
        # The bogus section didn't break the loader
        assert cfg.tools.send_message.enabled is False


# ---------------------------------------------------------------------------
# 4. Config root + cfg.tools.<name> accessor
# ---------------------------------------------------------------------------


class TestConfigAccessor:
    def test_config_has_tools_field(self):
        cfg = Config()
        assert hasattr(cfg, "tools")
        assert isinstance(cfg.tools, ToolsConfig)

    def test_get_config_returns_tools(self, tmp_path, monkeypatch):
        """The singleton `get_config().tools` accessor
        works after the singleton is populated."""
        monkeypatch.setenv("HALO_HOME", str(tmp_path))
        reset_config()
        cfg = get_config()
        assert isinstance(cfg.tools, ToolsConfig)
        # Defaults
        assert cfg.tools.web_search.enabled is True
        assert cfg.tools.send_message.enabled is False

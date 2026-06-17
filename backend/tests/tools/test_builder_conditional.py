"""Tests for conditional tool registration in default_tools() (Sprint 28/29).

Per `docs/FEATURE-SPEC-SPRINT28.md` §4.3 + §4.4.

Test categories:
  1. All 4 Mark-XL tools enabled (default state)
  2. Per-tool disable (each of 4 sub-configs)
  3. All 4 Mark-XL tools disabled
  4. Disabled tool not in OpenAI specs
  5. Hot-reload not yet wired (restart required)

The tests use `monkeypatch.setattr(cfg.tools.web_search,
"enabled", False)` to flip individual tools on/off
without re-parsing the TOML. The `reset_config()`
fixture ensures a clean singleton between tests.
"""
from __future__ import annotations

import textwrap

import pytest

from app.core.config import (
    get_config,
    load_config,
    reset_config,
)
from app.tools.builder import default_tools


# ---------------------------------------------------------------------------
# 1. All 4 Mark-XL tools enabled (default state)
# ---------------------------------------------------------------------------


class TestAllEnabledDefault:
    def test_default_state_has_3_mark_xl_tools(self, tmp_path, monkeypatch):
        """Default state: web_search + youtube_summarize +
        flight_finder enabled (3 of 4 Mark-XL tools).
        send_message is disabled (opt-in only).

        Tool count: 18 (pre-Sprint 27) + 3 (enabled Mark-XL) = 21.
        """
        monkeypatch.setenv("HALO_HOME", str(tmp_path))
        reset_config()
        load_config()
        tools = default_tools()
        names = [t.name for t in tools]
        assert "web_search" in names
        assert "youtube_summarize" in names
        assert "flight_finder" in names
        assert "send_message" not in names  # opt-in
        assert len(tools) == 21

    def test_send_message_default_disabled(
        self, tmp_path, monkeypatch
    ):
        """send_message is the one opt-in default."""
        monkeypatch.setenv("HALO_HOME", str(tmp_path))
        reset_config()
        load_config()
        cfg = get_config()
        assert cfg.tools.send_message.enabled is False


# ---------------------------------------------------------------------------
# 2. Per-tool disable
# ---------------------------------------------------------------------------


class TestPerToolDisable:
    def test_disabled_send_message_no_op_yields_21_tools(
        self, tmp_path, monkeypatch
    ):
        """send_message defaults to disabled (the one
        opt-in default). Setting `enabled = False`
        explicitly is a no-op. Tool count stays at
        21 (18 pre-Sprint 27 + 3 enabled Mark-XL)."""
        monkeypatch.setenv("HALO_HOME", str(tmp_path))
        reset_config()
        load_config()
        cfg = get_config()
        cfg.tools.send_message.enabled = False  # no-op (already default)
        tools = default_tools()
        assert len(tools) == 21  # 18 + 3 Mark-XL (no send_message)

    def test_disabled_web_search(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HALO_HOME", str(tmp_path))
        reset_config()
        load_config()
        cfg = get_config()
        cfg.tools.web_search.enabled = False
        tools = default_tools()
        names = [t.name for t in tools]
        assert "web_search" not in names
        # Other Mark-XL tools stay enabled
        assert "youtube_summarize" in names
        assert "flight_finder" in names
        assert len(tools) == 20  # 18 + 2 Mark-XL (no send_message)

    def test_disabled_youtube_summarize(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HALO_HOME", str(tmp_path))
        reset_config()
        load_config()
        cfg = get_config()
        cfg.tools.youtube_summarize.enabled = False
        tools = default_tools()
        names = [t.name for t in tools]
        assert "youtube_summarize" not in names
        assert "web_search" in names
        assert "flight_finder" in names
        assert len(tools) == 20

    def test_disabled_flight_finder(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HALO_HOME", str(tmp_path))
        reset_config()
        load_config()
        cfg = get_config()
        cfg.tools.flight_finder.enabled = False
        tools = default_tools()
        names = [t.name for t in tools]
        assert "flight_finder" not in names
        assert "web_search" in names
        assert "youtube_summarize" in names
        assert len(tools) == 20


# ---------------------------------------------------------------------------
# 3. All 4 Mark-XL tools disabled
# ---------------------------------------------------------------------------


class TestAllDisabled:
    def test_all_disabled_yields_18_tools(self, tmp_path, monkeypatch):
        """Disable all 4 Mark-XL tools → only the 18
        pre-Sprint 27 tools remain. (Simulates a
        paranoid enterprise deployment.)"""
        monkeypatch.setenv("HALO_HOME", str(tmp_path))
        reset_config()
        load_config()
        cfg = get_config()
        cfg.tools.web_search.enabled = False
        cfg.tools.youtube_summarize.enabled = False
        cfg.tools.flight_finder.enabled = False
        cfg.tools.send_message.enabled = False
        tools = default_tools()
        assert len(tools) == 18
        for name in ("web_search", "youtube_summarize",
                     "flight_finder", "send_message"):
            assert name not in [t.name for t in tools]


# ---------------------------------------------------------------------------
# 4. Disabled tool not in OpenAI specs
# ---------------------------------------------------------------------------


class TestDisabledNotInSpecs:
    def test_disabled_tool_not_in_openai_specs(
        self, tmp_path, monkeypatch
    ):
        """When a tool is disabled, its `to_spec()`
        is not in the list of OpenAI specs returned
        to the LLM. This is the user-facing test:
        the LLM never sees the disabled tool."""
        monkeypatch.setenv("HALO_HOME", str(tmp_path))
        reset_config()
        load_config()
        cfg = get_config()
        cfg.tools.web_search.enabled = False
        tools = default_tools()
        specs = [t.to_spec() for t in tools]
        spec_names = [s["function"]["name"] for s in specs]
        assert "web_search" not in spec_names
        # The other 2 enabled Mark-XL tools are in the specs
        assert "youtube_summarize" in spec_names
        assert "flight_finder" in spec_names

    def test_all_4_specs_when_all_enabled(
        self, tmp_path, monkeypatch
    ):
        """When all 4 Mark-XL tools are explicitly enabled
        (the user opts in to send_message), all 4 are in
        the OpenAI specs."""
        monkeypatch.setenv("HALO_HOME", str(tmp_path))
        reset_config()
        load_config()
        cfg = get_config()
        cfg.tools.send_message.enabled = True
        tools = default_tools()
        specs = [t.to_spec() for t in tools]
        spec_names = [s["function"]["name"] for s in specs]
        for name in ("web_search", "youtube_summarize",
                     "flight_finder", "send_message"):
            assert name in spec_names
        assert len(tools) == 22


# ---------------------------------------------------------------------------
# 5. Hot-reload not yet wired (restart required)
# ---------------------------------------------------------------------------


class TestRestartRequired:
    def test_toml_change_requires_singleton_reload(
        self, tmp_path, monkeypatch
    ):
        """A change to the TOML doesn't propagate
        to the existing singleton — the user must
        restart the backend (which calls
        `reset_config()` then `load_config()`).

        This is the restart-required caveat
        documented in Sprint 28 spec §4.5.
        """
        # Initial config: send_message disabled
        config_path = tmp_path / "config.toml"
        config_path.write_text(textwrap.dedent("""
            [tools.send_message]
            enabled = false
        """).strip())
        monkeypatch.setenv("HALO_HOME", str(tmp_path))
        reset_config()
        load_config()
        assert get_config().tools.send_message.enabled is False

        # User edits the config file to enable send_message.
        # Without restarting, the singleton still has the
        # old value.
        config_path.write_text(textwrap.dedent("""
            [tools.send_message]
            enabled = true
        """).strip())
        # Note: we DON'T call reset_config() or load_config() again.
        # The singleton still has the old value.
        assert get_config().tools.send_message.enabled is False

        # After the user restarts the backend, the singleton
        # is repopulated with the new value.
        reset_config()
        load_config()
        assert get_config().tools.send_message.enabled is True

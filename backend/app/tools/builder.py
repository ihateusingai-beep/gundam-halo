"""Build a list of default tools for an agent.

Imported by the session manager to give agents their tool set.

Sprint 27 (per `docs/FEATURE-SPEC-SPRINT27.md`):
added 4 new tools ported from Mark-XL's `actions/`:
  - WebSearchTool (DDG HTML search, no extra dep)
  - YouTubeSummarizeTool (transcript fetch + summary,
    requires optional `youtube-transcript-api` dep)
  - FlightFinderTool (Google Flights URL builder, no
    real flight-data extraction — see spec §4.2 Track 27.3)
  - SendMessageTool (pyautogui-based, opt-in via
    `~/.gundam-halo/config.toml` — see spec §4.2 Track 27.4)

All 4 tools are always registered. The user can
disable them per-tool by editing the
`[tools.<name>].enabled` config section in
`~/.gundam-halo/config.toml` (see `config.toml.example`).

Sprint 32 P0-1 refactor: replaces the 22 hardcoded imports
+ 22 instance creations with a single `ToolRegistry.items()`
iteration. Each tool class opts in via the
`@register_tool("name")` class decorator (see
`app/core/registry.py`); `app/tools/__init__.py` eager-imports
every tool module so the decorators fire at import time.

Tool count: 21 (M11 + Sprint 16) → 25 (Sprint 27).
"""
from __future__ import annotations

from app.core.registry import ToolRegistry
from app.tools._stubs import BaseTool


def default_tools() -> list[BaseTool]:
    """Return the default set of tools available to agents.

    Sprint 28/29: conditionally register the 4
    Mark-XL tools (web_search, youtube_summarize,
    flight_finder, send_message) based on
    `cfg.tools.<name>.enabled`. A disabled tool is
    **invisible** to the LLM — the agent's tool
    spec list does not include it.

    Sprint 32 P0-1: `default_tools()` now iterates
    `ToolRegistry.items()` (22 entries) instead of
    hardcoding 22 imports + 22 instance creations.
    The conditional logic reduces to a single
    `_is_enabled(name, cfg)` check per tool.

    The `get_config()` import is **lazy** (inside
    the function body, not at module level) to
    avoid forcing a TOML parse during the test
    suite's module import. The test suite uses
    `monkeypatch.setattr(cfg.tools.web_search,
    "enabled", False)` to flip individual tools
    on/off at runtime.

    Changes to `enabled` take effect on backend
    restart (not runtime-tunable in v0.1.5+).
    See `docs/FEATURE-SPEC-SPRINT28.md` §4.5 for
    the restart caveat and Appendix F for why
    runtime toggling is deferred.
    """
    # Lazy import to avoid forcing a TOML parse at
    # module import time. `app.core.config` is a
    # heavyweight module (it pulls in stdlib tomllib,
    # the Config singleton, all loaders). The test
    # suite imports `builder.py` from many test files;
    # a module-level `from app.core.config import
    # get_config` would force the TOML parse to run
    # at every test module import, slowing the test
    # suite by 10-50ms per test file.
    from app.core.config import get_config

    cfg = get_config()
    # Sprint 36 Tier 2 — preload the SKILL.md cache so each
    # tool's `to_spec()` can look up its enriched description
    # in O(1). Idempotent; safe to call repeatedly (the
    # cache is keyed on home path + mtime). When no SKILL.md
    # exists for any tool, this is a no-op (the cache stays
    # empty, and `to_spec()` falls back to the class-level
    # description exactly as before).
    try:
        from app.core.skill_metadata import (
            ensure_skill_seeded,
            preload_cache,
        )

        preload_cache(cfg.home)
        # Sprint 36 Tier 2 first-run: seed any missing
        # SKILL.md files from the bundled starter set. Like
        # the workspace seeding in `agent_context.py`, this
        # only ever copies files that don't exist yet —
        # user edits are never overwritten.
        ensure_skill_seeded(
            cfg.home, list(name for name, _ in ToolRegistry.items())
        )
        # Re-load after seeding so the freshly-copied
        # starter files are visible to the cache.
        preload_cache(cfg.home)
    except Exception as e:  # noqa: BLE001
        # Skill seeding is best-effort. The runtime still
        # works with class-level descriptions if the SKILL.md
        # system fails (e.g. permission denied on
        # `~/.gundam-halo/skills/`).
        import logging

        logging.getLogger(__name__).debug(
            "skill seeding / preload failed: %s", e
        )

    tools: list[BaseTool] = [
        tool_cls()
        for name, tool_cls in sorted(ToolRegistry.items(), key=lambda x: x[0])
        if _is_enabled(name, cfg)
    ]
    return tools


def _is_enabled(name: str, cfg) -> bool:
    """Check whether a registered tool should be enabled.

    The 4 Mark-XL tools (web_search / youtube_summarize /
    flight_finder / send_message) have a
    `[tools.<name>].enabled` config field in
    `~/.gundam-halo/config.toml`. The legacy 18
    tools (file_read, file_write, shell_exec, etc.)
    do NOT have a config field — they're always
    enabled.

    `MemoryReadTool` / `MemoryWriteTool` are registered
    as `memory_read` / `memory_write` (Sprint 32 P0-1)
    and do not have config fields either — always
    enabled (the legacy 18 behavior).

    Returns:
        True if the tool should be included in the
        agent's tool list, False if it's gated off
        by a `cfg.tools.<name>.enabled = false`.
    """
    tools_cfg = getattr(cfg, "tools", None)
    if tools_cfg is None:
        # No ToolsConfig at all — everything is enabled.
        return True
    sub = getattr(tools_cfg, name, None)
    if sub is None:
        # No sub-config for this tool (legacy 18 + memory_*) —
        # always enabled.
        return True
    # Mark-XL 4 tools have an explicit `enabled` flag.
    return getattr(sub, "enabled", True)


__all__ = ["default_tools"]

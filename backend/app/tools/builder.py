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
The conditional registration pattern based on
`cfg.tools.<name>.enabled` is documented in the
spec §4.4 but is not yet wired in v0.1.5+ (a
follow-up sprint can add it without changing the
agent loop).

Tool count: 21 (M11 + Sprint 16) → 25 (Sprint 27).
"""

from __future__ import annotations

from app.tools._stubs import BaseTool
from app.tools.a11y import A11yTool
from app.tools.apple_script import AppleScriptTool
from app.tools.bluetooth import BluetoothTool
from app.tools.brightness import BrightnessTool
from app.tools.clipboard import ClipboardTool
from app.tools.file_read import FileReadTool
from app.tools.file_write import FileWriteTool
from app.tools.flight_finder import FlightFinderTool
from app.tools.mavis_delegate import MavisDelegateTool
from app.tools.memory import MemoryReadTool, MemoryWriteTool
from app.tools.notify import NotifyTool
from app.tools.open_app import OpenAppTool
from app.tools.screenshot import ScreenshotTool
from app.tools.send_message import SendMessageTool
from app.tools.shell_exec import ShellExecTool
from app.tools.spotlight import SpotlightTool
from app.tools.system_settings import SystemSettingsTool
from app.tools.weather import WeatherTool
from app.tools.web_fetch import WebFetchTool
from app.tools.web_search import WebSearchTool
from app.tools.youtube_summarize import YouTubeSummarizeTool


def default_tools() -> list[BaseTool]:
    """Return the default set of tools available to agents.

    Sprint 28/29: conditionally register the 4
    Mark-XL tools (web_search, youtube_summarize,
    flight_finder, send_message) based on
    `cfg.tools.<name>.enabled`. A disabled tool
    is **invisible** to the LLM — the agent's tool
    spec list does not include it.

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
    tools: list[BaseTool] = [
        FileReadTool(),
        FileWriteTool(),
        ShellExecTool(),
        OpenAppTool(),
        MavisDelegateTool(),
        # M7-Phase-1: web tools
        WebFetchTool(),
        WeatherTool(),
        # M7-Phase-2: per-user memory
        MemoryReadTool(),
        MemoryWriteTool(),
        # M11: Mac-control surface — completes the README claim set
        # (AppleScript / Clipboard / Notifications / Spotlight / A11y)
        AppleScriptTool(),
        ClipboardTool(),
        NotifyTool(),
        SpotlightTool(),
        A11yTool(),
        # Sprint 16: Unicorn voice control. Four new Mac-control
        # tools that round out the v1 use-case catalog. All opt-in
        # via the same audit log as the M11 set.
        BrightnessTool(),       # display brightness
        SystemSettingsTool(),   # DND / Focus + general prefs
        ScreenshotTool(),        # screencapture wrapper
        BluetoothTool(),         # BT list + connect (blueutil)
    ]

    # Sprint 28/29: conditional Mark-XL tool registration
    # (per `docs/FEATURE-SPEC-SPRINT28.md`). The 4 tools
    # are added only if their `enabled` flag is True in
    # `~/.gundam-halo/config.toml`'s [tools.*] section.
    # A disabled tool is invisible to the LLM (the agent
    # loop never sees it). The user can disable a tool
    # by setting `enabled = false` and restarting the
    # backend.
    if cfg.tools.web_search.enabled:
        tools.append(WebSearchTool())
    if cfg.tools.youtube_summarize.enabled:
        tools.append(YouTubeSummarizeTool())
    if cfg.tools.flight_finder.enabled:
        tools.append(FlightFinderTool())
    if cfg.tools.send_message.enabled:
        tools.append(SendMessageTool())

    return tools


__all__ = ["default_tools"]


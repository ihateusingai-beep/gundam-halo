"""Build a list of default tools for an agent.

Imported by the session manager to give agents their tool set.
"""

from __future__ import annotations

from app.tools._stubs import BaseTool
from app.tools.a11y import A11yTool
from app.tools.apple_script import AppleScriptTool
from app.tools.clipboard import ClipboardTool
from app.tools.file_read import FileReadTool
from app.tools.file_write import FileWriteTool
from app.tools.mavis_delegate import MavisDelegateTool
from app.tools.memory import MemoryReadTool, MemoryWriteTool
from app.tools.notify import NotifyTool
from app.tools.open_app import OpenAppTool
from app.tools.shell_exec import ShellExecTool
from app.tools.spotlight import SpotlightTool
from app.tools.weather import WeatherTool
from app.tools.web_fetch import WebFetchTool


def default_tools() -> list[BaseTool]:
    """Return the default set of tools available to agents."""
    return [
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
    ]


__all__ = ["default_tools"]


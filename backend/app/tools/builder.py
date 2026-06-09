"""Build a list of default tools for an agent.

Imported by the session manager to give agents their tool set.
"""

from __future__ import annotations

from app.tools._stubs import BaseTool
from app.tools.file_read import FileReadTool
from app.tools.file_write import FileWriteTool
from app.tools.mavis_delegate import MavisDelegateTool
from app.tools.memory import MemoryReadTool, MemoryWriteTool
from app.tools.open_app import OpenAppTool
from app.tools.shell_exec import ShellExecTool
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
    ]


__all__ = ["default_tools"]


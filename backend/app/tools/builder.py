"""Build a list of default tools for an agent.

Imported by the session manager to give agents their tool set.
"""

from __future__ import annotations

from app.tools._stubs import BaseTool
from app.tools.file_read import FileReadTool
from app.tools.file_write import FileWriteTool
from app.tools.open_app import OpenAppTool
from app.tools.shell_exec import ShellExecTool


def default_tools() -> list[BaseTool]:
    """Return the default set of tools available to agents."""
    return [
        FileReadTool(),
        FileWriteTool(),
        ShellExecTool(),
        OpenAppTool(),
    ]


__all__ = ["default_tools"]

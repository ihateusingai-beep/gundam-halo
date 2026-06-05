"""open_app tool — launch a Mac application via `open` command.

Lightweight — no policy gate beyond the `open` allowlist (which is already
in `cfg.mac.shell_allowlist`). The agent is expected to use this for
launching apps like Safari, Terminal, VSCode, etc.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from app.tools._stubs import BaseTool

logger = logging.getLogger(__name__)


class OpenAppTool(BaseTool):
    name = "open_app"
    description = (
        "Launch a Mac application by name. Examples: 'Safari', 'Terminal', 'Visual Studio Code', "
        "'Finder'. Uses macOS `open -a <app>` so the app comes to the foreground. "
        "If the app is already running, it will be focused. "
        "The app name is case-insensitive. Use sparingly — only when the user explicitly asks."
    )
    parameters: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "app_name": {
                "type": "string",
                "description": "Name of the application to launch (e.g. 'Safari', 'Terminal').",
            },
        },
        "required": ["app_name"],
    }

    async def run(self, app_name: str, **kwargs: Any) -> str:
        import subprocess

        try:
            result = subprocess.run(
                ["open", "-a", app_name],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if result.returncode == 0:
                return f"OK: launched {app_name}"
            return f"Error: failed to launch {app_name} (exit {result.returncode}): {result.stderr.strip()}"
        except subprocess.TimeoutExpired:
            return f"Error: timeout launching {app_name}"
        except Exception as e:
            logger.error(f"open_app error: {e}")
            return f"Error: {e}"


__all__ = ["OpenAppTool"]

"""AppleScript tool — wrapper over `osascript` for general Mac scripting.

AppleScript is a powerful Mac automation interface. This tool lets
the agent run arbitrary AppleScript snippets. The agent is expected
to write the snippet; we just run it. Sibling to shell_exec but for
the AppleScript vocabulary.

Use cases:
- "tell application 'Safari' to open location 'https://...'"
- "tell application 'Finder' to set the desktop picture to ..."
- Compose keystrokes via System Events (requires A11y — see a11y tool)

Audit-loggable. No path policy (string-only interface).
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from app.tools._stubs import BaseTool
from app.core.registry import register_tool
from app.mac.apple_script import run_applescript

logger = logging.getLogger(__name__)


@register_tool("apple_script")
class AppleScriptTool(BaseTool):
    name = "apple_script"
    description = (
        "Run an AppleScript snippet on macOS. AppleScript can drive any "
        "scriptable Mac app (Finder, Safari, Mail, Calendar, Music, etc.) "
        "and the OS itself (System Events, System Preferences). Use this "
        "for things shell_exec can't do — app-specific scripting, GUI "
        "navigation, etc. The `script` argument is the full AppleScript "
        "source. Returns the script's `return` value plus exit code."
    )
    parameters: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "script": {
                "type": "string",
                "description": (
                    "AppleScript source. Example: "
                    '`tell application "Safari" to get URL of front document`.'
                ),
            },
            "timeout": {
                "type": "integer",
                "description": "Subprocess timeout in seconds. Default 30.",
            },
        },
        "required": ["script"],
    }

    async def run(self, script: str, timeout: int = 30, **kwargs: Any) -> str:
        try:
            result = run_applescript(script=script, timeout=timeout)
        except PermissionError as e:
            return f"Error: {e}"
        except ValueError as e:
            return f"Error: {e}"
        except RuntimeError as e:
            return f"Error: {e}"

        if result["exit_code"] == 0:
            out = result["stdout"]
            return out if out else "OK: AppleScript completed (no return value)"
        return (
            f"Error: AppleScript failed (exit {result['exit_code']}): "
            f"{result['stderr']}"
        )


__all__ = ["AppleScriptTool"]

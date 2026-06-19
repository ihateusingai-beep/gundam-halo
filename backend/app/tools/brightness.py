"""brightness tool — get / set screen brightness via AppleScript.

Wraps `osascript` to drive macOS's per-display brightness control
through System Events. Two ops:

  - `get` — returns the current main-display brightness (0-100)
  - `set` — sets main-display brightness; takes `level` arg (0-100)

Notes:
  - System Events requires Accessibility permission (System Settings
    → Privacy & Security → Accessibility). The first call after a
    fresh install will pop a TCC dialog. After granting, subsequent
    calls are silent.
  - On external displays that don't support software brightness
    control (most modern LG / Dell / BenQ monitors), `set` may
    succeed but produce no visible change. We always return the
    operation result; the user can tell from looking at the screen.
  - macOS 10.15+ supports multiple displays; for v1 we only touch
    the main display. Multi-display brightness is a Sprint 18
    addition.
  - Audit-loggable via mac.a11y paths (System Events).
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from app.tools._stubs import BaseTool
from app.core.registry import register_tool

logger = logging.getLogger(__name__)

# AppleScript snippets. Built as constants so we can later test the
# raw string format (the mac.a11y / apple_script modules wrap osascript
# invocation; we go through the apple_script module).
_GET_BRIGHTNESS = """
tell application "System Events"
    set b to current settings of frontmost application
    return brightness
end tell
""".strip()

# `set` requires the new level value; we splice it in.
_SET_BRIGHTNESS_TMPL = """
tell application "System Events"
    set brightness to {level}
end tell
""".strip()


@register_tool("brightness")
class BrightnessTool(BaseTool):
    name = "brightness"
    description = (
        "Get or set the main display's screen brightness (0-100). "
        "Operations: 'get' returns the current level as an integer; "
        "'set' takes a 'level' integer (0-100) and applies it. Requires "
        "Accessibility permission for System Events. Use sparingly — "
        "this is a system-level change. Audit-loggable."
    )
    parameters: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["get", "set"],
                "description": "Whether to read or write the brightness.",
            },
            "level": {
                "type": "integer",
                "minimum": 0,
                "maximum": 100,
                "description": "New brightness level 0-100 (required when operation='set').",
            },
        },
        "required": ["operation"],
    }

    async def run(
        self,
        operation: str,
        level: int = -1,
        **kwargs: Any,
    ) -> str:
        # Lazy import so unit tests can run without the heavy
        # `app.mac.apple_script` dependency at import time.
        from app.mac.apple_script import run_applescript

        if operation == "get":
            try:
                result = run_applescript(script=_GET_BRIGHTNESS, timeout=10)
            except (PermissionError, ValueError, RuntimeError) as e:
                return f"Error: {e}"
            if result["exit_code"] != 0:
                return (
                    f"Error: brightness query failed (exit {result['exit_code']}): "
                    f"{result['stderr']}"
                )
            raw = result["stdout"].strip()
            try:
                pct = int(float(raw))
                return f"Main display brightness: {pct}%"
            except ValueError:
                # Some macOS versions return a different shape; surface
                # the raw value so the agent can still summarize.
                return f"Main display brightness: {raw!r} (could not parse as int)"

        if operation == "set":
            if not 0 <= level <= 100:
                return f"Error: 'level' must be between 0 and 100, got {level}"
            script = _SET_BRIGHTNESS_TMPL.format(level=level)
            try:
                result = run_applescript(script=script, timeout=10)
            except (PermissionError, ValueError, RuntimeError) as e:
                return f"Error: {e}"
            if result["exit_code"] != 0:
                return (
                    f"Error: brightness set failed (exit {result['exit_code']}): "
                    f"{result['stderr']}"
                )
            return f"OK: main display brightness set to {level}%"

        return f"Error: unknown operation {operation!r}"


__all__ = ["BrightnessTool"]

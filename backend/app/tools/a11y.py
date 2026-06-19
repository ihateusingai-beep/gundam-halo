"""Accessibility tool — read-only view of the macOS UI tree.

Wraps `osascript -e 'tell application "System Events" to ...'`. We
expose four read-only operations and intentionally do NOT provide
a way to send synthetic input (that lives in a higher-trust path
out of v0.1.x scope).

Gated by `cfg.mac.a11y_enabled` (default False). The user must
opt in to give the agent Accessibility access. The first time a
System Events query runs, macOS will pop a TCC dialog asking
the user to grant permission — this is a system-level prompt,
not something we can short-circuit.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from app.tools._stubs import BaseTool
from app.core.registry import register_tool
from app.mac.a11y import (
    a11y_app_processes,
    a11y_focused_app,
    a11y_query,
    a11y_window_list,
)

logger = logging.getLogger(__name__)


@register_tool("a11y")
class A11yTool(BaseTool):
    name = "a11y"
    description = (
        "Read-only query of the macOS Accessibility API via System Events. "
        "Operations: 'windows' (list visible window names), 'processes' (list "
        "visible app names), 'focused' (return the frontmost app), 'query' "
        "(run a custom System Events snippet; the snippet must start with "
        "`tell application \"System Events\" to ...`). Synthetic input is "
        "NOT exposed by this tool. Requires a11y_enabled in config and a "
        "system Accessibility permission grant."
    )
    parameters: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["windows", "processes", "focused", "query"],
                "description": "Which A11y operation to run.",
            },
            "script": {
                "type": "string",
                "description": (
                    "Custom AppleScript snippet for operation='query'. Must "
                    "reference 'System Events'."
                ),
            },
            "timeout": {
                "type": "integer",
                "description": "Subprocess timeout in seconds. Default 30.",
            },
        },
        "required": ["operation"],
    }

    async def run(
        self,
        operation: str,
        script: str = "",
        timeout: int = 30,
        **kwargs: Any,
    ) -> str:
        try:
            if operation == "windows":
                result = a11y_window_list(timeout=timeout)
                return _format_list(result, "visible windows")
            if operation == "processes":
                result = a11y_app_processes(timeout=timeout)
                return _format_list(result, "visible app processes")
            if operation == "focused":
                result = a11y_focused_app(timeout=timeout)
                if result["exit_code"] != 0:
                    return (
                        f"Error: a11y_query failed (exit "
                        f"{result['exit_code']}): {result['stderr']}"
                    )
                return f"Frontmost app: {result['result'] or '(unknown)'}"
            if operation == "query":
                if not script:
                    return "Error: 'script' is required for operation='query'"
                result = a11y_query(script=script, timeout=timeout)
                if result["exit_code"] != 0:
                    return (
                        f"Error: a11y_query failed (exit "
                        f"{result['exit_code']}): {result['stderr']}"
                    )
                return result["result"] or "(empty result)"
            return f"Error: unknown operation {operation!r}"
        except PermissionError as e:
            return f"Error: {e}"
        except ValueError as e:
            return f"Error: {e}"
        except RuntimeError as e:
            return f"Error: {e}"


def _format_list(result: Dict[str, object], kind: str) -> str:
    """Format an a11y list result (windows/processes) for the agent."""
    if result["exit_code"] != 0:
        return (
            f"Error: a11y_query failed (exit {result['exit_code']}): "
            f"{result['stderr']}"
        )
    items = result.get("items", [])  # type: ignore[arg-type]
    if not items:
        return f"No {kind} found (or empty result)"
    lines = [f"{i+1}. {x}" for i, x in enumerate(items)]  # type: ignore[var-annotated]
    return f"Found {result['count']} {kind}:\n" + "\n".join(lines)  # type: ignore[arg-type]


__all__ = ["A11yTool"]

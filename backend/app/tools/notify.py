"""Notification tool — show a macOS system notification.

Wraps `osascript -e 'display notification ...'`. The user sees a
banner in the macOS Notification Center. Audit-loggable.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from app.tools._stubs import BaseTool
from app.core.registry import register_tool
from app.mac.notifications import send_notification

logger = logging.getLogger(__name__)


@register_tool("notify")
class NotifyTool(BaseTool):
    name = "notify"
    description = (
        "Show a macOS system notification banner. The user will see it in "
        "the Notification Center (right-side panel) and as a transient "
        "banner at the top of the screen. Use this to surface long-running "
        "task completion, alerts, or anything the user would want to know "
        "even if they're in another app. Audit-loggable."
    )
    parameters: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "The notification body — the main message.",
            },
            "title": {
                "type": "string",
                "description": "Optional title. Defaults to 'Gundam Halo'.",
            },
            "subtitle": {
                "type": "string",
                "description": "Optional subtitle shown below the title.",
            },
        },
        "required": ["text"],
    }

    async def run(
        self,
        text: str,
        title: str = "Gundam Halo",
        subtitle: str = "",
        **kwargs: Any,
    ) -> str:
        try:
            result = send_notification(
                text=text,
                title=title if title else None,
                subtitle=subtitle if subtitle else None,
            )
        except PermissionError as e:
            return f"Error: {e}"
        except ValueError as e:
            return f"Error: {e}"
        except RuntimeError as e:
            return f"Error: {e}"

        if result["exit_code"] == 0:
            return f"OK: notification sent ({result['duration_ms']}ms)"
        return (
            f"Error: notification failed (exit {result['exit_code']}): "
            f"{result['stderr']}"
        )


__all__ = ["NotifyTool"]

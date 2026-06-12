"""System notifications via `osascript` display notification.

macOS can show a banner notification via AppleScript:
    display notification "text" with title "title" subtitle "subtitle"

This wraps that. Gated by `cfg.mac.notifications_enabled` (default
True) — paranoid users can disable to keep the agent silent.

We use AppleScript rather than `terminal-notifier` or `pync` because
osascript ships with macOS and has no Python deps. The notification
center is a system-level surface; the user explicitly opted in by
enabling the flag.

Privacy note: the text is sent to the system notification center.
It will appear in the user's notification history (the right-side
Notification Center panel) until dismissed. Audit log keeps a copy
on our side.
"""
from __future__ import annotations

import logging
import shlex
import subprocess
import time
from typing import Dict, Optional

from app.core.config import get_config

logger = logging.getLogger(__name__)


def _escape_for_applescript(s: str) -> str:
    """Escape a string for use inside AppleScript double-quotes.

    AppleScript uses backslash escapes inside double-quoted strings,
    plus a few special cases (newline → return, " → \\\").
    """
    return s.replace("\\", "\\\\").replace('"', '\\"')


def send_notification(
    text: str,
    title: Optional[str] = None,
    subtitle: Optional[str] = None,
    timeout: int = 10,
) -> Dict[str, object]:
    """Show a macOS notification. Returns a small dict for the audit log."""
    if not text or not text.strip():
        raise ValueError("Notification text is empty")

    cfg = get_config()
    if not cfg.mac.notifications_enabled:
        raise PermissionError(
            "Notifications are disabled in config.toml "
            "(mac.notifications_enabled = false). "
            "Enable them to use this tool."
        )

    # Build the AppleScript snippet
    parts = [f'display notification "{_escape_for_applescript(text)}"']
    if title:
        parts.append(f'with title "{_escape_for_applescript(title)}"')
    if subtitle:
        parts.append(f'subtitle "{_escape_for_applescript(subtitle)}"')
    script = " ".join(parts)

    start = time.time()
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        duration_ms = int((time.time() - start) * 1000)
        return {
            "text": text,
            "title": title,
            "subtitle": subtitle,
            "exit_code": result.returncode,
            "stderr": result.stderr.strip(),
            "duration_ms": duration_ms,
        }
    except subprocess.TimeoutExpired:
        return {
            "text": text,
            "title": title,
            "subtitle": subtitle,
            "exit_code": -1,
            "stderr": f"Timeout after {timeout}s",
            "duration_ms": int((time.time() - start) * 1000),
        }


__all__ = ["send_notification"]

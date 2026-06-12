"""Accessibility API — a thin, safe wrapper over AppleScript System Events.

The macOS Accessibility API is a powerful interface that lets scripts
inspect the UI tree of any app, read window/button labels, and (with
proper permission) send synthetic key/click events. AppleScript's
"System Events" is the standard way to reach it from a script.

This module provides a *read-only* view of the Accessibility tree —
we never send synthetic input from this tool. Read-only is enough
for the agent's primary use case: figure out what's on screen and
report back. Sending input is much more dangerous and belongs to a
higher-trust path with explicit confirmation.

Gated by `cfg.mac.a11y_enabled` (default False) — this is the
single Mac-control capability that's off by default. The user
must opt in to give the agent Accessibility access. The first
time a System Events query runs, macOS will pop a TCC dialog
asking the user to grant permission to whatever terminal
osascript runs in — this is a system-level prompt, not a
Gundam-Halo check.

A11y queries in AppleScript are slow (multi-second), so we cap
the timeout generously.
"""
from __future__ import annotations

import logging
import subprocess
import time
from typing import Dict, List, Optional

from app.core.config import get_config

logger = logging.getLogger(__name__)

# Default timeout for A11y queries is generous — System Events is slow
DEFAULT_A11Y_TIMEOUT = 30


def _escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def a11y_window_list(timeout: int = DEFAULT_A11Y_TIMEOUT) -> Dict[str, object]:
    """List all visible window names via System Events.

    Returns:
        {
            "windows": List[str],   # window names, one per visible window
            "count": int,
            "exit_code": int,
            "stderr": str,
        }

    Privacy: window names often include document titles and app
    state. We surface them as-is; the user has opted in by
    enabling a11y_enabled in config.
    """
    if not _check_a11y_enabled():
        raise PermissionError(
            "Accessibility API is disabled in config.toml "
            "(mac.a11y_enabled = false). Enable it to use this tool."
        )

    script = (
        'tell application "System Events" to get name of every window of '
        'every application process whose visible is true'
    )
    return _run_a11y_script(script, timeout=timeout)


def a11y_app_processes(timeout: int = DEFAULT_A11Y_TIMEOUT) -> Dict[str, object]:
    """List visible app process names.

    Returns:
        {
            "processes": List[str],
            "count": int,
            "exit_code": int,
            "stderr": str,
        }
    """
    if not _check_a11y_enabled():
        raise PermissionError(
            "Accessibility API is disabled in config.toml "
            "(mac.a11y_enabled = false). Enable it to use this tool."
        )

    script = (
        'tell application "System Events" to get name of every application '
        'process whose visible is true'
    )
    return _run_a11y_script(script, timeout=timeout)


def a11y_focused_app(timeout: int = DEFAULT_A11Y_TIMEOUT) -> Dict[str, object]:
    """Return the name of the frontmost application process."""
    if not _check_a11y_enabled():
        raise PermissionError(
            "Accessibility API is disabled in config.toml "
            "(mac.a11y_enabled = false). Enable it to use this tool."
        )

    script = (
        'tell application "System Events" to get name of first application '
        'process whose frontmost is true'
    )
    return _run_a11y_script(script, timeout=timeout)


def a11y_query(script: str, timeout: int = DEFAULT_A11Y_TIMEOUT) -> Dict[str, object]:
    """Run a custom read-only AppleScript snippet under System Events.

    The snippet MUST start with `tell application "System Events" to ...`
    (we don't auto-wrap — script authors should be explicit). We
    *intentionally* do not provide a way to send synthetic input here:
    that would be a privilege escalation and lives in a separate
    tool behind a hard confirmation gate (out of v0.1.x scope).

    Args:
        script: full AppleScript snippet, beginning with a System Events
            `tell` block. Must be a read-only operation; we do not
            validate this.
        timeout: subprocess timeout in seconds.

    Returns:
        The script's stdout (AppleScript `return` value) plus exit
        code and stderr.
    """
    if not _check_a11y_enabled():
        raise PermissionError(
            "Accessibility API is disabled in config.toml "
            "(mac.a11y_enabled = false). Enable it to use this tool."
        )
    if not script or not script.strip():
        raise ValueError("AppleScript content is empty")
    if "System Events" not in script:
        raise ValueError(
            "Script must reference 'System Events' (we don't auto-wrap, "
            "and we don't allow non-A11y scripts via this tool)"
        )
    return _run_a11y_script(script, timeout=timeout)


def _check_a11y_enabled() -> bool:
    cfg = get_config()
    return bool(cfg.mac.a11y_enabled)


def _run_a11y_script(script: str, timeout: int) -> Dict[str, object]:
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
        # AppleScript lists of strings come back as comma-separated.
        # Split on comma and trim for the helper functions.
        stdout = result.stdout.strip()
        items: List[str] = []
        if stdout and "{" not in stdout and not stdout.startswith("missing"):
            items = [item.strip() for item in stdout.split(",") if item.strip()]
        return {
            "result": stdout,
            "items": items,
            "count": len(items),
            "exit_code": result.returncode,
            "stderr": result.stderr.strip(),
            "duration_ms": duration_ms,
        }
    except subprocess.TimeoutExpired:
        return {
            "result": "",
            "items": [],
            "count": 0,
            "exit_code": -1,
            "stderr": f"Timeout after {timeout}s",
            "duration_ms": int((time.time() - start) * 1000),
        }
    except FileNotFoundError:
        raise RuntimeError("`osascript` not found in PATH. This tool requires macOS.")


__all__ = [
    "a11y_window_list",
    "a11y_app_processes",
    "a11y_focused_app",
    "a11y_query",
]

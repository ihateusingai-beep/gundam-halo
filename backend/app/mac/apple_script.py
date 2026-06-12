"""AppleScript execution — thin wrapper over `osascript`.

AppleScript is a scripting language for macOS. The `osascript` CLI runs
.applescript files or -e snippets. We use it for:
- App control (tell application "X" to ...)
- System Events (UI scripting, requires Accessibility permission)
- Mail, Finder, Safari automation, etc.

Policy:
- Gated by `cfg.mac.apple_script_enabled` (default True).
- Always audit-logged (per `SettingsMac.require_confirm_for`).
- Script content is taken verbatim from the caller; the agent is
  expected to generate it. We do NOT parse or sanitize AppleScript
  — this is a deliberately low-level tool, like `shell_exec` but
  with a different vocabulary. Path-style policy doesn't apply;
  AppleScript is a string-only interface.

Security note: AppleScript on macOS is a powerful attack surface (can
trigger Accessibility events, send keystrokes, manipulate other apps).
This is why the `apple_script_enabled` flag exists — a paranoid
operator can disable it from `config.toml` to lock the agent out of
the scriptable Mac control plane entirely.
"""
from __future__ import annotations

import logging
import subprocess
import time
from typing import Dict

from app.core.config import get_config

logger = logging.getLogger(__name__)


def run_applescript(script: str, timeout: int = 30) -> Dict[str, object]:
    """Execute an AppleScript and return the result.

    Returns:
        {
            "script": str,           # echo back for audit
            "exit_code": int,        # osascript exit code (0 = success)
            "stdout": str,           # text result of `return` statement
            "stderr": str,           # any error output
            "duration_ms": int,
        }
    """
    if not script or not script.strip():
        raise ValueError("AppleScript content is empty")

    cfg = get_config()
    if not cfg.mac.apple_script_enabled:
        raise PermissionError(
            "AppleScript is disabled in config.toml "
            "(mac.apple_script_enabled = false). "
            "Enable it to use this tool."
        )

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
            "script": script,
            "exit_code": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "duration_ms": duration_ms,
        }
    except subprocess.TimeoutExpired as e:
        return {
            "script": script,
            "exit_code": -1,
            "stdout": (e.stdout.decode() if e.stdout else "").strip(),
            "stderr": f"Timeout after {timeout}s",
            "duration_ms": int((time.time() - start) * 1000),
        }
    except FileNotFoundError:
        # osascript not in PATH — shouldn't happen on macOS
        raise RuntimeError("`osascript` not found in PATH. This tool requires macOS.")


__all__ = ["run_applescript"]

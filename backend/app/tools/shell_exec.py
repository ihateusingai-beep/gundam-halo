"""shell_exec tool — execute a shell command, allowlist-gated.

REQUIRES user confirmation in real use.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from app.mac.shell import run_shell
from app.tools._stubs import BaseTool
from app.core.registry import register_tool

logger = logging.getLogger(__name__)


@register_tool("shell_exec")
class ShellExecTool(BaseTool):
    name = "shell_exec"
    description = (
        "Execute a shell command. The command's executable must be in the policy allowlist "
        "(e.g. git, ls, cat, grep, open). REQUIRES USER CONFIRMATION before use. "
        "Returns stdout, stderr, and exit code. "
        "For long-running commands, set timeout_sec (default 30s, max 300s). "
        "Avoid sudo / system-modifying commands."
    )
    parameters: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "Command and arguments, space-separated (will be parsed by shlex).",
            },
            "timeout_sec": {
                "type": "integer",
                "description": "Timeout in seconds. Default 30, max 300.",
                "default": 30,
            },
        },
        "required": ["command"],
    }

    async def run(self, command: str, timeout_sec: int = 30, **kwargs: Any) -> str:
        timeout = min(max(1, timeout_sec), 300)
        try:
            result = run_shell(command, timeout=timeout)
        except PermissionError as e:
            return f"Error: {e}"
        except Exception as e:
            logger.error(f"shell_exec error: {e}")
            return f"Error executing command: {e}"

        out = result["stdout"]
        err = result["stderr"]
        exit_code = result["exit_code"]

        parts = [f"Exit code: {exit_code}"]
        if out:
            parts.append(f"STDOUT:\n{out}")
        if err:
            parts.append(f"STDERR:\n{err}")

        result_text = "\n\n".join(parts)
        # Truncate
        MAX = 20_000
        if len(result_text) > MAX:
            return f"{result_text[:MAX]}\n\n[... truncated ...]"
        return result_text


__all__ = ["ShellExecTool"]

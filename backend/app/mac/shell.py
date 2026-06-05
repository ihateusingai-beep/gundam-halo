"""Shell command execution — allowlist-gated.

Uses subprocess to run commands. Returns exit code, stdout, stderr, duration.
"""

from __future__ import annotations

import shlex
import subprocess
import time
from typing import Dict

from app.mac.policy import check_shell_command


def run_shell(command: str, timeout: int = 30) -> Dict[str, object]:
    """Execute a shell command.

    Raises PermissionError if the command's executable is not in the allowlist.
    """
    if not check_shell_command(command):
        raise PermissionError(
            f"Command not in shell allowlist: {command.split()[0] if command else ''}"
        )

    start = time.time()
    try:
        result = subprocess.run(
            shlex.split(command),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        duration_ms = int((time.time() - start) * 1000)
        return {
            "command": command,
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "duration_ms": duration_ms,
        }
    except subprocess.TimeoutExpired as e:
        return {
            "command": command,
            "exit_code": -1,
            "stdout": e.stdout.decode() if e.stdout else "",
            "stderr": f"Timeout after {timeout}s",
            "duration_ms": int((time.time() - start) * 1000),
        }


__all__ = ["run_shell"]

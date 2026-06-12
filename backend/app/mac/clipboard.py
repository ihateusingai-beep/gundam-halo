"""Clipboard read/write via pbcopy / pbpaste.

macOS exposes the system clipboard via two CLI tools:
- `pbcopy` reads from stdin and writes to the clipboard
- `pbpaste` reads the clipboard and writes to stdout

We wrap both. No policy gate beyond an "is it a string" sanity check
— clipboard is a single-slot global, the agent is expected to use
sparingly (and the audit log records every read/write).

Use cases:
- Read what the user just copied and act on it (URL, address, etc.)
- Drop a result into the clipboard so the user can paste it
  into another app.
"""
from __future__ import annotations

import logging
import subprocess

logger = logging.getLogger(__name__)


def read_clipboard(timeout: int = 5) -> str:
    """Read the current clipboard text content.

    Returns the empty string if the clipboard is empty or holds a
    non-text type (image, file reference, etc.). Non-text returns
    also surface as `RuntimeError` from pbpaste on macOS — we
    catch that and return "".
    """
    try:
        result = subprocess.run(
            ["pbpaste"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if result.returncode != 0:
            # pbpaste returns 1 if the clipboard doesn't contain
            # plain text. Don't surface as an error — empty clipboard
            # is a normal state.
            return ""
        return result.stdout
    except subprocess.TimeoutExpired:
        return ""


def write_clipboard(text: str, timeout: int = 5) -> int:
    """Write text to the system clipboard. Returns bytes written."""
    if not isinstance(text, str):
        raise ValueError("Clipboard text must be a string")
    data = text.encode("utf-8")
    try:
        result = subprocess.run(
            ["pbcopy"],
            input=data,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        if result.returncode != 0:
            # text=True means stderr is already a str
            err = (result.stderr or "").strip()
            raise RuntimeError(f"pbcopy failed (exit {result.returncode}): {err}")
        return len(data)
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"pbcopy timed out after {timeout}s") from e
    except FileNotFoundError:
        raise RuntimeError("`pbcopy` not found in PATH. This tool requires macOS.")


__all__ = ["read_clipboard", "write_clipboard"]

"""File operations — read, write.

All operations go through `policy.check_path_*` first.
"""

from __future__ import annotations

import os
from pathlib import Path

from app.core.config import expand_home


def read_file(path: str) -> str:
    """Read a file as text. Raises FileNotFoundError, PermissionError, etc."""
    p = expand_home(path)
    if not p.exists():
        raise FileNotFoundError(f"File not found: {p}")
    if not p.is_file():
        raise ValueError(f"Not a file: {p}")
    return p.read_text(encoding="utf-8", errors="replace")


def write_file(path: str, content: str) -> int:
    """Write content to a file. Returns bytes written."""
    p = expand_home(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return len(content.encode("utf-8"))


__all__ = ["read_file", "write_file"]

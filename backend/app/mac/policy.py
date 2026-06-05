"""Path policy — decides whether a path is allowed for read/write.

Default: project_only. Means:
- Reads allowed in: file_read_paths (default: ~/Documents, ~/Downloads, ~/workspace, /tmp)
- Writes allowed in: file_write_paths (default: ~/workspace, ~/.gundam-halo/projects)

Future policies (TBD):
- user_home: read anywhere in $HOME except .ssh, .gnupg, etc.
- allowlist: explicit per-path allowlist
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List

from app.core.config import get_config, expand_home

# Paths that are NEVER readable or writable (defense-in-depth)
_NEVER_PATHS = [
    Path.home() / ".ssh",
    Path.home() / ".gnupg",
    Path.home() / ".aws",
    Path.home() / ".kube",
    Path("/etc"),
    Path("/System"),
    Path("/var/private"),
    Path("/private/etc"),
    Path("/private/var"),
]


def _resolve(path: str) -> Path:
    return Path(os.path.expanduser(path)).resolve()


def _is_in_never_paths(p: Path) -> bool:
    for never in _NEVER_PATHS:
        try:
            if p == never or never in p.parents:
                return True
        except OSError:
            continue
    return False


def _path_in_list(p: Path, allowed: List[str]) -> bool:
    """Check if p is under any of the allowed paths (after expansion + resolve)."""
    for ap in allowed:
        allowed_abs = expand_home(ap)
        try:
            p.relative_to(allowed_abs)
            return True
        except ValueError:
            continue
    return False


def check_path_read(path: str) -> bool:
    """Returns True if path is allowed for reading."""
    if not path:
        return False
    try:
        p = _resolve(path)
    except (OSError, RuntimeError):
        return False

    if _is_in_never_paths(p):
        return False

    cfg = get_config()
    return _path_in_list(p, cfg.mac.file_read_paths)


def check_path_write(path: str) -> bool:
    """Returns True if path is allowed for writing."""
    if not path:
        return False
    try:
        p = _resolve(path)
    except (OSError, RuntimeError):
        return False

    if _is_in_never_paths(p):
        return False

    cfg = get_config()
    return _path_in_list(p, cfg.mac.file_write_paths)


def check_shell_command(command: str) -> bool:
    """Returns True if the command is in the allowlist.

    Splits the command into the executable (first token) and checks that
    against cfg.mac.shell_allowlist.
    """
    if not command or not command.strip():
        return False
    parts = command.strip().split()
    if not parts:
        return False
    executable = parts[0]
    cfg = get_config()
    return executable in cfg.mac.shell_allowlist


__all__ = [
    "check_path_read",
    "check_path_write",
    "check_shell_command",
]

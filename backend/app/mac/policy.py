"""Path policy — decides whether a path is allowed for read/write.

Default: project_only. Means:
- Reads allowed in: file_read_paths (default: ~/Documents, ~/Downloads,
  ~/workspace, /tmp)
- Writes allowed in: file_write_paths (default: ~/workspace,
  ~/.gundam-halo/projects)

Future policies (TBD):
- user_home: read anywhere in $HOME except .ssh, .gnupg, etc.
- allowlist: explicit per-path allowlist

macOS path gotcha: `/var/folders/...` and `/tmp` are SYMLINKS to
`/private/var/folders/...` and `/private/tmp`. `Path.resolve()` returns
the `/private/...` form, so any allowlist entry must be checked in both
forms. See agent memory for the full story.
"""

from __future__ import annotations

import os
from pathlib import Path

from app.core.config import expand_home, get_config


def _never_paths() -> list[Path]:
    """Paths that are NEVER readable or writable (defense-in-depth).

    Narrow paths only — DO NOT add broad parents like `/private/var`
    because on macOS that would also block `/private/var/folders/...`
    which is the user-tmp dir pytest uses. Add the specific sensitive
    sub-paths instead.

    Computed at call time so that tests can change HOME / cwd
    without affecting the never-list semantics.
    """
    home = Path.home()
    return [
        home / ".ssh",
        home / ".gnupg",
        home / ".aws",
        home / ".kube",
        Path("/etc"),
        Path("/System"),
        Path("/private/etc"),
        Path("/var/private"),
        # Note: we DO NOT block `/private/var` broadly — on macOS
        # that would also block `/private/var/folders/...` which is
        # the user-tmp dir used by pytest. Only specific sensitive
        # sub-paths like `/var/private` are blocked.
    ]


def _resolve(path: str) -> Path:
    """Resolve a path via expanduser + realpath."""
    return Path(os.path.expanduser(path)).resolve()


def _path_variants(p: Path) -> list[Path]:
    """Return the resolved path plus the /var ↔ /private/var alias.

    E.g. `/private/var/folders/x` and `/var/folders/x` are the same
    physical directory. A user's allowlist might contain either spelling;
    we try both.
    """
    s = str(p)
    variants = [p]
    # /private/var/... ↔ /var/...
    if s.startswith("/private/var/"):
        variants.append(Path("/var/" + s[len("/private/var/"):]))
    elif s.startswith("/var/"):
        variants.append(Path("/private/var/" + s[len("/var/"):]))
    # /private/tmp ↔ /tmp
    if s == "/private/tmp" or s.startswith("/private/tmp/"):
        rest = s[len("/private/tmp"):]
        variants.append(Path("/tmp" + rest))
    elif s == "/tmp" or s.startswith("/tmp/"):
        rest = s[len("/tmp"):]
        variants.append(Path("/private/tmp" + rest))
    return variants


def _is_in_never_paths(p: Path) -> bool:
    """Check if p (or any of its macOS-alias variants) is in the never list."""
    for variant in _path_variants(p):
        for never in _never_paths():
            try:
                if variant == never or never in variant.parents:
                    return True
            except OSError:
                continue
    return False


def _path_in_list(p: Path, allowed: list[str]) -> bool:
    """Check if p is under any of the allowed paths (after expansion + resolve)."""
    p_variants = _path_variants(p)
    for ap in allowed:
        allowed_abs = expand_home(ap)
        # Also try the alias form of the allowed path
        for allowed_variant in _path_variants(allowed_abs):
            for p_var in p_variants:
                try:
                    p_var.relative_to(allowed_variant)
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
    against cfg.mac.shell_allowlist. The wildcard `*` allows all commands
    (intended for test/dev environments only — never use in production).
    """
    if not command or not command.strip():
        return False
    parts = command.strip().split()
    if not parts:
        return False
    executable = parts[0]
    cfg = get_config()
    if "*" in cfg.mac.shell_allowlist:
        return True
    return executable in cfg.mac.shell_allowlist


__all__ = [
    "check_path_read",
    "check_path_write",
    "check_shell_command",
]

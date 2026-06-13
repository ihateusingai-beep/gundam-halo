"""Per-project filesystem layout.

The on-disk layout is locked by ARCHITECTURE.md §10 (item 5):

    ~/.gundam-halo/projects/<name>/
        project.toml
        memory/
            short-term.jsonl   (T2/M12 follow-up writes here)
            long-term.db       (SQLite + FAISS)
            embeddings/        (cached embedding vectors)
        conversations/         (already used by persistence.py)
        files/                 (files referenced/created by the project)
        tools/                 (per-tool-call audit log)
        checkpoints/           (session resume points — T2)
        state.json             (current session state — T2)

This module owns the path helpers. The rules:

- Path helpers are *pure* (no I/O). They take a project root and
  return a Path. This is what makes them cheap to call from
  hot paths and easy to test.
- ``ensure_layout(root)`` is the *only* function that creates
  directories. It is idempotent — safe to call after a partial
  create / power loss / a project that was bootstrapped by a
  previous toolchain.
- ``archive/`` is intentionally **NOT** created by
  ``ensure_layout`` — that lives in the user's home-level
  ``$HALO_HOME/archive/`` directory, not per-project. The
  ``archive_dir()`` helper is provided for symmetry but returns
  the per-project staging area (``$ROOT/archive/``) which is
  currently unused; the manager archives by ``shutil.move`` of
  the whole project into ``$HALO_HOME/archive/<name>-<ts>/``.

The function ``project_root(home, name)`` is the canonical way to
ask "where on disk does this project live?" and is used by the
manager and by every consumer of project files.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from pathlib import Path

from app.projects.models import ProjectNotFoundError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Root + project paths
# ---------------------------------------------------------------------------


def projects_root(home: Path) -> Path:
    """Return the projects root: ``$HALO_HOME/projects``.

    This directory always exists once the system is bootstrapped.
    We do NOT create it here — the manager / setup flow owns
    ``$HALO_HOME`` directory creation. Tests that need the dir
    can call ``projects_root().mkdir(parents=True, exist_ok=True)``.
    """
    return Path(home) / "projects"


def project_root(home: Path, name: str) -> Path:
    """Return the per-project root: ``$HALO_HOME/projects/<name>``.

    Pure path helper — does not create or check existence. Use
    ``ProjectManager.get(name)`` if you need a ``Project`` model
    or a 404-on-missing semantic.
    """
    return projects_root(home) / name


# ---------------------------------------------------------------------------
# Subdirectory helpers
# ---------------------------------------------------------------------------


def project_toml_path(root: Path) -> Path:
    """``<root>/project.toml`` — the metadata file."""
    return Path(root) / "project.toml"


def memory_dir(root: Path) -> Path:
    """``<root>/memory/`` — short-term JSONL, long-term SQLite, embeddings."""
    return Path(root) / "memory"


def memory_short_term(root: Path) -> Path:
    """``<root>/memory/short-term.jsonl`` — recent conversations append-only."""
    return memory_dir(root) / "short-term.jsonl"


def memory_long_term(root: Path) -> Path:
    """``<root>/memory/long-term.db`` — SQLite, FAISS-ready."""
    return memory_dir(root) / "long-term.db"


def memory_embeddings(root: Path) -> Path:
    """``<root>/memory/embeddings/`` — cached embedding vectors (lazy)."""
    return memory_dir(root) / "embeddings"


def conversations_dir(root: Path) -> Path:
    """``<root>/conversations/`` — one JSON per session id.

    Note: this is also exposed by ``app.projects.persistence``.
    We re-export the helper here so the manager and any
    per-project code can depend on ``workspace`` only.
    """
    return Path(root) / "conversations"


def files_dir(root: Path) -> Path:
    """``<root>/files/`` — files referenced/created by the project."""
    return Path(root) / "files"


def tools_dir(root: Path) -> Path:
    """``<root>/tools/`` — one JSON per tool call id."""
    return Path(root) / "tools"


def checkpoints_dir(root: Path) -> Path:
    """``<root>/checkpoints/`` — session resume points (T2)."""
    return Path(root) / "checkpoints"


def state_file(root: Path) -> Path:
    """``<root>/state.json`` — current session state (T2)."""
    return Path(root) / "state.json"


def archive_dir(root: Path) -> Path:
    """Per-project archive staging: ``<root>/archive/``.

    Currently unused — the manager archives by moving the whole
    project root into ``$HALO_HOME/archive/<name>-<ts>/``. This
    helper is kept for symmetry and for a future "in-place
    archive + soft-delete" feature (T2 candidate).
    """
    return Path(root) / "archive"


# ---------------------------------------------------------------------------
# Layout creation
# ---------------------------------------------------------------------------


# Canonical list of directories that ``ensure_layout`` creates.
# Kept as a list (not set) so the order is stable and the test
# suite can assert on it.
CANONICAL_SUBDIRS: tuple[str, ...] = (
    "memory",
    "conversations",
    "files",
    "tools",
    "checkpoints",
)


def ensure_layout(root: Path) -> None:
    """Create the canonical per-project directory tree.

    Idempotent: safe to call repeatedly, safe to call after a
    crash that left a partial layout. Existing directories are
    left alone — never ``rmtree``d.

    The ``project.toml`` file is *not* created here; that is the
    manager's job (it owns the metadata schema and the atomic
    write pattern).

    Raises:
        OSError: on permission errors or other I/O failures.
    """
    root = Path(root)
    for sub in CANONICAL_SUBDIRS:
        (root / sub).mkdir(parents=True, exist_ok=True)
    logger.debug("ensure_layout: %s ready (subdirs=%s)", root, CANONICAL_SUBDIRS)


def is_workspace_ready(root: Path) -> bool:
    """True if every canonical subdir exists and is a directory.

    Pure check — does NOT create. Used by the manager to decide
    whether ``ensure_layout`` is needed before writing the
    project.toml.
    """
    root = Path(root)
    if not root.is_dir():
        return False
    return all((root / sub).is_dir() for sub in CANONICAL_SUBDIRS)


def list_existing_subdirs(root: Path) -> list[str]:
    """Return the canonical subdir names that currently exist under ``root``.

    Used by the manager's archive step to compute file_count /
    total_bytes for the ``ArchiveSnapshot`` — we walk only the
    canonical dirs and skip the project.toml (it's not a "file
    referenced by the project", it's metadata).

    Returns an empty list if ``root`` does not exist.
    """
    root = Path(root)
    if not root.exists():
        return []
    return [name for name in CANONICAL_SUBDIRS if (root / name).is_dir()]


# ---------------------------------------------------------------------------
# Archive metadata directory
# ---------------------------------------------------------------------------


def archive_root(home: Path) -> Path:
    """``$HALO_HOME/archive/`` — top-level archive directory.

    The manager places archived projects here as
    ``archive/<name>-<timestamp>/``.
    """
    return Path(home) / "archive"


# ---------------------------------------------------------------------------
# Iterators (used by the manager + tests)
# ---------------------------------------------------------------------------


def iter_project_files(root: Path) -> Iterable[Path]:
    """Yield every file under the canonical subdirs of ``root``.

    Used by the archive step to compute total_bytes / file_count
    and (in a future ticket) to build a tar.gz of the project.
    Walks in sorted order for deterministic test output.
    """
    root = Path(root)
    for sub in list_existing_subdirs(root):
        sub_path = root / sub
        for p in sorted(sub_path.rglob("*")):
            if p.is_file():
                yield p


__all__ = [
    "CANONICAL_SUBDIRS",
    "archive_dir",
    "archive_root",
    "checkpoints_dir",
    "conversations_dir",
    "ensure_layout",
    "files_dir",
    "is_workspace_ready",
    "iter_project_files",
    "list_existing_subdirs",
    "memory_dir",
    "memory_embeddings",
    "memory_long_term",
    "memory_short_term",
    "project_root",
    "project_toml_path",
    "projects_root",
    "state_file",
    "tools_dir",
]


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


def raise_missing_project(home: Path, name: str) -> None:
    """Convenience: raise ``ProjectNotFoundError`` with a useful message.

    Used by the manager's get() / archive() / exists()-based checks
    to keep the error path in one place.
    """
    raise ProjectNotFoundError(name=name, root=project_root(home, name))

"""Per-project filesystem layer (M14).

This package owns the on-disk layout, the metadata file
(``project.toml``), and the CRUD/archive operations for one
project at a time. Everything else in M14 (per-project memory
engines, agent wiring, session lifecycle, the full REST CRUD)
builds on top of these three primitives.

Public API
----------
The three modules:

- ``manager`` — ``ProjectManager``: create / list / get / archive /
  exists. Owns the project.toml metadata file and the atomic
  write contract.
- ``workspace`` — pure path helpers + ``ensure_layout``. The
  canonical on-disk layout (memory/, conversations/, files/,
  tools/, checkpoints/).
- ``models`` — Pydantic v2 models: ``Project``, ``ProjectSummary``,
  ``ArchiveSnapshot``, ``ProjectStatus`` enum, and the typed
  exceptions ``ProjectNotFoundError`` / ``ProjectNameError`` /
  ``ProjectExistsError``.

The re-exports here are the *public* surface — anything not
listed is implementation detail and may change between
versions.
"""

from __future__ import annotations

from app.projects.manager import (
    APP_STATE_KEY,
    ProjectExistsError,
    ProjectManager,
    ProjectNameError,
    ProjectNotFoundError,
    get_project_manager,
    init_project_manager,
    reset_project_manager,
    set_project_manager,
)
from app.projects.models import (
    ArchiveSnapshot,
    Project,
    ProjectStatus,
    ProjectSummary,
    now_utc_iso_z,
)
from app.projects.workspace import (
    archive_dir,
    archive_root,
    checkpoints_dir,
    conversations_dir,
    ensure_layout,
    files_dir,
    is_workspace_ready,
    iter_project_files,
    list_existing_subdirs,
    memory_dir,
    memory_embeddings,
    memory_long_term,
    memory_short_term,
    project_root,
    project_toml_path,
    projects_root,
    state_file,
    tools_dir,
)

__all__ = [
    # manager
    "ProjectManager",
    "init_project_manager",
    "set_project_manager",
    "get_project_manager",
    "reset_project_manager",
    "APP_STATE_KEY",
    # models
    "Project",
    "ProjectSummary",
    "ProjectStatus",
    "ArchiveSnapshot",
    "now_utc_iso_z",
    # errors
    "ProjectNotFoundError",
    "ProjectNameError",
    "ProjectExistsError",
    # workspace path helpers
    "projects_root",
    "project_root",
    "project_toml_path",
    "memory_dir",
    "memory_short_term",
    "memory_long_term",
    "memory_embeddings",
    "conversations_dir",
    "files_dir",
    "tools_dir",
    "checkpoints_dir",
    "state_file",
    "archive_dir",
    "archive_root",
    "is_workspace_ready",
    "ensure_layout",
    "list_existing_subdirs",
    "iter_project_files",
]

"""Tests for ``app.projects.workspace`` — per-project FS layout.

Covers:
- ``ensure_layout`` is idempotent and creates only the canonical
  subdirs (no extras).
- The path helpers return absolute paths under the project root.
- A missing project raises the typed ``ProjectNotFoundError``.
- ``iter_project_files`` walks canonical subdirs only (not the
  project.toml) and is deterministic (sorted order).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from app.projects.models import ProjectNotFoundError
from app.projects.workspace import (
    CANONICAL_SUBDIRS,
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
    raise_missing_project,
    state_file,
    tools_dir,
)

# ---------------------------------------------------------------------------
# ensure_layout
# ---------------------------------------------------------------------------


def test_ensure_layout_creates_canonical_subdirs(tmp_path: Path):
    root = tmp_path / "demo"
    ensure_layout(root)
    for sub in CANONICAL_SUBDIRS:
        assert (root / sub).is_dir(), f"missing subdir {sub!r}"
    # And ONLY the canonical ones — no surprise extra directories.
    actual = {p.name for p in root.iterdir() if p.is_dir()}
    assert actual == set(CANONICAL_SUBDIRS)


def test_ensure_layout_is_idempotent(tmp_path: Path):
    root = tmp_path / "demo"
    ensure_layout(root)
    ensure_layout(root)
    ensure_layout(root)  # third call, should still be fine
    actual = {p.name for p in root.iterdir() if p.is_dir()}
    assert actual == set(CANONICAL_SUBDIRS)


def test_ensure_layout_creates_intermediate_dirs(tmp_path: Path):
    # If the parent doesn't exist, ensure_layout should still work
    # (the manager calls mkdir on the root first, so this is
    # belt-and-braces).
    root = tmp_path / "deep" / "nested" / "demo"
    ensure_layout(root)
    assert root.is_dir()


def test_ensure_layout_does_not_create_project_toml(tmp_path: Path):
    """``project.toml`` is the manager's job, not the workspace's."""
    root = tmp_path / "demo"
    ensure_layout(root)
    assert not (root / "project.toml").exists()


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "fn,expected",
    [
        (project_toml_path, "project.toml"),
        (memory_dir, "memory"),
        (memory_short_term, "memory/short-term.jsonl"),
        (memory_long_term, "memory/long-term.db"),
        (memory_embeddings, "memory/embeddings"),
        (conversations_dir, "conversations"),
        (files_dir, "files"),
        (tools_dir, "tools"),
        (checkpoints_dir, "checkpoints"),
        (state_file, "state.json"),
        (archive_dir, "archive"),
    ],
)
def test_path_helpers_return_paths_under_root(tmp_path: Path, fn, expected: str):
    """Every per-project helper returns <root>/<expected>."""
    p = fn(tmp_path)
    assert p == tmp_path / expected
    # All helpers should return absolute paths (they have a root
    # argument that may be relative, so we resolve before checking).
    assert (tmp_path / expected).resolve().is_absolute()


def test_projects_root_under_home(tmp_path: Path):
    assert projects_root(tmp_path) == tmp_path / "projects"


def test_project_root_under_home(tmp_path: Path):
    assert project_root(tmp_path, "demo") == tmp_path / "projects" / "demo"


def test_archive_root_under_home(tmp_path: Path):
    assert archive_root(tmp_path) == tmp_path / "archive"


# ---------------------------------------------------------------------------
# is_workspace_ready
# ---------------------------------------------------------------------------


def test_is_workspace_ready_false_for_missing_root(tmp_path: Path):
    assert is_workspace_ready(tmp_path / "nope") is False


def test_is_workspace_ready_true_after_ensure(tmp_path: Path):
    root = tmp_path / "demo"
    ensure_layout(root)
    assert is_workspace_ready(root) is True


def test_is_workspace_ready_false_for_partial_layout(tmp_path: Path):
    """If any canonical subdir is missing, ready == False."""
    root = tmp_path / "demo"
    root.mkdir()
    (root / "memory").mkdir()
    # intentionally not creating the others
    assert is_workspace_ready(root) is False


# ---------------------------------------------------------------------------
# list_existing_subdirs
# ---------------------------------------------------------------------------


def test_list_existing_subdirs_empty_for_missing(tmp_path: Path):
    assert list_existing_subdirs(tmp_path / "nope") == []


def test_list_existing_subdirs_returns_canonical_only(tmp_path: Path):
    root = tmp_path / "demo"
    root.mkdir()
    (root / "memory").mkdir()
    (root / "conversations").mkdir()
    (root / "extra-junk").mkdir()  # not canonical, should be ignored
    found = list_existing_subdirs(root)
    assert sorted(found) == ["conversations", "memory"]


# ---------------------------------------------------------------------------
# iter_project_files
# ---------------------------------------------------------------------------


def test_iter_project_files_empty_when_no_subdirs(tmp_path: Path):
    root = tmp_path / "demo"
    root.mkdir()
    assert list(iter_project_files(root)) == []


def test_iter_project_files_walks_canonical_only(tmp_path: Path):
    root = tmp_path / "demo"
    ensure_layout(root)
    # Drop a file in each canonical subdir + an extra one in a
    # non-canonical subdir (which should be ignored).
    (root / "memory" / "a.jsonl").write_text("a")
    (root / "tools" / "b.json").write_text("b")
    (root / "files" / "c.txt").write_text("c")
    (root / "extra-junk").mkdir()
    (root / "extra-junk" / "ignore.txt").write_text("ignore")

    files = [p.name for p in iter_project_files(root)]
    assert sorted(files) == ["a.jsonl", "b.json", "c.txt"]


def test_iter_project_files_is_sorted(tmp_path: Path):
    """Stable, sorted order — matters for deterministic test output
    and for the archive step's file_count / total_bytes walk."""
    root = tmp_path / "demo"
    ensure_layout(root)
    (root / "files").mkdir(exist_ok=True)
    for name in ["z.txt", "a.txt", "m.txt"]:
        (root / "files" / name).write_text("x")
    files = [p.name for p in iter_project_files(root)]
    assert files == ["a.txt", "m.txt", "z.txt"]


# ---------------------------------------------------------------------------
# raise_missing_project
# ---------------------------------------------------------------------------


def test_raise_missing_project_raises_typed_error(tmp_path: Path):
    with pytest.raises(ProjectNotFoundError) as exc:
        raise_missing_project(tmp_path, "ghost")
    assert exc.value.name == "ghost"
    assert exc.value.root == tmp_path / "projects" / "ghost"
    assert "ghost" in str(exc.value)
    assert "not found" in str(exc.value).lower()

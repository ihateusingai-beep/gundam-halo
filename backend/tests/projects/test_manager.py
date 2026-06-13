"""Tests for ``app.projects.manager`` — the on-disk CRUD + archive.

These tests use a fresh ``tmp_path`` per test (autouse fixture
``default_test_config`` in ``tests/conftest.py`` already points
``HALO_HOME`` there) and instantiate ``ProjectManager(home=tmp_path)``
directly. They do NOT boot the FastAPI app — the API integration
is covered by ``test_projects_health.py`` (a separate test file
under ``tests/api/``).

Categories:
- create (fresh, idempotent re-create, default vs. custom args)
- list (empty, sorted, skips partial / corrupt dirs)
- get (happy path, raises ``ProjectNotFoundError`` for missing)
- exists (true / false / False for invalid name)
- archive (happy path + post-archive existence + file_count / total_bytes)
- name validation (good + bad + reserved)
- atomicity under simulated crash (os.replace failure)
- singleton wiring (get / set / reset on app.state)
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from app.projects.manager import (
    APP_STATE_KEY,
    ProjectManager,
    ProjectNameError,
    ProjectNotFoundError,
    _atomic_write_text,
    get_project_manager,
    init_project_manager,
    reset_project_manager,
    set_project_manager,
)
from app.projects.models import (
    ProjectStatus,
)
from app.projects.workspace import (
    CANONICAL_SUBDIRS,
    project_toml_path,
)
from fastapi import FastAPI

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def home(tmp_path: Path) -> Path:
    """Per-test home. The conftest autouse fixture already points
    ``HALO_HOME`` at ``tmp_path`` so any ``get_config()`` calls inside
    the manager use the same directory."""
    return tmp_path


@pytest.fixture
def manager(home: Path) -> ProjectManager:
    return ProjectManager(home=home)


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


def test_create_writes_project_toml_and_layout(manager: ProjectManager, home: Path):
    p = manager.create("fix-jarvis")
    root = home / "projects" / "fix-jarvis"
    assert root.is_dir()
    assert (root / "project.toml").is_file()
    for sub in CANONICAL_SUBDIRS:
        assert (root / sub).is_dir(), f"missing subdir {sub}"
    # Default values
    assert p.name == "fix-jarvis"
    assert p.status == ProjectStatus.ACTIVE
    assert p.agent_type == "native_react"
    assert p.theme_override is None
    assert p.default_paths == []
    assert p.allowed_apps == []
    # created_at is ISO 8601 Z
    assert p.created_at.endswith("Z")


def test_create_with_custom_args(manager: ProjectManager):
    p = manager.create(
        "jarvis-b",
        agent_type="orchestrator",
        default_paths=["~/x/", "~/y/"],
        theme_override="gundam-ntd",
        allowed_apps=["com.example"],
    )
    assert p.agent_type == "orchestrator"
    assert p.default_paths == ["~/x/", "~/y/"]
    assert p.theme_override == "gundam-ntd"
    assert p.allowed_apps == ["com.example"]


def test_create_is_idempotent_returns_existing(manager: ProjectManager, home: Path):
    """Re-creating an existing project is a no-op + warning log."""
    p1 = manager.create("demo", agent_type="native_react")
    p2 = manager.create("demo", agent_type="orchestrator")  # would-be overwrite
    # Same project, agent_type NOT changed (no overwrite).
    assert p1.name == p2.name
    assert p2.agent_type == "native_react"
    # And the on-disk file is the original — no corruption.
    loaded = manager.get("demo")
    assert loaded.agent_type == "native_react"


def test_create_publishes_project_created_event(manager: ProjectManager):
    """The manager publishes EventType.PROJECT_CREATED on the bus."""
    from app.core.events import EventType, get_event_bus

    bus = get_event_bus()
    received: list = []

    def sub(evt):
        received.append(evt)

    bus.subscribe(EventType.PROJECT_CREATED, sub)
    try:
        manager.create("evented")
    finally:
        bus.unsubscribe(EventType.PROJECT_CREATED, sub)
    assert received, "expected at least one PROJECT_CREATED event"
    payload = received[-1].data
    assert payload["name"] == "evented"
    assert payload["agent_type"] == "native_react"


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


def test_list_empty_when_no_projects(manager: ProjectManager):
    assert manager.list() == []


def test_list_returns_summaries(manager: ProjectManager):
    manager.create("ab")
    manager.create("bc")
    manager.create("cd")
    summaries = manager.list()
    assert [s.name for s in summaries] == ["ab", "bc", "cd"]
    for s in summaries:
        assert s.status == ProjectStatus.ACTIVE
        assert s.agent_type == "native_react"
        assert s.created_at.endswith("Z")


def test_list_skips_dirs_without_project_toml(manager: ProjectManager, home: Path):
    manager.create("good")
    # A stray dir with no project.toml — should be skipped, not raised.
    (home / "projects" / "stray").mkdir()
    names = [s.name for s in manager.list()]
    assert names == ["good"]


def test_list_skips_corrupt_project_toml(manager: ProjectManager, home: Path):
    manager.create("good")
    (home / "projects" / "bad").mkdir()
    (home / "projects" / "bad" / "project.toml").write_text("this is = = not toml ===")
    names = [s.name for s in manager.list()]
    assert names == ["good"]


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------


def test_get_returns_project(manager: ProjectManager):
    p = manager.create("demo")
    loaded = manager.get("demo")
    assert loaded == p
    assert loaded.name == "demo"
    assert loaded.status == ProjectStatus.ACTIVE


def test_get_raises_for_missing(manager: ProjectManager):
    with pytest.raises(ProjectNotFoundError) as exc:
        manager.get("ghost")
    assert exc.value.name == "ghost"
    assert "not found" in str(exc.value).lower()


def test_get_raises_for_invalid_name(manager: ProjectManager):
    with pytest.raises(ProjectNameError):
        manager.get("Bad")  # uppercase


# ---------------------------------------------------------------------------
# exists
# ---------------------------------------------------------------------------


def test_exists_true_after_create(manager: ProjectManager):
    manager.create("demo")
    assert manager.exists("demo") is True


def test_exists_false_for_missing(manager: ProjectManager):
    assert manager.exists("ghost") is False


def test_exists_false_for_invalid_name(manager: ProjectManager):
    """Invalid name -> exists() returns False (doesn't raise)."""
    assert manager.exists("Bad") is False
    assert manager.exists("default") is False  # reserved


def test_exists_false_for_stray_dir_without_toml(manager: ProjectManager, home: Path):
    (home / "projects" / "stray").mkdir()
    assert manager.exists("stray") is False


# ---------------------------------------------------------------------------
# count
# ---------------------------------------------------------------------------


def test_count_reflects_on_disk_state(manager: ProjectManager):
    assert manager.count() == 0
    manager.create("ab")
    manager.create("bc")
    assert manager.count() == 2
    manager.archive("ab")
    assert manager.count() == 1


# ---------------------------------------------------------------------------
# archive
# ---------------------------------------------------------------------------


def test_archive_moves_project_to_archive_dir(manager: ProjectManager, home: Path):
    manager.create("demo")
    snapshot = manager.archive("demo")
    assert snapshot.project_name == "demo"
    assert snapshot.archived_at.endswith("Z")
    assert snapshot.snapshot_path.is_dir()
    assert snapshot.snapshot_path.parent == home / "archive"
    # The archived snapshot contains the original project.toml + subdirs.
    assert (snapshot.snapshot_path / "project.toml").is_file()
    for sub in CANONICAL_SUBDIRS:
        assert (snapshot.snapshot_path / sub).is_dir()
    # And the original location is gone.
    assert not (home / "projects" / "demo").exists()
    # And the manager no longer sees it.
    assert manager.exists("demo") is False
    assert manager.count() == 0


def test_archive_counts_files_and_bytes(manager: ProjectManager, home: Path):
    manager.create("demo")
    root = home / "projects" / "demo"
    # Drop a few files of known sizes
    (root / "memory").mkdir(exist_ok=True)  # ensure_layout did this
    (root / "memory" / "a.jsonl").write_bytes(b"x" * 10)
    (root / "tools" / "b.json").write_bytes(b"y" * 20)
    (root / "files" / "c.txt").write_bytes(b"z" * 30)

    snapshot = manager.archive("demo")
    assert snapshot.file_count == 3
    assert snapshot.total_bytes == 60


def test_archive_raises_for_missing(manager: ProjectManager):
    with pytest.raises(ProjectNotFoundError):
        manager.archive("ghost")


def test_archive_publishes_event(manager: ProjectManager):
    from app.core.events import EventType, get_event_bus

    manager.create("evented")
    bus = get_event_bus()
    received: list = []

    def sub(evt):
        received.append(evt)

    bus.subscribe(EventType.PROJECT_ARCHIVED, sub)
    try:
        manager.archive("evented")
    finally:
        bus.unsubscribe(EventType.PROJECT_ARCHIVED, sub)
    assert received, "expected at least one PROJECT_ARCHIVED event"
    payload = received[-1].data
    assert payload["name"] == "evented"
    assert payload["file_count"] == 0
    assert payload["total_bytes"] == 0
    assert "snapshot" in payload


def test_archive_after_archive_get_raises(manager: ProjectManager):
    manager.create("demo")
    manager.archive("demo")
    with pytest.raises(ProjectNotFoundError):
        manager.get("demo")


# ---------------------------------------------------------------------------
# name validation (at the manager boundary)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad,why",
    [
        ("a", "too short"),
        ("A", "uppercase"),
        ("abc_def", "underscore"),
        ("", "empty"),
    ],
)
def test_create_rejects_invalid_name(manager: ProjectManager, bad: str, why: str):
    with pytest.raises(ProjectNameError) as exc:
        manager.create(bad)
    msg = str(exc.value).lower()
    assert (
        "match" in msg
        or "invalid" in msg
        or "lowercase" in msg
    )


@pytest.mark.parametrize(
    "reserved",
    ["default", "global", "archive", "templates", "rm"],
)
def test_create_rejects_reserved_name(manager: ProjectManager, reserved: str):
    """Reserved names that pass the regex (e.g. ``default``) get a
    specific 'reserved' error. Names like ``.mavis`` are also in the
    reserved set but they're caught by the regex first — covered
    by the regex test. ``rm`` is a defense-in-depth shell-token name
    (would be a footgun in ``rm -rf ~/.gundam-halo/projects/*``)."""
    with pytest.raises(ProjectNameError) as exc:
        manager.create(reserved)
    assert "reserved" in str(exc.value).lower()


def test_create_rejects_non_string_name(manager: ProjectManager):
    with pytest.raises(ProjectNameError):
        manager.create(123)  # type: ignore[arg-type]


def test_create_rejects_path_traversal(manager: ProjectManager):
    """Names with ``/`` or ``..`` must be rejected — they're not in
    the regex, so the manager's _validate_name raises."""
    with pytest.raises(ProjectNameError):
        manager.create("../escape")


# ---------------------------------------------------------------------------
# Atomicity under simulated crash
# ---------------------------------------------------------------------------


def test_atomic_write_leaves_no_tmp_file_on_success(tmp_path: Path):
    target = tmp_path / "f.txt"
    _atomic_write_text(target, "hello")
    assert target.read_text() == "hello"
    # No leftover .tmp files
    leftovers = list(tmp_path.glob(".f.txt.*.tmp"))
    assert leftovers == []


def test_atomic_write_removes_tmp_on_failure(tmp_path: Path):
    """If the inner write raises, the tmp file is removed (no garbage)."""
    target = tmp_path / "f.txt"
    with patch("os.replace", side_effect=OSError("simulated crash")):
        with pytest.raises(OSError):
            _atomic_write_text(target, "boom")
    # Tmp removed
    leftovers = list(tmp_path.glob(".f.txt.*.tmp"))
    assert leftovers == []
    # Target never created
    assert not target.exists()


def test_atomic_write_preserves_existing_file_on_failure(tmp_path: Path):
    """If we crash mid-write, the original file is unchanged."""
    target = tmp_path / "f.txt"
    target.write_text("original")
    with patch("os.replace", side_effect=OSError("simulated crash")):
        with pytest.raises(OSError):
            _atomic_write_text(target, "new")
    # Original content intact
    assert target.read_text() == "original"


def test_create_atomicity_preserves_existing_project(
    manager: ProjectManager, home: Path
):
    """Simulate a crash during project.toml write — original project
    is unchanged."""
    manager.create("demo")
    original_path = project_toml_path(home / "projects" / "demo")
    original_content = original_path.read_text()

    with patch("os.replace", side_effect=OSError("simulated crash")):
        # The atomic write will fail, but the existing project
        # is not corrupted. We call _atomic_write_text directly
        # because the manager's `create` flow short-circuits on
        # `exists()`.
        with pytest.raises(OSError):
            _atomic_write_text(original_path, "would-be overwrite")
    # Original file intact
    assert original_path.read_text() == original_content
    # The project is still loadable
    loaded = manager.get("demo")
    assert loaded.name == "demo"


# ---------------------------------------------------------------------------
# Singleton wiring (FastAPI app.state)
# ---------------------------------------------------------------------------


def test_get_project_manager_raises_when_not_initialised():
    app = FastAPI()
    with pytest.raises(RuntimeError) as exc:
        get_project_manager(app)
    assert "not initialised" in str(exc.value).lower()


def test_set_and_get_project_manager_roundtrip():
    app = FastAPI()
    pm = init_project_manager(home=Path("/tmp/fake-home"))
    set_project_manager(app, pm)
    assert get_project_manager(app) is pm


def test_reset_project_manager_clears_state():
    app = FastAPI()
    pm = init_project_manager(home=Path("/tmp/fake-home"))
    set_project_manager(app, pm)
    reset_project_manager(app)
    with pytest.raises(RuntimeError):
        get_project_manager(app)


def test_app_state_key_is_project_manager():
    """The attribute name on app.state is part of the public contract."""
    assert APP_STATE_KEY == "project_manager"

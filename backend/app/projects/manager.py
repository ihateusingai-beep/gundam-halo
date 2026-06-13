"""ProjectManager — create / list / get / archive projects on disk.

This is the single source of truth for the per-project filesystem
layer. It owns:

- the metadata file ``project.toml`` (Pydantic ``Project`` round-trip)
- the canonical directory layout (delegated to ``workspace.py``)
- the archive step (``$HALO_HOME/projects/<name>/`` →
  ``$HALO_HOME/archive/<name>-<timestamp>/``)

Lifespan
--------
The manager is a singleton per process, created in the FastAPI
``lifespan`` and shared by every request handler that needs it
(``T2`` will mount the CRUD endpoints). It is **not** a global
module-level variable — that pattern caused subtle test isolation
problems in earlier M-series tickets (see STATUS-2026-06-13 §"36
hidden execution-order deps"). The singleton is held in
``app.state.project_manager`` and exposed via
``get_project_manager(app)``.

Atomicity
---------
Every write goes through ``_atomic_write_text`` (tmp file in the
same directory → ``os.replace``). This is the same pattern used
by ``app/projects/persistence.py`` and the M13 setup wizard. The
test suite asserts atomicity by simulating a crash mid-write
(``os.replace`` mocked to raise) and verifying the original file
is unchanged.

Idempotency
-----------
``create(name)`` is idempotent: re-creating an existing project
is a no-op + a warning log. The returned ``Project`` is the
existing one, not a new one. This matches the lock in the
task description: *"re-create an existing project is a no-op +
log warning, do NOT overwrite"*.
"""

from __future__ import annotations

import builtins
import json
import logging
import os
import shutil
import tempfile
import tomllib
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI
from pydantic import ValidationError

from app.core.events import EventType, get_event_bus
from app.projects.models import (
    PROJECT_NAME_PATTERN,
    RESERVED_PROJECT_NAMES,
    ArchiveSnapshot,
    Project,
    ProjectExistsError,
    ProjectNameError,
    ProjectNotFoundError,
    ProjectStatus,
    ProjectSummary,
    now_utc_iso_z,
)
from app.projects.workspace import (
    archive_root,
    ensure_layout,
    iter_project_files,
    project_root,
    project_toml_path,
    projects_root,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public errors (re-exported at the package level for convenience)
# ---------------------------------------------------------------------------

__all__ = [
    "ProjectManager",
    "init_project_manager",
    "set_project_manager",
    "get_project_manager",
    "reset_project_manager",
    "APP_STATE_KEY",
    "Project",
    "ProjectSummary",
    "ProjectStatus",
    "ArchiveSnapshot",
    "ProjectNotFoundError",
    "ProjectNameError",
    "ProjectExistsError",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_name(name: str) -> str:
    """Validate a project name against the regex and reserved set.

    Raises:
        ProjectNameError: if the name is invalid or reserved.
    """
    if not isinstance(name, str):
        raise ProjectNameError(f"project name must be str, got {type(name).__name__}")
    if not PROJECT_NAME_PATTERN.match(name):
        raise ProjectNameError(
            f"project name {name!r} does not match {PROJECT_NAME_PATTERN.pattern!r}"
            " (lowercase letters/digits/hyphens, must start with a "
            "letter or digit, 2-31 chars)"
        )
    if name in RESERVED_PROJECT_NAMES:
        raise ProjectNameError(
            f"project name {name!r} is reserved; pick something else"
        )
    return name


def _atomic_write_text(path: Path, body: str, *, encoding: str = "utf-8") -> None:
    """Write *body* to *path* atomically.

    - creates the parent directory if it doesn't exist
    - writes to a tmp file in the same directory (so ``os.replace``
      is atomic on the same filesystem)
    - ``flush`` + ``os.fsync`` to push bytes to disk before the
      rename — protects against power loss between the write and
      the rename (see the M13 setup wizard for the same pattern)
    - on any error, removes the tmp file before re-raising
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_str = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding=encoding) as f:
            f.write(body)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                # fsync can fail on some filesystems (e.g. network
                # mounts); the data is still on the local page
                # cache, so we don't tear down the write over it.
                logger.debug("fsync failed for %s; continuing", tmp_str)
        os.replace(tmp_str, path)
    except Exception:
        try:
            os.unlink(tmp_str)
        except OSError:
            pass
        raise


def _toml_escape_string(s: str) -> str:
    """Escape a string for a TOML basic string literal.

    We use JSON-style escaping because the rules are similar
    (control chars, quote, backslash) and the result is
    stdlib-verified safe. The output is wrapped in double
    quotes by the caller.
    """
    # json.dumps gives us correct escaping for " \\ and control
    # characters, plus unicode preservation. We strip the
    # surrounding quotes and re-add them so the JSON output
    # is TOML-compatible.
    return json.dumps(s, ensure_ascii=False)


def _dump_project_toml(project: Project) -> str:
    """Serialise a ``Project`` to a TOML string under the ``[project]`` table.

    We write the file ourselves instead of using ``tomlkit`` for
    one reason: TOML v1.0 (which Python's ``tomllib`` parses)
    has no ``null`` type. The ARCHITECTURE spec asks for
    ``theme_override = null`` ("use user default") but ``tomllib``
    rejects it. The cleanest workaround is to *omit* the key
    when there's no override and *write the string* when there
    is one — semantically equivalent for the load path, and
    Pydantic's ``Optional[str]`` accepts both.

    We also do our own string formatting because we control the
    schema: the project.toml only has 7 known fields, all of
    which are scalars or string lists. Hand-formatting keeps
    the output stable, predictable, and free of tomlkit's
    quote-style surprises. The Pydantic ``Project`` model
    re-validates every read, so any drift in the format
    surfaces immediately as a test failure.
    """
    lines: list[str] = []
    lines.append("[project]")
    lines.append(f"schema_version = {int(project.schema_version)}")
    lines.append(f"name = {_toml_escape_string(project.name)}")
    lines.append(f"created_at = {_toml_escape_string(project.created_at)}")
    lines.append(f"status = {_toml_escape_string(project.status.value)}")
    lines.append(f"agent_type = {_toml_escape_string(project.agent_type)}")

    # theme_override — omit the key when None so the load path
    # can read it back as None. (See docstring above for why.)
    if project.theme_override is not None:
        lines.append(
            f"theme_override = {_toml_escape_string(project.theme_override)}"
        )

    # Lists — emit as inline arrays. Empty list = "[]".
    def _toml_array(values: list[str]) -> str:
        if not values:
            return "[]"
        return "[ " + ", ".join(_toml_escape_string(v) for v in values) + " ]"

    lines.append(f"default_paths = {_toml_array(project.default_paths)}")
    lines.append(f"allowed_apps = {_toml_array(project.allowed_apps)}")
    lines.append("")  # trailing newline so the file is POSIX-clean
    return "\n".join(lines)


def _load_project_toml(path: Path) -> Project:
    """Load a ``Project`` from a ``project.toml`` file.

    Raises:
        FileNotFoundError: if the file doesn't exist
        ValidationError: if the file is malformed or has unknown fields
    """
    path = Path(path)
    with open(path, "rb") as f:
        raw = tomllib.load(f)

    proj_dict = raw.get("project", {})

    # The Pydantic model expects a flat dict (status as string,
    # not enum). Build it explicitly so we don't have to worry
    # about tomlkit's quirks inside `model_validate`.
    schema_version = proj_dict.get("schema_version", 1)
    if not isinstance(schema_version, int):
        # Pydantic coerces ints; reject floats / strings loudly.
        raise ValidationError.from_exception_data(
            "Project",
            [
                {
                    "type": "int_parsing",
                    "loc": ("schema_version",),
                    "input": schema_version,
                }
            ],
        )

    return Project.model_validate(
        {
            "schema_version": schema_version,
            "name": proj_dict.get("name", path.parent.name),
            "created_at": proj_dict.get("created_at", ""),
            "status": proj_dict.get("status", "active"),
            "agent_type": proj_dict.get("agent_type", "native_react"),
            "theme_override": proj_dict.get("theme_override", None),
            "default_paths": list(proj_dict.get("default_paths", []) or []),
            "allowed_apps": list(proj_dict.get("allowed_apps", []) or []),
        }
    )


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------


class ProjectManager:
    """Create / list / get / archive projects on disk.

    Stateless apart from the ``home`` Path. All public methods
    take the project name as a positional argument so the manager
    can be safely re-used across requests without leaking state
    between them.
    """

    def __init__(self, home: Path) -> None:
        self.home = Path(home).resolve()
        # Eagerly create $HALO_HOME/projects/ so subsequent
        # `list()` calls don't need to. We do NOT create the
        # full per-project layout here — that's the per-project
        # job in `create()`.
        projects_root(self.home).mkdir(parents=True, exist_ok=True)
        logger.debug("ProjectManager ready: home=%s", self.home)

    # ----- create / list / get -----

    def create(
        self,
        name: str,
        agent_type: str = "native_react",
        default_paths: builtins.list[str] | None = None,
        theme_override: str | None = None,
        allowed_apps: builtins.list[str] | None = None,
    ) -> Project:
        """Create a new project, or return the existing one.

        Idempotent: re-creating an existing project is a no-op +
        warning log. Does NOT overwrite — if you need to update
        metadata, edit ``project.toml`` via the manager's helpers
        (T2 will add ``update()``).

        Returns the freshly created (or pre-existing) ``Project``.
        """
        _validate_name(name)
        root = project_root(self.home, name)

        if root.exists():
            # Idempotent path — load the existing project.toml
            # (if any) and return it. We do NOT touch the on-disk
            # state. If a directory exists but has no project.toml
            # we treat it as a partial / corrupt project and let
            # the existing on-disk shape speak for itself by
            # returning a default model.
            logger.warning(
                "ProjectManager.create: project %r already exists at %s; "
                "returning existing (no-op, no overwrite)",
                name,
                root,
            )
            if (project_toml_path(root)).exists():
                return _load_project_toml(project_toml_path(root))
            # No project.toml — fabricate a minimal Project so the
            # caller can decide what to do. This shouldn't happen
            # in practice because ensure_layout() is the only
            # writer and it always runs alongside project.toml.
            return Project(
                name=name,
                created_at=now_utc_iso_z(),
                agent_type=agent_type,
                status=ProjectStatus.ACTIVE,
                theme_override=theme_override,
                default_paths=list(default_paths or []),
                allowed_apps=list(allowed_apps or []),
            )

        # Fresh project: build the layout + write the metadata
        # file atomically.
        ensure_layout(root)

        project = Project(
            name=name,
            created_at=now_utc_iso_z(),
            status=ProjectStatus.ACTIVE,
            agent_type=agent_type,
            theme_override=theme_override,
            default_paths=list(default_paths or []),
            allowed_apps=list(allowed_apps or []),
        )
        _atomic_write_text(project_toml_path(root), _dump_project_toml(project))
        logger.info("ProjectManager.create: created %r at %s", name, root)

        # Event — best-effort; never let the bus take down a
        # create. The status field on the event payload lets
        # subscribers (Telegram bot, cockpit live feed) refresh
        # their project list.
        try:
            get_event_bus().publish(
                EventType.PROJECT_CREATED,
                {"name": name, "agent_type": agent_type, "root": str(root)},
            )
        except Exception as e:  # pragma: no cover — defensive
            logger.debug("ProjectManager.create: event bus publish failed: %s", e)

        return project

    def list(self) -> builtins.list[ProjectSummary]:
        """Return ``ProjectSummary`` for every project on disk.

        Skips directories that don't have a ``project.toml``
        (these are partial / corrupt — logged at warning level).
        Sorted by name for stable test output and predictable UI
        ordering.
        """
        root = projects_root(self.home)
        if not root.exists():
            return []

        out: list[ProjectSummary] = []
        for entry in sorted(root.iterdir()):
            if not entry.is_dir():
                continue
            toml_path = project_toml_path(entry)
            if not toml_path.exists():
                logger.warning(
                    "ProjectManager.list: %s has no project.toml; skipping",
                    entry,
                )
                continue
            try:
                p = _load_project_toml(toml_path)
            except (ValidationError, tomllib.TOMLDecodeError, OSError) as e:
                logger.warning(
                    "ProjectManager.list: failed to load %s: %s; skipping",
                    toml_path,
                    e,
                )
                continue
            out.append(
                ProjectSummary(
                    name=p.name,
                    status=p.status,
                    created_at=p.created_at,
                    agent_type=p.agent_type,
                )
            )
        return out

    def get(self, name: str) -> Project:
        """Load a single project by name.

        Raises:
            ProjectNotFoundError: if the project doesn't exist or
                has no ``project.toml``.
        """
        _validate_name(name)
        root = project_root(self.home, name)
        if not root.is_dir():
            raise ProjectNotFoundError(name=name, root=root)
        toml_path = project_toml_path(root)
        if not toml_path.exists():
            raise ProjectNotFoundError(name=name, root=root)
        return _load_project_toml(toml_path)

    def exists(self, name: str) -> bool:
        """True if the project root + project.toml both exist."""
        try:
            _validate_name(name)
        except ProjectNameError:
            return False
        root = project_root(self.home, name)
        if not root.is_dir():
            return False
        if not project_toml_path(root).exists():
            return False
        return True

    def count(self) -> int:
        """Count of projects on disk. Used by the /api/projects health probe."""
        return len(self.list())

    # ----- archive -----

    def archive(self, name: str) -> ArchiveSnapshot:
        """Move the project into ``$HALO_HOME/archive/<name>-<ts>/``.

        Returns an ``ArchiveSnapshot`` with the new path + a
        ``file_count`` / ``total_bytes`` summary. The original
        project root is removed by ``shutil.move`` (it moves
        across the filesystem boundary when ``projects/`` and
        ``archive/`` are on the same disk, otherwise it falls
        back to copy + delete — both safe).

        After the move, the project is "archived" from the
        user's perspective: ``list()`` no longer returns it,
        ``exists()`` returns False, and ``get()`` raises
        ``ProjectNotFoundError``. If the user wants the project
        back, they re-create it (and the data is sitting in
        archive/).

        Raises:
            ProjectNotFoundError: if the project doesn't exist.
        """
        _validate_name(name)
        root = project_root(self.home, name)
        if not root.is_dir():
            raise ProjectNotFoundError(name=name, root=root)

        # Compute stats BEFORE the move so the on-disk file_count
        # is captured. We walk the canonical subdirs only.
        files = list(iter_project_files(root))
        file_count = len(files)
        total_bytes = sum(p.stat().st_size for p in files if p.is_file())

        # Destination: $HALO_HOME/archive/<name>-YYYYMMDD-HHMMSS/
        archive_dir_root = archive_root(self.home)
        archive_dir_root.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        dest = archive_dir_root / f"{name}-{ts}"
        if dest.exists():
            # Defensive: collision avoidance. Append a counter.
            counter = 1
            while True:
                candidate = archive_dir_root / f"{name}-{ts}-{counter}"
                if not candidate.exists():
                    dest = candidate
                    break
                counter += 1

        shutil.move(str(root), str(dest))
        logger.info("ProjectManager.archive: %r -> %s (%d files, %d bytes)",
                    name, dest, file_count, total_bytes)

        # Best-effort event publish.
        try:
            get_event_bus().publish(
                EventType.PROJECT_ARCHIVED,
                {
                    "name": name,
                    "snapshot": str(dest),
                    "file_count": file_count,
                    "total_bytes": total_bytes,
                },
            )
        except Exception as e:  # pragma: no cover — defensive
            logger.debug("ProjectManager.archive: event bus publish failed: %s", e)

        return ArchiveSnapshot(
            project_name=name,
            archived_at=now_utc_iso_z(),
            snapshot_path=dest,
            file_count=file_count,
            total_bytes=total_bytes,
        )

    # ----- internals exposed for the tests -----

    def _home(self) -> Path:
        return self.home


# ---------------------------------------------------------------------------
# Singleton wiring (FastAPI lifespan)
# ---------------------------------------------------------------------------

# State attribute name on FastAPI. Kept as a constant so T2's
# route handlers can read it without string-typing.
APP_STATE_KEY = "project_manager"


def get_project_manager(app: FastAPI) -> ProjectManager:
    """Return the ``ProjectManager`` stored on ``app.state``.

    Raises:
        RuntimeError: if the manager hasn't been initialised.
        Tests should call ``reset_project_manager()`` between
        cases to avoid the singleton leak (the same pattern
        used by ``get_channel_manager()``).
    """
    # FastAPI exposes request.app; we accept that. Reading from
    # `app.state.<key>` is the canonical way to reach lifespan
    # singletons in modern FastAPI.
    pm = getattr(app.state, APP_STATE_KEY, None)
    if pm is None:
        raise RuntimeError(
            "ProjectManager is not initialised; "
            "is the FastAPI lifespan running? (see app.main.lifespan)"
        )
    return pm


def reset_project_manager(app: FastAPI) -> None:
    """Clear the manager — for tests only."""
    if hasattr(app.state, APP_STATE_KEY):
        try:
            delattr(app.state, APP_STATE_KEY)
        except AttributeError:
            pass


def init_project_manager(home: Path) -> ProjectManager:
    """Construct a manager bound to *home*. Used by the lifespan."""
    return ProjectManager(home=home)


def set_project_manager(app: FastAPI, manager: ProjectManager) -> None:
    """Attach *manager* to ``app.state`` under :data:`APP_STATE_KEY`.

    Called by the lifespan in :mod:`app.main`. Exposed so tests
    that build a FastAPI ``TestClient(app)`` without booting the
    real lifespan (e.g. a unit test that wants to inject a
    manager pointing at ``tmp_path``) can wire it directly.
    """
    setattr(app.state, APP_STATE_KEY, manager)

"""Pydantic models for the per-project filesystem layer.

The project manager (`manager.py`) and the workspace helpers
(`workspace.py`) are the only writers of `project.toml` — this
module defines the schema that every read/write of that file must
go through.

Why Pydantic and not the existing dataclass `Config` in
``app.core.config``? Two reasons:

1. ``extra="forbid"`` makes typo'd fields in the TOML blow up
   loud at load time, instead of silently dropping the value or
   writing it back out.
2. The dataclass `Config` is the user-level config; this is the
   per-project config. They live in different files
   (``config.toml`` vs ``project.toml``) and have different
   lifecycles. Keeping the models separate makes the contract
   explicit and the validation errors traceable.

Status enum
-----------
The status string in ``project.toml`` is one of ``active`` /
``paused`` / ``archived``. Pydantic v2's ``StrEnum`` is
preferred (3.11+); we fall back to ``str, Enum`` for older
runtimes even though ``pyproject.toml`` already pins 3.11+.

Round-trip
----------
``Project.model_dump()`` produces a plain dict that ``tomlkit``
can serialise directly. ``Project.model_validate(dict)`` parses
a dict that was loaded via ``tomlkit.load(...)`` (whose nested
tables become dicts). See ``test_models.py`` for the round-trip
contract.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Project name regex — lowercase / digits / hyphens, must start with
# lowercase letter or digit, 2-31 chars total. Same regex used by the
# manager to validate incoming `create(name=...)` requests.
PROJECT_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{1,30}$")

# Reserved names — would shadow real dirs in $HALO_HOME. Refusing them
# keeps `~/.gundam-halo/{projects,archive,templates,...}` unambiguous.
RESERVED_PROJECT_NAMES: frozenset[str] = frozenset(
    {
        "default",
        "global",
        "archive",
        "templates",
        ".mavis",
    }
)


# ---------------------------------------------------------------------------
# Status enum
# ---------------------------------------------------------------------------


class ProjectStatus(StrEnum):
    """Lifecycle state of a project on disk.

    - ``active``:    created, sessions can be opened (T2 territory)
    - ``paused``:    user manually paused; sessions cannot be opened
    - ``archived``:  moved to ``$HALO_HOME/archive/<name>-<ts>/`` and
                     removed from the active ``projects/`` directory
    """

    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


# ---------------------------------------------------------------------------
# Core model: Project
# ---------------------------------------------------------------------------


class Project(BaseModel):
    """Full metadata for one project on disk.

    Written to ``$HALO_HOME/projects/<name>/project.toml`` under the
    ``[project]`` table. Fields mirror the ARCHITECTURE §2 spec,
    with the addition of a schema version so we can migrate the
    file format later without silently breaking old data.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    # Schema version — bump when fields are added / renamed. The
    # round-trip tests in `test_models.py` will catch accidental
    # bumps; old files load fine because Pydantic ignores unknown
    # keys by default — but with `extra="forbid"`, unknown keys
    # error loudly which is the whole point of this model.
    schema_version: int = Field(default=1, ge=1)

    # --- identity ---
    name: str = Field(..., min_length=2, max_length=31)
    created_at: str = Field(..., description="ISO 8601 UTC with Z suffix")
    status: ProjectStatus = ProjectStatus.ACTIVE
    agent_type: str = Field(default="native_react", min_length=1, max_length=64)

    # --- per-project overrides ---
    # `None` means "use the user-level default from $HALO_HOME/config.toml".
    theme_override: str | None = Field(default=None, max_length=64)
    default_paths: list[str] = Field(
        default_factory=list,
        description=(
            "Default working paths the agent may touch (relative to "
            "project root, or absolute)"
        ),
    )
    allowed_apps: list[str] = Field(
        default_factory=list,
        description="App bundle IDs the agent may `open` from this project",
    )

    # --- validators ---

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        if not PROJECT_NAME_PATTERN.match(v):
            raise ValueError(
                f"project name {v!r} does not match {PROJECT_NAME_PATTERN.pattern}"
            )
        if v in RESERVED_PROJECT_NAMES:
            raise ValueError(f"project name {v!r} is reserved")
        return v

    @field_validator("created_at")
    @classmethod
    def _validate_created_at(cls, v: str) -> str:
        # We don't accept Z timezone offset in a relaxed way —
        # either it's there or it's not, and the manager always
        # writes it. Loose parsing would silently allow wrong TZ.
        if not v.endswith("Z"):
            raise ValueError("created_at must end with 'Z' (UTC ISO 8601)")
        # Try to parse — Pydantic's stricter mode would do this for
        # us, but keeping the regex explicit makes test failures
        # readable.
        try:
            datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError as e:
            raise ValueError(
                f"created_at is not a valid ISO 8601 timestamp: {e}"
            ) from e
        return v

    @field_validator("default_paths", "allowed_apps")
    @classmethod
    def _strip_blanks(cls, v: list[str]) -> list[str]:
        # Empty strings cause path_join surprises and look ugly in
        # the TOML. Strip them at the model boundary so the manager
        # never has to think about it.
        return [s for s in (item.strip() for item in v) if s]

    @field_validator("agent_type")
    @classmethod
    def _validate_agent_type(cls, v: str) -> str:
        # Agent types are registry keys; we don't import the
        # registry here (would be a circular), so just enforce
        # the shape and let the runtime check the actual existence
        # when the session starts (T2's job).
        if not v.replace("_", "").replace("-", "").isalnum():
            raise ValueError(
                f"agent_type {v!r} must be alphanumeric (with optional _ or -)"
            )
        return v


# ---------------------------------------------------------------------------
# Lightweight summary
# ---------------------------------------------------------------------------


class ProjectSummary(BaseModel):
    """A reduced view used for list endpoints.

    Deliberately a separate model from ``Project`` so the list
    response can never accidentally leak a field that was added to
    ``Project`` later (e.g. internal IDs, paths). New fields belong
    in ``Project`` first; promote them to ``ProjectSummary`` only
    when the UI needs them.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    name: str
    status: ProjectStatus
    created_at: str
    agent_type: str

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        if not PROJECT_NAME_PATTERN.match(v):
            raise ValueError(
                f"project name {v!r} does not match {PROJECT_NAME_PATTERN.pattern}"
            )
        return v

    @field_validator("created_at")
    @classmethod
    def _validate_created_at(cls, v: str) -> str:
        if not v.endswith("Z"):
            raise ValueError("created_at must end with 'Z' (UTC ISO 8601)")
        return v


# ---------------------------------------------------------------------------
# Archive result
# ---------------------------------------------------------------------------


class ArchiveSnapshot(BaseModel):
    """Result of archiving a project.

    Returned by ``ProjectManager.archive(name)``. Carries enough
    metadata that the caller can render a "Project X archived to
    Y (Z files, W bytes)" line without re-reading the snapshot
    directory.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    project_name: str
    archived_at: str = Field(..., description="ISO 8601 UTC with Z suffix")
    snapshot_path: Path
    file_count: int = Field(..., ge=0)
    total_bytes: int = Field(..., ge=0)

    @field_validator("project_name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        if not PROJECT_NAME_PATTERN.match(v):
            raise ValueError(
                f"project name {v!r} does not match {PROJECT_NAME_PATTERN.pattern}"
            )
        return v

    @field_validator("archived_at")
    @classmethod
    def _validate_archived_at(cls, v: str) -> str:
        if not v.endswith("Z"):
            raise ValueError("archived_at must end with 'Z' (UTC ISO 8601)")
        try:
            datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError as e:
            raise ValueError(
                f"archived_at is not a valid ISO 8601 timestamp: {e}"
            ) from e
        return v


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ProjectNotFoundError(LookupError):
    """Raised by workspace helpers / manager.get() when a project is missing.

    Typed so the API layer (T2) can map this to 404 without string
    matching, and so the test suite can assert on the exact class.
    """

    def __init__(self, name: str, root: Path | None = None) -> None:
        self.name = name
        self.root = root
        msg = f"project {name!r} not found"
        if root is not None:
            msg += f" under {root}"
        super().__init__(msg)


class ProjectNameError(ValueError):
    """Raised when a project name fails the regex or is reserved.

    Subclass of ``ValueError`` so callers that catch the standard
    Python exception still get a sane error message. Tests assert
    on this class directly.
    """


class ProjectExistsError(FileExistsError):
    """Raised by manager.create() when the project dir already exists.

    Note: ``create()`` is documented as idempotent — it returns the
    existing project without writing. This error is raised only by
    the *strict* create path (e.g. when the caller asks to overwrite
    an existing project; the API layer in T2 might expose a
    ``?strict=true`` query param for that).
    """


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def now_utc_iso_z() -> str:
    """Return current UTC time as an ISO 8601 string with a ``Z`` suffix.

    Centralised so the manager and the tests both use the same
    format. Pydantic v2 + Pydantic 2's `datetime` serializer would
    produce ``+00:00`` by default; we want the explicit ``Z`` to
    match the format committed in M13's TOML.
    """
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


__all__ = [
    "ArchiveSnapshot",
    "PROJECT_NAME_PATTERN",
    "Project",
    "ProjectExistsError",
    "ProjectNameError",
    "ProjectNotFoundError",
    "ProjectStatus",
    "ProjectSummary",
    "RESERVED_PROJECT_NAMES",
    "now_utc_iso_z",
]

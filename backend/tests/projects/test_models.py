"""Tests for ``app.projects.models`` — Pydantic v2 schema + errors.

Covers:
- Round-trip TOML ↔ Pydantic (via ``Project.model_dump`` and the
  hand-rolled ``_dump_project_toml``/``_load_project_toml`` helpers
  in the manager module).
- ``extra="forbid"`` rejection — typos in TOML blow up loud.
- ``ProjectStatus`` enum validation (3 values, lowercase strings).
- ``ProjectNameError`` for invalid / reserved names.
- ``ProjectNotFoundError`` carries the name + the root Path.
- ``now_utc_iso_z()`` format check.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from app.projects.manager import _dump_project_toml, _load_project_toml
from app.projects.models import (
    PROJECT_NAME_PATTERN,
    RESERVED_PROJECT_NAMES,
    ArchiveSnapshot,
    Project,
    ProjectNameError,
    ProjectNotFoundError,
    ProjectStatus,
    ProjectSummary,
    now_utc_iso_z,
)
from pydantic import ValidationError

# ---------------------------------------------------------------------------
# ProjectStatus
# ---------------------------------------------------------------------------


def test_project_status_has_three_values():
    assert {s.value for s in ProjectStatus} == {"active", "paused", "archived"}


def test_project_status_rejects_unknown_value():
    with pytest.raises(ValueError):
        ProjectStatus("deleted")  # type: ignore[call-arg]


def test_project_status_serialises_as_lowercase_string():
    p = Project(
        name="abc",
        created_at="2026-06-13T10:00:00Z",
        status=ProjectStatus.PAUSED,
    )
    assert p.status.value == "paused"
    assert p.model_dump()["status"] == ProjectStatus.PAUSED


# ---------------------------------------------------------------------------
# Project name validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "good",
    [
        "ab",          # minimum length (2)
        "fix-jarvis",  # typical
        "my-cool-2",   # with digit
        "abc123",      # digits allowed
        "a" + "b" * 30,  # 31 chars (max)
    ],
)
def test_project_name_accepts_valid(good):
    p = Project(name=good, created_at="2026-06-13T10:00:00Z")
    assert p.name == good


@pytest.mark.parametrize(
    "bad,why",
    [
        ("a", "too short"),
        ("A", "uppercase"),
        ("abc_def", "underscore"),
        ("-leading", "leading dash"),
        ("abc.def", "dot"),
        ("abc/def", "slash"),
    ],
)
def test_project_name_rejects_invalid(bad, why):
    with pytest.raises(ValidationError):
        Project(name=bad, created_at="2026-06-13T10:00:00Z")


@pytest.mark.parametrize(
    "edge_ok",
    [
        # The spec's regex `^[a-z0-9][a-z0-9-]{1,30}$` accepts these:
        # - first char must be [a-z0-9]
        # - subsequent chars (1..30 more) can be [a-z0-9-]
        # so trailing dashes ARE allowed.
        "ab-",
        "a-b",
        "0a",
        "0" + "a" * 30,  # 31 chars total
    ],
)
def test_project_name_accepts_spec_edge_cases(edge_ok):
    p = Project(name=edge_ok, created_at="2026-06-13T10:00:00Z")
    assert p.name == edge_ok


@pytest.mark.parametrize("reserved", sorted(RESERVED_PROJECT_NAMES))
def test_project_name_rejects_reserved(reserved):
    """Every reserved name must be rejected.

    Names that pass the regex (e.g. ``default``) get the specific
    'reserved' error. Names that fail the regex first (e.g. ``.mavis``)
    get the regex-mismatch error. Both are correct rejections; the
    invariant is *that* they're rejected, not which message.
    """
    with pytest.raises(ValidationError) as exc:
        Project(name=reserved, created_at="2026-06-13T10:00:00Z")
    msg = str(exc.value).lower()
    assert "reserved" in msg or "match" in msg


def test_project_name_pattern_is_locked():
    """The regex is part of the public contract — change it and you
    break the spec. This test fails if anyone touches the pattern."""
    assert PROJECT_NAME_PATTERN.pattern == r"^[a-z0-9][a-z0-9-]{1,30}$"


# ---------------------------------------------------------------------------
# created_at validation
# ---------------------------------------------------------------------------


def test_created_at_must_end_with_z():
    with pytest.raises(ValidationError):
        Project(name="abc", created_at="2026-06-13T10:00:00+00:00")


def test_created_at_must_be_valid_iso_8601():
    with pytest.raises(ValidationError):
        Project(name="abc", created_at="not-a-timestampZ")


def test_now_utc_iso_z_format():
    s = now_utc_iso_z()
    assert s.endswith("Z")
    # Round-trips through datetime.fromisoformat
    datetime.fromisoformat(s.replace("Z", "+00:00"))


# ---------------------------------------------------------------------------
# extra="forbid"
# ---------------------------------------------------------------------------


def test_project_rejects_unknown_field():
    with pytest.raises(ValidationError) as exc:
        Project(
            name="abc",
            created_at="2026-06-13T10:00:00Z",
            typo_field="boom",  # type: ignore[call-arg]
        )
    # Pydantic reports the unknown field name in the error.
    assert "typo_field" in str(exc.value)


def test_project_summary_rejects_unknown_field():
    with pytest.raises(ValidationError) as exc:
        ProjectSummary(
            name="abc",
            status="active",
            created_at="2026-06-13T10:00:00Z",
            agent_type="native_react",
            extra_garbage=True,  # type: ignore[call-arg]
        )
    assert "extra_garbage" in str(exc.value)


# ---------------------------------------------------------------------------
# Round-trip via TOML helpers
# ---------------------------------------------------------------------------


def test_project_roundtrip_via_toml(tmp_path):
    """Build a Project, dump to TOML, load it back, check equality."""
    p = Project(
        name="fix-jarvis",
        created_at="2026-06-13T10:00:00Z",
        status=ProjectStatus.ACTIVE,
        agent_type="native_react",
        theme_override="gundam-ntd",
        default_paths=["~/x/", "~/y/"],
        allowed_apps=["com.example"],
    )
    body = _dump_project_toml(p)
    toml_path = tmp_path / "project.toml"
    toml_path.write_text(body)

    loaded = _load_project_toml(toml_path)
    assert loaded.name == p.name
    assert loaded.status == p.status
    assert loaded.agent_type == p.agent_type
    assert loaded.theme_override == p.theme_override
    assert loaded.default_paths == p.default_paths
    assert loaded.allowed_apps == p.allowed_apps
    assert loaded.schema_version == p.schema_version


def test_project_roundtrip_with_no_theme_override(tmp_path):
    p = Project(
        name="jarvis-b",
        created_at="2026-06-13T10:00:00Z",
        status=ProjectStatus.PAUSED,
        agent_type="orchestrator",
        theme_override=None,  # omitted in TOML; re-loaded as None
    )
    body = _dump_project_toml(p)
    assert "theme_override" not in body  # absent key = None on read

    toml_path = tmp_path / "project.toml"
    toml_path.write_text(body)
    loaded = _load_project_toml(toml_path)
    assert loaded.theme_override is None
    assert loaded.status == ProjectStatus.PAUSED


def test_project_roundtrip_with_empty_lists(tmp_path):
    p = Project(
        name="empty-lists",
        created_at="2026-06-13T10:00:00Z",
        default_paths=[],
        allowed_apps=[],
    )
    body = _dump_project_toml(p)
    assert "default_paths = []" in body
    assert "allowed_apps = []" in body
    toml_path = tmp_path / "project.toml"
    toml_path.write_text(body)
    loaded = _load_project_toml(toml_path)
    assert loaded.default_paths == []
    assert loaded.allowed_apps == []


# ---------------------------------------------------------------------------
# ArchiveSnapshot
# ---------------------------------------------------------------------------


def test_archive_snapshot_basic():
    snap = ArchiveSnapshot(
        project_name="fix-jarvis",
        archived_at="2026-06-13T10:00:00Z",
        snapshot_path="/home/user/.gundam-halo/archive/fix-jarvis-20260613-100000",
        file_count=42,
        total_bytes=12345,
    )
    assert snap.file_count == 42
    assert snap.total_bytes == 12345
    assert snap.snapshot_path.is_absolute()


def test_archive_snapshot_rejects_invalid_name():
    with pytest.raises(ValidationError):
        ArchiveSnapshot(
            project_name="Bad",  # uppercase
            archived_at="2026-06-13T10:00:00Z",
            snapshot_path="/tmp/x",
            file_count=0,
            total_bytes=0,
        )


def test_archive_snapshot_rejects_negative_counts():
    with pytest.raises(ValidationError):
        ArchiveSnapshot(
            project_name="abc",
            archived_at="2026-06-13T10:00:00Z",
            snapshot_path="/tmp/x",
            file_count=-1,
            total_bytes=0,
        )


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


def test_project_not_found_error_carries_name_and_root():
    err = ProjectNotFoundError(name="missing")
    assert err.name == "missing"
    assert err.root is None
    assert "missing" in str(err)
    assert "not found" in str(err).lower()


def test_project_not_found_error_with_root():
    from pathlib import Path

    err = ProjectNotFoundError(name="missing", root=Path("/tmp/x/missing"))
    assert err.root == Path("/tmp/x/missing")
    assert "/tmp/x/missing" in str(err)


def test_project_name_error_is_value_error():
    # Subclass of ValueError so callers can catch the standard
    # Python exception and still get a useful message.
    err = ProjectNameError("bad name")
    assert isinstance(err, ValueError)

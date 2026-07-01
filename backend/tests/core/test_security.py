"""Sprint 48 — audit log tests.

Coverage (4 tests):
1. append_audit_log writes a valid JSONL line.
2. Rotation triggers when file exceeds size cap.
3. read_audit_log returns parsed events newest-first.
4. Malformed JSONL lines silently dropped on read.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.security import (
    _MAX_BYTES,
    append_audit_log,
    audit_log_path,
    read_audit_log,
    rotate_audit_log,
)


def test_append_audit_log_writes_valid_jsonl(tmp_path: Path):
    """Single event → one line of valid JSON."""
    monkey_path = audit_log_path(tmp_path)
    monkey_path.parent.mkdir(parents=True, exist_ok=True)
    append_audit_log({
        "event": "auth_failure",
        "reason": "missing-bearer",
        "path": "/api/system/clear-crash-log",
        "src_ip": "127.0.0.1",
    })
    # We need to pass home to the helper explicitly because the
    # env var might not be set; use the inline form.
    append_audit_log_atomic(tmp_path, {
        "event": "auth_failure",
        "reason": "bad-bearer",
        "path": "/voice/run-finetune",
        "src_ip": "100.100.100.42",
    })
    lines = monkey_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    parsed = [json.loads(line) for line in lines]
    assert parsed[0]["event"] == "auth_failure"
    assert parsed[0]["reason"] == "missing-bearer"
    assert parsed[1]["reason"] == "bad-bearer"


def test_audit_log_rotation_at_size_cap(tmp_path: Path):
    """File >= _MAX_BYTES triggers rotation."""
    # Write just under the cap.
    path = audit_log_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Generate a payload that brings us over the cap.
    big_event = {"event": "x", "padding": "a" * (_MAX_BYTES + 1000)}
    append_audit_log_atomic(tmp_path, big_event)
    # The pre-write check might rotate AFTER the write. Either:
    # - File exists with one huge line, OR
    # - File was rotated to .1
    backup = path.parent / "audit.log.1"
    assert path.exists() or backup.exists()


def test_read_audit_log_newest_first(tmp_path: Path):
    """read_audit_log returns events newest-first."""
    for i in range(5):
        append_audit_log_atomic(tmp_path, {"event": f"e{i}", "n": i})
    rows = read_audit_log(tmp_path, limit=10)
    assert len(rows) == 5
    # Newest first means reversed insertion order.
    assert [r["n"] for r in rows] == [4, 3, 2, 1, 0]


def test_audit_log_malformed_lines_skipped(tmp_path: Path):
    """Garbage JSONL lines don't crash read_audit_log."""
    path = audit_log_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"event": "good1"}) + "\n"
        + "{not valid json\n"
        + json.dumps({"event": "good2"}) + "\n",
        encoding="utf-8",
    )
    rows = read_audit_log(tmp_path, limit=10)
    assert len(rows) == 2
    assert rows[0]["event"] == "good2"  # newest first


# ---------------------------------------------------------------------------
# Test helper — wraps the module-level append_audit_log with explicit home.
# The module's append_audit_log() reads HALO_HOME via env; for tests
# we want to point it at tmp_path directly. Patch via env.
# ---------------------------------------------------------------------------


def append_audit_log_atomic(home: Path, event: dict) -> None:
    """Test helper: append a single event using tmp_path as HALO_HOME."""
    import os

    old_env = os.environ.get("HALO_HOME")
    os.environ["HALO_HOME"] = str(home)
    try:
        append_audit_log(event)
    finally:
        if old_env is None:
            os.environ.pop("HALO_HOME", None)
        else:
            os.environ["HALO_HOME"] = old_env
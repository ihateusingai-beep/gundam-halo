"""Sprint 43 — tests for scripts/on-launchd-crash.sh.

The script is bash, but the logic is pure data transformation. We
shell out to bash via subprocess to test the real binary (rather
than re-implementing it in Python — that would diverge over time).

Coverage:
1. Missing marker → script exits 0, no log entry written.
2. Valid marker → JSONL entry appended, marker removed.
3. Malformed marker (with quote injection attempt) → no log entry,
   marker removed (defensive against buggy marker writers).
4. Multiple crashes in sequence → all entries accumulate correctly.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parent.parent.parent.parent / "scripts" / "on-launchd-crash.sh"


def _has_bash() -> bool:
    return shutil.which("bash") is not None


def _write_marker(home: Path, **fields) -> None:
    marker = home / "state" / "crash_marker"
    marker.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{k}={v}" for k, v in fields.items()]
    marker.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _run_script(home: Path) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["HALO_HOME"] = str(home)
    return subprocess.run(
        ["bash", str(SCRIPT)],
        env=env,
        capture_output=True,
        text=True,
        timeout=5,
    )


@pytest.mark.skipif(not _has_bash(), reason="bash not available")
def test_missing_marker_exits_clean(tmp_path: Path):
    """No marker file → exit 0, no log entry."""
    # State dir exists but no marker.
    (tmp_path / "state").mkdir()
    result = _run_script(tmp_path)
    assert result.returncode == 0
    assert not (tmp_path / "state" / "crash_log.jsonl").exists()


@pytest.mark.skipif(not _has_bash(), reason="bash not available")
def test_valid_marker_appends_jsonl(tmp_path: Path):
    """Valid marker → JSONL entry appended, marker removed."""
    ts = datetime.now(UTC).isoformat()
    _write_marker(
        tmp_path,
        timestamp=ts,
        exit_code=137,
        reason="oom-killed",
        uptime_seconds=7200,
    )

    result = _run_script(tmp_path)
    assert result.returncode == 0

    log = (tmp_path / "state" / "crash_log.jsonl").read_text(encoding="utf-8")
    lines = [l for l in log.splitlines() if l.strip()]
    assert len(lines) == 1

    entry = json.loads(lines[0])
    assert entry["timestamp"] == ts
    assert entry["exit_code"] == 137
    assert entry["reason"] == "oom-killed"
    assert entry["uptime_seconds"] == 7200

    # Marker should be removed.
    assert not (tmp_path / "state" / "crash_marker").exists()


@pytest.mark.skipif(not _has_bash(), reason="bash not available")
def test_quote_injection_refused(tmp_path: Path):
    """Malicious quote in marker → refused, marker removed."""
    # Bypass our Python writer — write the bad marker directly.
    marker = tmp_path / "state" / "crash_marker"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(
        'timestamp=2026-06-26T10:00:00+00:00\n'
        'exit_code=1\n'
        'reason=evil","injected":"yes\n'
        'uptime_seconds=0\n',
        encoding="utf-8",
    )

    result = _run_script(tmp_path)
    assert result.returncode == 0  # always exits clean

    # No log entry — injection was refused.
    log_path = tmp_path / "state" / "crash_log.jsonl"
    assert not log_path.exists() or log_path.stat().st_size == 0

    # Marker removed so next crash starts clean.
    assert not marker.exists()


@pytest.mark.skipif(not _has_bash(), reason="bash not available")
def test_multiple_crashes_accumulate(tmp_path: Path):
    """Three crashes in sequence → all 3 entries in the log."""
    for i in range(3):
        _write_marker(
            tmp_path,
            timestamp=datetime.now(UTC).isoformat(),
            exit_code=1,
            reason=f"crash-{i}",
            uptime_seconds=10 * (i + 1),
        )
        result = _run_script(tmp_path)
        assert result.returncode == 0

    log = (tmp_path / "state" / "crash_log.jsonl").read_text(encoding="utf-8")
    lines = [json.loads(l) for l in log.splitlines() if l.strip()]
    reasons = [e["reason"] for e in lines]
    assert reasons == ["crash-0", "crash-1", "crash-2"]


@pytest.mark.skipif(not _has_bash(), reason="bash not available")
def test_defaults_used_for_missing_fields(tmp_path: Path):
    """Marker with only some fields → defaults fill in the rest."""
    # Only timestamp set; exit_code, reason, uptime_seconds missing.
    marker = tmp_path / "state" / "crash_marker"
    marker.parent.mkdir(parents=True, exist_ok=True)
    ts = "2026-06-26T12:00:00+00:00"
    marker.write_text(f"timestamp={ts}\n", encoding="utf-8")

    result = _run_script(tmp_path)
    assert result.returncode == 0

    log = (tmp_path / "state" / "crash_log.jsonl").read_text(encoding="utf-8")
    entry = json.loads(log.strip())
    assert entry["timestamp"] == ts
    assert entry["exit_code"] == 1  # default
    assert entry["reason"] == "unknown"  # default
    assert entry["uptime_seconds"] == 0  # default

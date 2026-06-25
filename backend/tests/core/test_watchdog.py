"""Sprint 43 — watchdog module unit tests.

Six scenarios covering the core crash log logic:
1. record_crash appends + preserves ordering.
2. record_crash prunes > 60min old entries.
3. crash_count_last_hour returns 0 on missing log.
4. should_stop_respawning fires at threshold.
5. Concurrent crash recording from 10 threads is safe.
6. clear_crash_log returns the event count + removes the file.
"""
from __future__ import annotations

import json
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.core.watchdog import (
    CrashEvent,
    clear_crash_log,
    crash_count_last_hour,
    last_crash_at,
    record_crash,
    should_stop_respawning,
    write_crash_marker,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _iso_minus(seconds: int) -> str:
    return (datetime.now(UTC) - timedelta(seconds=seconds)).isoformat()


def _make_event(seconds_ago: int = 0, **overrides) -> CrashEvent:
    """Build a CrashEvent timestamped `seconds_ago` seconds in the past."""
    defaults = {
        "timestamp": _iso_minus(seconds_ago),
        "exit_code": 1,
        "reason": "test",
        "uptime_seconds": 3600,
    }
    defaults.update(overrides)
    return CrashEvent(**defaults)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_record_crash_appends_preserving_order(tmp_path: Path):
    """Three crashes written in order → log has 3 lines, timestamps preserved."""
    e1 = _make_event(seconds_ago=10, reason="first")
    e2 = _make_event(seconds_ago=5, reason="second")
    e3 = _make_event(seconds_ago=0, reason="third")

    record_crash(tmp_path, e1)
    record_crash(tmp_path, e2)
    record_crash(tmp_path, e3)

    log = (tmp_path / "state" / "crash_log.jsonl").read_text(encoding="utf-8")
    lines = [l for l in log.splitlines() if l.strip()]
    assert len(lines) == 3
    # Parse back and verify order + reasons.
    reasons = [json.loads(l)["reason"] for l in lines]
    assert reasons == ["first", "second", "third"]


def test_record_crash_prunes_old_entries(tmp_path: Path):
    """Old entries (> 60min) get dropped on every write."""
    # Write 3 stale entries directly to the log (simulating an old crash
    # that happened > 60min ago — we bypass record_crash for the stale ones
    # because record_crash always uses "now" for the new entry timestamp).
    log_path = tmp_path / "state" / "crash_log.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    stale = _iso_minus(7200)  # 2 hours ago
    fresh = _iso_minus(60)     # 1 minute ago
    log_path.write_text(
        json.dumps({"timestamp": stale, "exit_code": 1, "reason": "stale1", "uptime_seconds": 0}) + "\n"
        + json.dumps({"timestamp": stale, "exit_code": 1, "reason": "stale2", "uptime_seconds": 0}) + "\n"
        + json.dumps({"timestamp": fresh, "exit_code": 1, "reason": "fresh", "uptime_seconds": 0}) + "\n",
        encoding="utf-8",
    )

    # Record a new crash — should trigger pruning.
    record_crash(tmp_path, _make_event(reason="newest"))

    log = log_path.read_text(encoding="utf-8")
    lines = [json.loads(l) for l in log.splitlines() if l.strip()]
    reasons = [e["reason"] for e in lines]
    # Stale entries dropped; fresh + newest remain.
    assert "stale1" not in reasons
    assert "stale2" not in reasons
    assert reasons == ["fresh", "newest"]


def test_crash_count_last_hour_zero_when_no_log(tmp_path: Path):
    """Missing log file → 0, no crash."""
    assert crash_count_last_hour(tmp_path) == 0
    assert should_stop_respawning(tmp_path) is False
    assert last_crash_at(tmp_path) is None


def test_should_stop_respawning_at_threshold(tmp_path: Path):
    """3 crashes in 30min → should_stop_respawning True; clear → False."""
    for i in range(3):
        record_crash(tmp_path, _make_event(seconds_ago=10 * (i + 1)))

    assert crash_count_last_hour(tmp_path) == 3
    assert should_stop_respawning(tmp_path, threshold=3) is True
    # Threshold of 4 should still be False.
    assert should_stop_respawning(tmp_path, threshold=4) is False

    # Clear → back to False.
    cleared = clear_crash_log(tmp_path)
    assert cleared == 3
    assert should_stop_respawning(tmp_path, threshold=3) is False


def test_concurrent_crash_recording(tmp_path: Path):
    """10 threads each call record_crash once → all 10 entries present."""
    threads: list[threading.Thread] = []

    def worker(i: int) -> None:
        record_crash(tmp_path, _make_event(reason=f"thread-{i}"))

    for i in range(10):
        threads.append(threading.Thread(target=worker, args=(i,)))
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    log = (tmp_path / "state" / "crash_log.jsonl").read_text(encoding="utf-8")
    lines = [json.loads(l) for l in log.splitlines() if l.strip()]
    reasons = sorted(e["reason"] for e in lines)
    assert reasons == sorted(f"thread-{i}" for i in range(10))


def test_clear_crash_log_returns_event_count(tmp_path: Path):
    """5 crashes → clear returns 5 + removes the file."""
    for i in range(5):
        record_crash(tmp_path, _make_event(reason=f"e{i}"))

    assert (tmp_path / "state" / "crash_log.jsonl").is_file()

    cleared = clear_crash_log(tmp_path)
    assert cleared == 5
    assert not (tmp_path / "state" / "crash_log.jsonl").exists()

    # Calling clear again on missing file returns 0 (no error).
    assert clear_crash_log(tmp_path) == 0


def test_write_crash_marker_creates_file(tmp_path: Path):
    """write_crash_marker writes a KEY=VALUE marker readable by launchd hook."""
    write_crash_marker(tmp_path, exit_code=137, reason="oom-killed", uptime_seconds=7200)
    marker = (tmp_path / "state" / "crash_marker").read_text(encoding="utf-8")
    assert "exit_code=137" in marker
    assert "reason=oom-killed" in marker
    assert "uptime_seconds=7200" in marker

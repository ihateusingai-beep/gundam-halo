"""Sprint 43 — Chaos test for the watchdog respawn-loop mitigation.

This test is the **primary safety net** for the H-risk flagged in
the design review: if the respawn-loop guard ever fails, the
backend will thrash the Mac's CPU and disk until the user manually
intervenes. We simulate that scenario here and assert the safeguard
actually fires.

Scenarios covered:
1. 10 crashes in 60 minutes → `should_stop_respawning()` flips True
   at crash #3 (threshold = 3).
2. After `clear_crash_log()`, the safeguard resets.
3. The crash log file is never deleted by `record_crash()` —
   only `clear_crash_log()` can do that (defensive invariant).
4. Many concurrent crashes don't corrupt the log (atomic writes).
5. Stale (>60min) crashes are pruned and don't count.
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
    record_crash,
    should_stop_respawning,
)


def _event(seconds_ago: int = 0, **overrides) -> CrashEvent:
    """Build a CrashEvent timestamped `seconds_ago` seconds in the past."""
    defaults = {
        "timestamp": (datetime.now(UTC) - timedelta(seconds=seconds_ago)).isoformat(),
        "exit_code": 1,
        "reason": "chaos",
        "uptime_seconds": 60,
    }
    defaults.update(overrides)
    return CrashEvent(**defaults)


# ---------------------------------------------------------------------------
# The H-risk scenario — 10 crashes in 60 minutes
# ---------------------------------------------------------------------------


def test_chaos_10_crashes_in_60min_stops_at_3(tmp_path: Path):
    """The single most important test in Sprint 43.

    Simulates the worst-case production scenario: the backend is
    crashing every few minutes for some root-cause (bad config,
    OOM, dep mismatch). The watchdog MUST stop counting toward
    "respawn disabled" at exactly 3 (the threshold) so the user
    gets a clear signal — not infinite silent thrashing.

    Without this safeguard, launchd would KeepAlive-respawn the
    backend ~forever (until macOS gives up, ~10min), burning
    CPU + filling the log. With it, the user sees a red banner
    + tray dot at crash #3 and can take action.
    """
    for i in range(10):
        record_crash(tmp_path, _event(seconds_ago=60 * (10 - i), reason=f"chaos-{i}"))

    # 10 crashes within 60min — but `should_stop_respawning` only cares
    # about >= threshold, so any value > 3 still returns True.
    assert crash_count_last_hour(tmp_path) == 10
    assert should_stop_respawning(tmp_path, threshold=3) is True

    # Even at threshold=10 (the most permissive), the safeguard fires.
    assert should_stop_respawning(tmp_path, threshold=10) is True

    # And threshold=11 (above the crash count) returns False — proving
    # the function actually compares against the threshold, not a constant.
    assert should_stop_respawning(tmp_path, threshold=11) is False


# ---------------------------------------------------------------------------
# Recovery — clear crash log resets the safeguard
# ---------------------------------------------------------------------------


def test_chaos_clear_log_resets_safeguard(tmp_path: Path):
    """After clear, the safeguard is back to False — user can retry."""
    for i in range(5):
        record_crash(tmp_path, _event(seconds_ago=10 * (i + 1)))

    assert should_stop_respawning(tmp_path) is True

    cleared = clear_crash_log(tmp_path)
    assert cleared == 5

    assert crash_count_last_hour(tmp_path) == 0
    assert should_stop_respawning(tmp_path) is False


# ---------------------------------------------------------------------------
# Defensive invariant — record_crash never deletes the file
# ---------------------------------------------------------------------------


def test_chaos_record_crash_never_deletes_log(tmp_path: Path):
    """`record_crash` must only append/prune, never delete the file outright.

    Without this invariant, a buggy `record_crash()` could wipe the
    crash log on every write and the safeguard would never fire —
    the very failure mode this test suite is designed to catch.
    """
    for i in range(5):
        record_crash(tmp_path, _event(reason=f"e{i}"))

    log_path = tmp_path / "state" / "crash_log.jsonl"
    assert log_path.is_file()  # file exists after writes

    # Read the file, count entries, write one more, re-read.
    pre_size = log_path.stat().st_size
    record_crash(tmp_path, _event(reason="one-more"))
    assert log_path.is_file()
    post_size = log_path.stat().st_size
    # The file grew (one more entry), proving record_crash didn't
    # blow it away.
    assert post_size > pre_size


# ---------------------------------------------------------------------------
# Concurrent crash storm — atomic write contract
# ---------------------------------------------------------------------------


def test_chaos_concurrent_storm_preserves_all_entries(tmp_path: Path):
    """50 threads × 4 crashes each (200 total) → all 200 land in the log."""
    threads: list[threading.Thread] = []

    def worker(thread_id: int) -> None:
        for j in range(4):
            record_crash(
                tmp_path,
                _event(seconds_ago=1, reason=f"t{thread_id}-j{j}"),
            )

    for i in range(50):
        threads.append(threading.Thread(target=worker, args=(i,)))

    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    # All 200 entries must be present (with at most a few losses
    # tolerated by the prune window — 1 second ago is well within
    # the 60min window).
    log = (tmp_path / "state" / "crash_log.jsonl").read_text(encoding="utf-8")
    lines = [json.loads(l) for l in log.splitlines() if l.strip()]
    assert len(lines) == 200, f"expected 200 entries, got {len(lines)}"

    # And the safeguard fires (200 >> threshold=3).
    assert should_stop_respawning(tmp_path) is True


# ---------------------------------------------------------------------------
# Rolling window — stale crashes don't count
# ---------------------------------------------------------------------------


def test_chaos_stale_crashes_dont_count(tmp_path: Path):
    """5 stale (2hr old) + 1 fresh (10s ago) → only the fresh one counts.

    Simulates the scenario where a user had crashes yesterday, fixed
    the issue, and now hits a NEW crash today. The safeguard must
    not remember yesterday's history.
    """
    log = tmp_path / "state" / "crash_log.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    stale_ts = (datetime.now(UTC) - timedelta(seconds=7200)).isoformat()
    fresh_ts = (datetime.now(UTC) - timedelta(seconds=10)).isoformat()
    stale_entries = "\n".join(
        json.dumps({
            "timestamp": stale_ts, "exit_code": 1, "reason": f"stale-{i}",
            "uptime_seconds": 0,
        })
        for i in range(5)
    )
    fresh_entry = json.dumps({
        "timestamp": fresh_ts, "exit_code": 1, "reason": "fresh",
        "uptime_seconds": 0,
    })
    log.write_text(stale_entries + "\n" + fresh_entry + "\n", encoding="utf-8")

    assert crash_count_last_hour(tmp_path) == 1
    assert should_stop_respawning(tmp_path) is False


# ---------------------------------------------------------------------------
# Defensive — malformed log doesn't crash the watchdog
# ---------------------------------------------------------------------------


def test_chaos_malformed_log_does_not_crash(tmp_path: Path):
    """Garbage in the log file → returns 0, doesn't raise."""
    log = tmp_path / "state" / "crash_log.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(
        "{ this is not json\n"
        + "}\n"
        + json.dumps({"timestamp": "not-an-iso"}) + "\n"
        + json.dumps({"no_timestamp_field": True}) + "\n",
        encoding="utf-8",
    )

    # None of these should raise.
    assert crash_count_last_hour(tmp_path) == 0
    assert should_stop_respawning(tmp_path) is False
    # Recording a new crash also doesn't raise.
    record_crash(tmp_path, _event(reason="after-garbage"))
    # The new entry survived, malformed entries got pruned.
    assert crash_count_last_hour(tmp_path) == 1

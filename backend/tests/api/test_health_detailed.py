"""Sprint 43 — /api/system/health-detailed route tests.

Verifies:
1. Crash count is read from the JSONL log.
2. `respawn_disabled` flag flips at threshold (>= 3 in 60min).
3. launchd install status is reflected via `watchdog.installed`.
4. POST /clear-crash-log wipes the log and returns event count.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Fixtures + helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def client(monkeypatch, tmp_path):
    """Fresh HALO_HOME → backend with the new watchdog endpoints."""
    monkeypatch.setenv("HALO_HOME", str(tmp_path))
    monkeypatch.setenv("MINIMAX_API_KEY", "test-fake")

    from app.core import config as config_mod
    config_mod.reset_config()

    from app.main import create_app
    return TestClient(create_app())


def _write_crash(home: Path, seconds_ago: int, reason: str = "test") -> None:
    """Write one crash event directly to the JSONL log."""
    log_dir = home / "state"
    log_dir.mkdir(parents=True, exist_ok=True)
    log = log_dir / "crash_log.jsonl"
    ts = (datetime.now(UTC) - timedelta(seconds=seconds_ago)).isoformat()
    entry = json.dumps({
        "timestamp": ts, "exit_code": 1, "reason": reason, "uptime_seconds": 0
    })
    with log.open("a", encoding="utf-8") as f:
        f.write(entry + "\n")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_health_detailed_includes_crash_count(client, tmp_path):
    """2 crashes → crash_count_60m == 2; respawn_disabled is False."""
    _write_crash(tmp_path, seconds_ago=10, reason="r1")
    _write_crash(tmp_path, seconds_ago=20, reason="r2")

    r = client.get("/api/system/health-detailed")
    assert r.status_code == 200
    body = r.json()

    assert body["status"] == "ok"
    assert body["crash_count_60m"] == 2
    assert body["last_crash_at"] is not None
    assert body["respawn_disabled"] is False
    # launchd won't be installed in the test env.
    assert body["watchdog"]["installed"] is False
    assert body["watchdog"]["pid"] is None


def test_health_detailed_flags_respawn_disabled_at_threshold(client, tmp_path):
    """4 crashes → respawn_disabled is True (threshold = 3)."""
    for i in range(4):
        _write_crash(tmp_path, seconds_ago=5 * (i + 1), reason=f"r{i}")

    r = client.get("/api/system/health-detailed")
    assert r.status_code == 200
    body = r.json()
    assert body["crash_count_60m"] == 4
    assert body["respawn_disabled"] is True


def test_health_detailed_excludes_old_crashes(client, tmp_path):
    """Crashes > 60min old are not counted."""
    # 3 stale + 1 fresh
    _write_crash(tmp_path, seconds_ago=7200, reason="stale1")
    _write_crash(tmp_path, seconds_ago=7200, reason="stale2")
    _write_crash(tmp_path, seconds_ago=7200, reason="stale3")
    _write_crash(tmp_path, seconds_ago=10, reason="fresh")

    r = client.get("/api/system/health-detailed")
    body = r.json()
    assert body["crash_count_60m"] == 1  # only the fresh one
    assert body["respawn_disabled"] is False


def test_clear_crash_log_returns_event_count(client, tmp_path):
    """POST /clear-crash-log returns the cleared count."""
    for i in range(3):
        _write_crash(tmp_path, seconds_ago=5 * (i + 1), reason=f"r{i}")

    r = client.post("/api/system/clear-crash-log")
    assert r.status_code == 200
    body = r.json()
    assert body == {"ok": True, "cleared": 3}

    # Log file is gone; subsequent health-detailed shows zero crashes.
    r2 = client.get("/api/system/health-detailed")
    assert r2.json()["crash_count_60m"] == 0


def test_clear_crash_log_empty_returns_zero(client, tmp_path):
    """POST /clear-crash-log on missing file → cleared: 0, no error."""
    r = client.post("/api/system/clear-crash-log")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "cleared": 0}


# ---------------------------------------------------------------------------
# Sprint 41 — /api/system/cancel-restart route tests
# ---------------------------------------------------------------------------


def test_cancel_restart_returns_ok_when_no_restart_scheduled(client):
    """Idempotent: returns ok=true even when no restart was scheduled."""
    r = client.post("/api/system/cancel-restart")
    assert r.status_code == 200
    body = r.json()
    assert body == {"ok": True, "cancelled": False}


def test_cancel_restart_returns_cancelled_true_when_scheduled(client):
    """After schedule_restart, cancel returns cancelled=true."""
    from app.core import restart

    restart.schedule_restart(delay_s=5.0, reason="test")
    try:
        r = client.post("/api/system/cancel-restart")
        assert r.status_code == 200
        body = r.json()
        assert body == {"ok": True, "cancelled": True}
        # Side effect: flag is cleared.
        assert restart.is_restart_scheduled() is False
    finally:
        # Defensive cleanup so other tests aren't affected.
        restart.cancel_scheduled_restart()


def test_cancel_restart_then_voice_config_reports_not_scheduled(client):
    """End-to-end: schedule → cancel → GET /voice/config shows
    restart_scheduled=false + restart_in_seconds=None."""
    from app.core import restart

    restart.schedule_restart(delay_s=5.0, reason="test")
    client.post("/api/system/cancel-restart")
    r = client.get("/voice/config")
    body = r.json()
    assert body["restart_scheduled"] is False
    assert body["restart_in_seconds"] is None

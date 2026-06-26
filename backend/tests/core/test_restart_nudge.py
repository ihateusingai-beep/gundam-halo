"""Sprint 41 — restart nudge backend tests.

3 tests:
1. schedule_restart records _restart_scheduled_at within ±0.5s
2. get_restart_countdown_s decrements as time passes
3. cancel_scheduled_restart clears all flags
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest

from app.core import restart


@pytest.fixture(autouse=True)
def _reset_restart_flags():
    """Wipe module-level flags between tests."""
    restart._restart_scheduled = False
    restart._restart_scheduled_reason = ""
    restart._restart_scheduled_at = None
    yield
    restart._restart_scheduled = False
    restart._restart_scheduled_reason = ""
    restart._restart_scheduled_at = None


def test_schedule_restart_records_scheduled_at():
    """schedule_restart(5.0, ...) sets _restart_scheduled_at to ~now + 5."""
    restart.schedule_restart(delay_s=5.0, reason="test")
    assert restart.is_restart_scheduled() is True
    assert restart._restart_scheduled_at is not None
    expected = time.monotonic() + 5.0
    # Within ±0.5s tolerance (scheduling overhead).
    assert abs(restart._restart_scheduled_at - expected) < 0.5


def test_get_restart_countdown_s_decrements():
    """Schedule 5s, sleep 1s, verify countdown returns ~4."""
    restart.schedule_restart(delay_s=5.0, reason="test")
    # The asyncio task was scheduled but the countdown reads
    # the module-level timestamp, not the task itself.
    first = restart.get_restart_countdown_s()
    assert first is not None
    assert 4.0 <= first <= 5.0

    time.sleep(1.0)
    second = restart.get_restart_countdown_s()
    assert second is not None
    # Should be ~1s less than the first reading.
    assert first - second >= 0.9
    assert 3.0 <= second <= 4.5


def test_cancel_scheduled_restart_clears_state():
    """After cancel, is_restart_scheduled=False + countdown=None."""
    restart.schedule_restart(delay_s=5.0, reason="test")
    assert restart.is_restart_scheduled() is True
    assert restart.get_restart_countdown_s() is not None

    cancelled = restart.cancel_scheduled_restart()
    assert cancelled is True

    assert restart.is_restart_scheduled() is False
    assert restart.get_restart_countdown_s() is None
    assert restart._restart_scheduled_at is None
    assert restart._restart_scheduled_reason == ""


def test_cancel_scheduled_restart_is_idempotent():
    """Calling cancel twice returns True once + False once."""
    restart.schedule_restart(delay_s=5.0, reason="test")
    assert restart.cancel_scheduled_restart() is True
    # Second call: nothing to cancel.
    assert restart.cancel_scheduled_restart() is False


def test_get_restart_countdown_s_returns_none_when_not_scheduled():
    """Baseline — no restart scheduled → countdown=None."""
    assert restart.get_restart_countdown_s() is None


def test_get_restart_countdown_s_floors_at_zero():
    """If the scheduled time has passed (clock manipulation
    or slow task scheduling), countdown returns 0.0 not a
    negative number."""
    restart.schedule_restart(delay_s=0.001, reason="test")
    # Wait long enough for the deadline to pass.
    time.sleep(0.5)
    countdown = restart.get_restart_countdown_s()
    assert countdown is not None
    assert countdown == 0.0
"""Sprint 19b: in-process self-restart scheduler.

When the user changes the ASR engine or corrector via
`put_voice_config`, the new values are written to
`config.toml` but the running pipeline (silero VAD +
FsmnVAD + yuesub ASR + corrector) is constructed at voice
WS connect time and doesn't reload. We need to restart
the backend process so the new values take effect.

`schedule_restart(delay_s, reason)` schedules a
self-restart using `os.execvp(sys.executable, sys.argv)`.
The exec replaces the process image in place (Unix), so
the new process reuses the same PID. No orphan, no
supervisor.

The 5-second grace period gives in-flight voice turns
time to finish. The current HTTP request that triggered
the PUT returns successfully before the exec.

We deliberately don't fork-and-exec or use a supervisor
(launchd / systemd) for Sprint 19b — the user launches
the backend themselves (no daemon mode in v1). A
follow-up sprint can add a launchd plist / systemd unit
if the in-process pattern proves fragile.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from typing import Optional

logger = logging.getLogger(__name__)


# Module-level flag set by schedule_restart so the
# put_voice_config response can include
# `restart_scheduled: true` and the GET /voice/config
# response can reflect the same value. The flag is
# cleared by any subsequent PUT that doesn't change
# the asr fields (see put_voice_config).
_restart_scheduled: bool = False
_restart_scheduled_reason: str = ""
# Sprint 41: monotonic-clock timestamp at which the
# scheduled restart will fire. None when no restart is
# scheduled. Used by `get_restart_countdown_s()` for the
# RestartNudgeBanner's live countdown. We use
# `time.monotonic()` (immune to wall-clock changes) rather
# than `time.time()`.
_restart_scheduled_at: float | None = None


def is_restart_scheduled() -> bool:
    """Whether a self-restart is pending.

    Mirrors `is_restart_required()` in
    `app.api.voice_ws` (which tracks the config-diff
    side). Both flags are reset by a non-asr PUT.
    """
    return _restart_scheduled


def _set_restart_scheduled(scheduled: bool, reason: str = "") -> None:
    """Internal helper for put_voice_config to flip the
    flag based on whether a restart is actually scheduled.

    Setting scheduled=False with a non-empty reason means
    "we evaluated a restart, decided not to do it". The
    reason is logged at DEBUG level for traceability.
    """
    global _restart_scheduled, _restart_scheduled_reason
    _restart_scheduled = scheduled
    _restart_scheduled_reason = reason
    if not scheduled:
        _restart_scheduled_at = None
        logger.debug(f"[halo.restart] restart flag cleared: reason={reason!r}")


def schedule_restart(
    delay_s: float = 5.0, reason: str = ""
) -> None:
    """Schedule a self-restart in `delay_s` seconds.

    Spawns a background asyncio task that sleeps for the
    grace period, logs a final marker line, then calls
    `os.execvp(sys.executable, sys.argv)` to replace the
    process image in place. The new process inherits the
    same CLI args (uvicorn target, host, port, log level)
    and the same PID — there's no fork, so the parent
    never sees a defunct child.

    Sprint 41: also flips `_restart_scheduled = True` and
    records the scheduled-at timestamp, so the
    RestartNudgeBanner can show a live countdown via
    `get_restart_countdown_s()`. The flag is cleared by
    `cancel_scheduled_restart()` (user-initiated cancel)
    or `_set_restart_scheduled(False)` (non-asr PUT).

    Args:
        delay_s: seconds to wait before the exec. Default
            5.0 gives in-flight voice turns time to finish
            and the user's browser time to receive the
            PUT response.
        reason: short string for the log marker. The
            caller usually passes the trigger (e.g.
            "asr_config_change").
    """
    global _restart_scheduled, _restart_scheduled_reason, _restart_scheduled_at
    _restart_scheduled = True
    _restart_scheduled_reason = reason
    _restart_scheduled_at = time.monotonic() + delay_s

    async def _do_restart() -> None:
        logger.info(
            f"[halo.restart] scheduling self-restart in "
            f"{delay_s}s: reason={reason!r}"
        )
        try:
            await asyncio.sleep(delay_s)
        except asyncio.CancelledError:
            # The event loop was cancelled (e.g. during
            # shutdown or by `cancel_scheduled_restart()`).
            # Abort the restart.
            logger.info("[halo.restart] restart cancelled")
            _restart_scheduled_at = None
            return
        # If we get here, the asyncio task wasn't cancelled
        # but the flag may have been cleared by
        # `cancel_scheduled_restart()`. Check before exec.
        if not _restart_scheduled:
            logger.info(
                "[halo.restart] restart aborted (flag cleared)"
            )
            return
        logger.info(
            f"[halo.restart] execvp {sys.executable} "
            f"{sys.argv[:5]}{'...' if len(sys.argv) > 5 else ''}"
        )
        # Replace the process image. On Unix this reuses
        # the same PID; on Windows it would spawn a new
        # process (we don't support Windows).
        try:
            os.execvp(sys.executable, sys.argv)
        except OSError as e:
            # Should never happen — execvp replaces the
            # process image so the only way it returns is
            # if it failed. Log and bail (the process
            # continues to run with the old config).
            logger.error(f"[halo.restart] execvp failed: {e}")

    # Capture the current event loop. asyncio.create_task
    # schedules the coroutine on the running loop. If
    # there's no running loop (e.g. the function is
    # called from a sync context like a thread), the
    # task is created lazily and runs the next time the
    # loop is started.
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_do_restart())
    except RuntimeError:
        # No running loop. The restart is best-effort —
        # we can't schedule it. The PUT response will
        # still report restart_scheduled=true so the
        # user can manually restart.
        logger.warning(
            "[halo.restart] no running asyncio loop; "
            "restart not scheduled. User must restart manually."
        )


def get_restart_countdown_s() -> float | None:
    """Seconds remaining until the scheduled restart fires.

    Returns None when no restart is scheduled. Uses
    `time.monotonic()` so it's immune to wall-clock changes
    (the user adjusting their clock won't break the
    countdown). Returns `max(0.0, remaining)` so the
    countdown never goes negative — once 0 is reached,
    the asyncio task has either fired or been cancelled.
    """
    if _restart_scheduled_at is None:
        return None
    remaining = _restart_scheduled_at - time.monotonic()
    return max(0.0, remaining)


def cancel_scheduled_restart() -> bool:
    """Cancel a pending self-restart (Sprint 41).

    Idempotent: returns True if a restart was actually
    cancelled, False if no restart was scheduled (safe to
    call multiple times). Sets the module-level flags so
    /voice/config immediately reports `restart_scheduled:
    false`. The asyncio task may still complete its sleep
    (we can't reach into a different event loop), but it
    checks the flag before exec and bails cleanly.

    Returns True if a cancellation actually happened.
    """
    global _restart_scheduled, _restart_scheduled_reason, _restart_scheduled_at
    was_scheduled = _restart_scheduled
    _restart_scheduled = False
    _restart_scheduled_reason = ""
    _restart_scheduled_at = None
    if was_scheduled:
        logger.info("[halo.restart] scheduled restart cancelled by user")
    return was_scheduled


__all__ = [
    "schedule_restart",
    "is_restart_scheduled",
    "_set_restart_scheduled",
    "get_restart_countdown_s",
    "cancel_scheduled_restart",
]

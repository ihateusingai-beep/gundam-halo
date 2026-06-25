"""Watchdog — crash-rate tracking for the self-healing backend (Sprint 43).

This module owns:

1. ``CrashEvent`` — a dataclass for one crash event written to
   ``$HALO_HOME/state/crash_log.jsonl``.
2. ``record_crash(home, event)`` — append + prune > 60min old.
3. ``crash_count_last_hour(home)`` — count crashes in the last 60min.
4. ``last_crash_at(home)`` — most recent crash ISO 8601 timestamp.
5. ``should_stop_respawning(home, threshold)`` — bool used by Tauri to
   decide whether to suppress the respawn loop.
6. ``clear_crash_log(home)`` — admin wipe (called from the cockpit's
   BackendHealthBanner "Clear crash log" button).

Design notes
------------
- The crash log lives at ``$HALO_HOME/state/crash_log.jsonl`` — one JSON
  object per line. We chose JSONL over JSON array because the file
  grows by append (no read-modify-write race) and rotation is just
  ``log.write_text(new_lines + "\n")``.
- The 60-minute rolling window is computed on every read — no background
  thread, no scheduled cleanup. With <100 crashes/hour the file stays
  tiny (each line ~120 bytes → ~12 KB/hr max in pathological cases).
- ``should_stop_respawning`` is the **single source of truth** for the
  H-risk respawn loop mitigation. The Tauri watchdog and the
  ``/api/system/health-detailed`` endpoint both read it.
- The threshold default is **3 crashes/hour** — chosen empirically:
  1-2 crashes/hr is normal flakiness (Mac sleep, Tailscale blip);
  3+ means something is genuinely broken (OOM, bad config, dep mismatch)
  and respawning just thrashes the box.
- Concurrent writes are protected by ``_crash_log_lock`` (threading.Lock).
  launchd is single-threaded but Tauri may write from a different thread
  if we ever add IPC-driven crash recording.
- The function NEVER raises — every operation catches + logs. The
  watchdog must never be the thing that crashes the backend.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Filename of the crash log (under $HALO_HOME/state/).
CRASH_LOG_FILENAME = "state/crash_log.jsonl"

#: Filename of the crash marker (consumed by launchd WatchPaths).
CRASH_MARKER_FILENAME = "state/crash_marker"

#: Default respawn-stop threshold (crashes per rolling 60 minutes).
DEFAULT_CRASH_THRESHOLD = 3

#: Rolling window for "crashes per hour" metrics, in seconds.
CRASH_WINDOW_SEC = 3600

#: Defensive cap on crash log size — if the file exceeds this,
#: truncate to the last MAX_LOG_LINES lines.
MAX_LOG_BYTES = 1_048_576  # 1 MB
MAX_LOG_LINES = 1000

# Thread-safe write lock. Module-level so all watchdog writers share it.
_crash_log_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------


@dataclass
class CrashEvent:
    """One crash event. JSON-serialisable for the JSONL log."""

    timestamp: str  # ISO 8601 UTC, e.g. "2026-06-26T10:30:00+00:00"
    exit_code: int
    reason: str  # "oom-killed" | "uncaught-exception" | "launchd-throttled" | "shutdown" | "unknown"
    uptime_seconds: int


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def _crash_log_path(home: Path) -> Path:
    return Path(home) / CRASH_LOG_FILENAME


def _crash_marker_path(home: Path) -> Path:
    return Path(home) / CRASH_MARKER_FILENAME


# ---------------------------------------------------------------------------
# Pruning + reading
# ---------------------------------------------------------------------------


def _parse_iso(ts: str) -> float | None:
    """Parse ISO 8601 timestamp to epoch seconds. Returns None on failure."""
    try:
        return datetime.fromisoformat(ts).timestamp()
    except (TypeError, ValueError):
        return None


def _read_valid_lines(home: Path) -> list[str]:
    """Read the crash log, dropping malformed lines + lines outside the window.

    Returns a list of JSONL-formatted strings, oldest first.
    """
    path = _crash_log_path(home)
    if not path.is_file():
        return []
    cutoff = time.time() - CRASH_WINDOW_SEC
    kept: list[str] = []
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as e:
        logger.warning(f"watchdog: failed to read crash log: {e}")
        return []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
            ts = ev.get("timestamp", "")
            epoch = _parse_iso(ts)
            if epoch is None or epoch < cutoff:
                continue
            kept.append(line)
        except (json.JSONDecodeError, TypeError):
            # Drop silently — malformed entries are noise.
            continue
    return kept


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def record_crash(home: Path, event: CrashEvent) -> Path:
    """Append a crash event to the log + prune > 60min old entries.

    Atomic via a tempfile + os.replace dance on the same directory.
    Returns the path written. Never raises.
    """
    log_path = _crash_log_path(home)
    with _crash_log_lock:
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            kept = _read_valid_lines(home)
            kept.append(json.dumps(asdict(event), ensure_ascii=False))

            # Defensive cap — if the file exceeds 1 MB or 1000 lines,
            # truncate to the last MAX_LOG_LINES lines.
            if len(kept) > MAX_LOG_LINES:
                kept = kept[-MAX_LOG_LINES:]
                logger.warning(
                    f"watchdog: crash log exceeded {MAX_LOG_LINES} lines; truncated"
                )

            # Atomic write via tempfile + replace.
            fd, tmp_path = tempfile.mkstemp(
                dir=log_path.parent, prefix=".crash_log.", suffix=".tmp"
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write("\n".join(kept) + "\n")
                os.replace(tmp_path, log_path)
            except Exception:
                # Clean up the temp file on any failure.
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
            logger.info(
                f"watchdog: recorded crash reason={event.reason} "
                f"uptime={event.uptime_seconds}s (total in window: {len(kept)})"
            )
            return log_path
        except Exception as e:
            logger.error(f"watchdog: record_crash failed: {e}")
            # NEVER raise — the watchdog must not crash the backend.
            return log_path


def crash_count_last_hour(home: Path) -> int:
    """Return the count of crashes in the last 60 minutes.

    Reads (and prunes via _read_valid_lines) the crash log. Returns 0
    if the file is missing or unreadable.
    """
    try:
        return len(_read_valid_lines(home))
    except Exception as e:
        logger.error(f"watchdog: crash_count_last_hour failed: {e}")
        return 0


def last_crash_at(home: Path) -> str | None:
    """Return the ISO 8601 timestamp of the most recent crash, or None."""
    try:
        lines = _read_valid_lines(home)
        if not lines:
            return None
        latest: str | None = None
        for line in lines:
            try:
                ev = json.loads(line)
                ts = ev.get("timestamp", "")
                if ts and (latest is None or ts > latest):
                    latest = ts
            except (json.JSONDecodeError, TypeError):
                continue
        return latest
    except Exception as e:
        logger.error(f"watchdog: last_crash_at failed: {e}")
        return None


def should_stop_respawning(
    home: Path, threshold: int = DEFAULT_CRASH_THRESHOLD
) -> bool:
    """True if the crash count in the last 60 minutes exceeds *threshold*.

    This is the H-risk mitigation gate. Called by the Tauri watchdog
    and the ``/api/system/health-detailed`` endpoint on every check.
    """
    return crash_count_last_hour(home) >= threshold


def clear_crash_log(home: Path) -> int:
    """Truncate the crash log. Returns the number of events cleared.

    Called by the cockpit's "Clear crash log & retry" button. Does
    NOT touch the crash marker file (that file is owned by launchd
    WatchPaths and is removed by the crash hook script).
    """
    log_path = _crash_log_path(home)
    with _crash_log_lock:
        try:
            if not log_path.is_file():
                return 0
            count = sum(
                1
                for line in log_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            )
            log_path.unlink()
            logger.info(f"watchdog: cleared crash log ({count} events)")
            return count
        except Exception as e:
            logger.error(f"watchdog: clear_crash_log failed: {e}")
            return 0


def write_crash_marker(
    home: Path,
    exit_code: int = 1,
    reason: str = "shutdown",
    uptime_seconds: int = 0,
) -> None:
    """Write the crash marker file (consumed by launchd WatchPaths).

    The marker is a newline-separated KEY=VALUE file:
        exit_code=1
        reason=oom-killed
        uptime_seconds=3600

    Called from ``app/main.py`` shutdown hook + uncaught exception
    handler. The actual JSONL write happens via
    ``scripts/on-launchd-crash.sh`` after launchd fires the WatchPaths
    trigger. This indirection is necessary because launchd has no
    built-in "process crashed" callback — WatchPaths is the closest
    primitive.
    """
    marker = _crash_marker_path(home)
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(
            f"exit_code={exit_code}\nreason={reason}\nuptime_seconds={uptime_seconds}\n",
            encoding="utf-8",
        )
    except Exception as e:
        logger.error(f"watchdog: write_crash_marker failed: {e}")


# ---------------------------------------------------------------------------
# launchd helpers — read supervisor install state
# ---------------------------------------------------------------------------


def is_launchd_supervisor_loaded() -> bool:
    """True if ``com.gundam.halo`` plist is loaded in launchd.

    Runs ``launchctl list`` and greps for the label. Returns False
    on any error (binary missing, timeout, parse error). Never raises.
    """
    import subprocess

    try:
        result = subprocess.run(
            ["launchctl", "list"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        return "com.gundam.halo" in result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        logger.debug(f"watchdog: launchctl list failed: {e}")
        return False


def get_launchd_pid() -> int | None:
    """Return the PID of the running uvicorn process supervised by launchd.

    Runs ``launchctl list com.gundam.halo`` and parses the output.
    Returns None if not running or any error. Never raises.
    """
    import subprocess

    try:
        result = subprocess.run(
            ["launchctl", "list", "com.gundam.halo"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        # launchctl output format: "PID\tStatus\tLabel"
        # PID is "-" if not running.
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 3 and parts[2] == "com.gundam.halo":
                try:
                    return int(parts[0])
                except ValueError:
                    return None
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        logger.debug(f"watchdog: launchctl list com.gundam.halo failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Module exports
# ---------------------------------------------------------------------------


__all__ = [
    "CRASH_LOG_FILENAME",
    "CRASH_MARKER_FILENAME",
    "CrashEvent",
    "DEFAULT_CRASH_THRESHOLD",
    "clear_crash_log",
    "crash_count_last_hour",
    "get_launchd_pid",
    "is_launchd_supervisor_loaded",
    "last_crash_at",
    "record_crash",
    "should_stop_respawning",
    "write_crash_marker",
]

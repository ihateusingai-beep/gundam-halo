"""Sprint 48 — audit log + security helpers.

JSONL audit log at `$HALO_HOME/logs/audit.log`. One line per
event (auth failure, privileged call success/failure, etc.).
Rotates at 1 MB; old file moves to `audit.log.1`.

The log is **best-effort**: errors writing the audit log NEVER
mask the underlying operation. If the disk is full or the file
is corrupted, we log a WARNING and continue.

Format (per line):
    {"ts": 1782732509.123, "event": "auth_failure", "reason":
     "bad-bearer", "method": "POST", "path": "/api/system/
     clear-crash-log", "src_ip": "100.100.100.42", "user_agent":
     "GundamHalo/0.1.20"}

Lines that don't parse as JSON are silently dropped on read.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Size cap for the active audit log. Rotation moves the active
# file to `audit.log.1` (overwriting any prior `audit.log.1`).
# We keep ONE generation, not N, because the audit log is short-lived
# (a few KB per day under normal use). Bump if real-world load
# justifies more retention.
_MAX_BYTES = 1_000_000  # 1 MB
_LOG_FILENAME = "audit.log"
_LOG_BACKUP_FILENAME = "audit.log.1"

# Thread-safe append (Tauri watchdog + eval job threads may all
# write concurrently).
_lock = threading.Lock()


def audit_log_path(home: Path | None = None) -> Path:
    """Resolve the audit log file path.

    Honours $HALO_HOME (set by tests). Default: ~/.gundam-halo/logs/audit.log.
    The directory is created lazily on first write.
    """
    if home is None:
        env = os.environ.get("HALO_HOME")
        home = Path(env).expanduser().resolve() if env else (Path.home() / ".gundam-halo")
    return home / "logs" / _LOG_FILENAME


def append_audit_log(event: dict[str, Any]) -> None:
    """Append one JSONL line to the audit log.

    Best-effort: never raises. Spawning a watchdog event that
    crashes the backend because the audit log is full would be
    worse than missing one event.

    Includes an automatic rotation: if the file grows past
    _MAX_BYTES, the existing file is renamed to `audit.log.1`
    (overwriting) and a fresh log starts.
    """
    try:
        path = audit_log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        # Ensure the timestamp is set if the caller didn't.
        event.setdefault("ts", time.time())
        line = json.dumps(event, ensure_ascii=False) + "\n"
        with _lock:
            if path.exists() and path.stat().st_size >= _MAX_BYTES:
                backup = path.parent / _LOG_BACKUP_FILENAME
                if backup.exists():
                    backup.unlink()
                path.rename(backup)
            with path.open("a", encoding="utf-8") as f:
                f.write(line)
    except OSError as e:
        # Disk full, permission denied, etc. — log + continue.
        logger.warning("Sprint 48 audit log: append failed: %s", e)


def read_audit_log(home: Path | None = None, limit: int = 100) -> list[dict[str, Any]]:
    """Read the most recent `limit` audit events (newest-first).

    Skips malformed JSONL lines silently. Used by the audit-log
    diagnostic endpoint (out of scope for Sprint 48 — placeholder
    for future Sprint 49+).
    """
    path = audit_log_path(home)
    if not path.is_file():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    rows: list[dict[str, Any]] = []
    for raw in reversed(lines):
        try:
            rows.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
        if len(rows) >= limit:
            break
    return rows


def rotate_audit_log(home: Path | None = None) -> bool:
    """Force-rotate the audit log. Returns True if a rotation
    actually happened.

    Implements the TODO from Sprint 13's docs/SECURITY-HARDENING.md:
    "auto-rotate audit log file". The auto-rotation in
    `append_audit_log` handles normal use; this function is for
    manual triggers (e.g. once a day from a cron job, or after
    a sensitive operation).
    """
    path = audit_log_path(home)
    if not path.is_file():
        return False
    if path.stat().st_size == 0:
        return False
    backup = path.parent / _LOG_BACKUP_FILENAME
    if backup.exists():
        backup.unlink()
    path.rename(backup)
    return True


__all__ = [
    "append_audit_log",
    "read_audit_log",
    "rotate_audit_log",
    "audit_log_path",
]
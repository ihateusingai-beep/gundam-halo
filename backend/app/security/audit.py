"""Append-only audit log for Mac control actions.

Every file read, file write, shell command, AppleScript, etc. is logged
here for security review. NDJSON format (one JSON object per line).
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Optional

from app.core.config import get_config
from app.core.events import Event, EventBus, EventType, get_event_bus

logger = logging.getLogger(__name__)


class AuditLogger:
    """Append-only NDJSON audit log writer.

    Thread-safe. Bounded file size (rotates when too large).
    """

    def __init__(self, log_path: Path, max_size_mb: int = 100) -> None:
        self.log_path = Path(log_path)
        self.max_size_bytes = max_size_mb * 1024 * 1024
        self._lock = Lock()

        # Ensure parent dir exists
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def _maybe_rotate(self) -> None:
        """Rotate log if too large."""
        if not self.log_path.exists():
            return
        if self.log_path.stat().st_size < self.max_size_bytes:
            return
        # Rotate: rename current to .1, .2, etc. Keep 3 most recent.
        for i in range(2, 0, -1):
            older = self.log_path.with_suffix(f".{i}.log")
            newer = self.log_path.with_suffix(f".{i+1}.log") if i < 3 else None
            if older.exists() and newer:
                older.rename(newer)
        self.log_path.rename(self.log_path.with_suffix(".1.log"))

    def write(self, event: Event) -> None:
        """Append event to log (NDJSON)."""
        record = {
            "id": uuid.uuid4().hex,
            "ts": datetime.fromtimestamp(event.timestamp, tz=timezone.utc).isoformat(),
            "event_type": event.event_type.value,
            "data": event.data,
        }
        line = json.dumps(record, ensure_ascii=False, default=str) + "\n"
        with self._lock:
            self._maybe_rotate()
            with open(self.log_path, "a") as f:
                f.write(line)
                f.flush()
                os.fsync(f.fileno())

    def tail(self, n: int = 100) -> list[dict]:
        """Read last N records (most recent first)."""
        if not self.log_path.exists():
            return []
        with self._lock:
            with open(self.log_path) as f:
                lines = f.readlines()
        records = []
        for line in reversed(lines[-n:]):
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return records


# ---------------------------------------------------------------------------
# Module-level singleton + bus subscription
# ---------------------------------------------------------------------------

_logger: Optional[AuditLogger] = None


def get_audit_logger() -> AuditLogger:
    global _logger
    if _logger is None:
        from app.core.config import expand_home

        cfg = get_config()
        _logger = AuditLogger(
            log_path=expand_home(cfg.security.audit_log),
            max_size_mb=cfg.security.audit_max_size_mb,
        )
        # Subscribe to all MAC_OP_* events
        for et in [EventType.MAC_OP_START, EventType.MAC_OP_END, EventType.MAC_OP_AUDIT, EventType.MAC_OP_BLOCKED]:
            get_event_bus().subscribe(et, _logger.write)
        # Chmod 600 on the log file
        if _logger.log_path.exists():
            os.chmod(_logger.log_path, 0o600)
    return _logger


def reset_audit_logger() -> None:
    global _logger
    _logger = None


__all__ = ["AuditLogger", "get_audit_logger", "reset_audit_logger"]

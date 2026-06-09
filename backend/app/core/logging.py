"""Structured logging configuration.

Uses stdlib logging with a simple JSON-style formatter. Avoids extra deps
for now — can swap in `structlog` later if needed.

M7-Phase-0: also installs a `BackendLogHandler` that publishes
INFO+ log records to the EventBus as `BACKEND_LOG` events. The
main `/ws` channel broadcasts those to every connected client,
where the ActivityTicker renders them as a slim `[log]` chip
with the level + message.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    """Format log records as single-line JSON."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        # Include any extra fields
        for k, v in record.__dict__.items():
            if k not in {
                "name", "msg", "args", "levelname", "levelno", "pathname",
                "filename", "module", "exc_info", "exc_text", "stack_info",
                "lineno", "funcName", "created", "msecs", "relativeCreated",
                "thread", "threadName", "processName", "process", "taskName",
            }:
                payload[k] = v
        return json.dumps(payload, ensure_ascii=False, default=str)


class BackendLogHandler(logging.Handler):
    """Publishes log records onto the EventBus.

    Keeps the existing stdout stream handler for the terminal / docker
    logs. This one is a *secondary* sink for the cockpit UI.
    """

    def __init__(self, level: int = logging.INFO) -> None:
        super().__init__(level=level)
        # Lazy import — avoid forcing the event_bus module on every
        # import of this file (it's imported very early).
        from app.core.events import EventType, get_event_bus
        self._EventType = EventType
        self._get_event_bus = get_event_bus

    def emit(self, record: logging.LogRecord) -> None:
        try:
            # Avoid feedback loop: don't publish records produced by
            # the EventBus itself or the WS broadcaster.
            if record.name.startswith(("app.core.events", "app.api.ws")):
                return
            # Keep the bus queue short — cap to INFO+ to avoid
            # DEBUG spam hitting the dashboard.
            if record.levelno < logging.INFO:
                return
            self._get_event_bus().publish(
                self._EventType.BACKEND_LOG,
                {
                    "level": record.levelname,
                    "logger": record.name,
                    "msg": record.getMessage(),
                },
            )
        except Exception:  # noqa: BLE001
            # Never let a logging handler take down the process.
            self.handleError(record)


def configure_logging(level: str = "INFO", json_format: bool = True) -> None:
    """Configure root logger."""
    root = logging.getLogger()
    # Clear existing handlers (idempotent)
    for h in list(root.handlers):
        root.removeHandler(h)

    handler = logging.StreamHandler(sys.stdout)
    if json_format:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%H:%M:%S",
            )
        )
    root.addHandler(handler)
    root.setLevel(level.upper())

    # Add the bus-publishing handler as a sibling sink
    root.addHandler(BackendLogHandler(level=logging.INFO))


__all__ = ["configure_logging", "JsonFormatter", "BackendLogHandler"]

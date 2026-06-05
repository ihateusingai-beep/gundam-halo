"""Thread-safe pub/sub event bus for inter-primitive telemetry.

Inspired by OpenJarvis (Apache 2.0) — reimplemented under MIT for Gundam Halo.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


# ---------------------------------------------------------------------------
# Event taxonomy
# ---------------------------------------------------------------------------


class EventType(str, Enum):
    """Supported event categories for Gundam Halo."""

    # LLM
    INFERENCE_START = "inference_start"
    INFERENCE_END = "inference_end"

    # Tools
    TOOL_CALL_START = "tool_call_start"
    TOOL_CALL_END = "tool_call_end"

    # Agent
    AGENT_TURN_START = "agent_turn_start"
    AGENT_TURN_END = "agent_turn_end"

    # Session / Project
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    SESSION_MESSAGE_RECEIVED = "session_message_received"

    # Project
    PROJECT_CREATED = "project_created"
    PROJECT_ARCHIVED = "project_archived"

    # Channel
    CHANNEL_MESSAGE_RECEIVED = "channel_message_received"
    CHANNEL_MESSAGE_SENT = "channel_message_sent"

    # Mac control
    MAC_OP_START = "mac_op_start"
    MAC_OP_END = "mac_op_end"
    MAC_OP_BLOCKED = "mac_op_blocked"
    MAC_OP_AUDIT = "mac_op_audit"

    # Security
    SECURITY_SCAN = "security_scan"
    SECURITY_ALERT = "security_alert"
    SECURITY_BLOCK = "security_block"

    # System
    SYSTEM_GAUGES = "system_gauges"
    SYSTEM_ERROR = "system_error"


@dataclass(slots=True)
class Event:
    """A single event published on the bus."""

    event_type: EventType
    timestamp: float
    data: Dict[str, Any] = field(default_factory=dict)


# Type alias for subscriber callbacks
Subscriber = Callable[[Event], None]


# ---------------------------------------------------------------------------
# EventBus
# ---------------------------------------------------------------------------


class EventBus:
    """Thread-safe publish/subscribe event bus.

    Subscribers are called synchronously in registration order within the
    publishing thread. An optional *record_history* flag retains all
    published events for later inspection (useful in tests/telemetry).
    """

    def __init__(self, *, record_history: bool = False) -> None:
        self._subscribers: Dict[EventType, List[Subscriber]] = {}
        self._lock = threading.Lock()
        self._record_history = record_history
        self._history: List[Event] = []

    def subscribe(self, event_type: EventType, callback: Subscriber) -> None:
        with self._lock:
            self._subscribers.setdefault(event_type, []).append(callback)

    def unsubscribe(self, event_type: EventType, callback: Subscriber) -> None:
        with self._lock:
            listeners = self._subscribers.get(event_type, [])
            try:
                listeners.remove(callback)
            except ValueError:
                pass

    def publish(
        self,
        event_type: EventType,
        data: Optional[Dict[str, Any]] = None,
    ) -> Event:
        event = Event(event_type=event_type, timestamp=time.time(), data=data or {})

        with self._lock:
            if self._record_history:
                self._history.append(event)
            listeners = list(self._subscribers.get(event_type, []))

        for callback in listeners:
            try:
                callback(event)
            except Exception as e:
                # Don't let one bad subscriber kill the publisher
                # (logger would be ideal here, but avoid circular import)
                print(f"EventBus subscriber error: {e}", flush=True)

        return event

    @property
    def history(self) -> List[Event]:
        with self._lock:
            return list(self._history)

    def clear_history(self) -> None:
        with self._lock:
            self._history.clear()


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_bus: Optional[EventBus] = None
_bus_lock = threading.Lock()


def get_event_bus(*, record_history: bool = False) -> EventBus:
    """Return the module-level EventBus singleton, creating it if needed."""
    global _bus
    with _bus_lock:
        if _bus is None:
            _bus = EventBus(record_history=record_history)
        return _bus


def reset_event_bus() -> None:
    """Replace the singleton with a fresh instance (for tests)."""
    global _bus
    with _bus_lock:
        _bus = None


__all__ = [
    "Event",
    "EventBus",
    "EventType",
    "Subscriber",
    "get_event_bus",
    "reset_event_bus",
]

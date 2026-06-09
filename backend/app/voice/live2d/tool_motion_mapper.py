"""ToolMotionMapper — translate tool calls into Live2D avatar reactions.

Subscribes to the EventBus and, for every TOOL_CALL_START / TOOL_CALL_END,
publishes a LIVE2D_TOOL_TRIGGER with the appropriate (expression, motion,
emotion) triple from `EMOTION_MAP`. This makes the avatar react in real
time to the agent's actions even when the user isn't speaking — the
cockpit feels alive.

Design:
- The mapping is a *table*, not code. New tools = new row. No special
  handling for unknown tools (default fallback).
- Two mapping slots per tool: `start` (TOOL_CALL_START) and `end` (with
  either `ok=True` or `ok=False`). The end mapping is symmetric to start
  so the avatar visibly "completes" the action.
- The mapping reuses the same emotion DSL the LLM already speaks (see
  `halo_responder.EMOTION_MAP`), so the CSS Avatar's class map and the
  real Live2D model agree on the same vocabulary.
- The mapper is a *passive* subscriber: it just publishes events. It does
  not own any state beyond the start() / stop() flag.

Wired into the FastAPI lifespan in `app/main.py` so the subscriber lives
exactly as long as the server.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

from app.core.events import Event, EventBus, EventType, get_event_bus

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Mapping table
# ---------------------------------------------------------------------------
#
# Each entry maps a tool name to a dict with two trigger frames:
#   - "start": emitted on TOOL_CALL_START
#   - "end":   emitted on TOOL_CALL_END (used for both ok=True and ok=False;
#              the ok case adds a brief celebratory touch, the failure case
#              flinches).
#
# The trigger frame has the same shape the voice WS uses for
# `live2d.trigger`, so the frontend avatar bridge can dispatch both through
# the same code path.
#
# `expression` and `motion` come from the NTDResponder / Live2D model.
# `emotion` is the key in `EMOTION_MAP` that the LLM uses (and the CSS
# avatar's class map uses).

_TOOL_TRIGGER = dict  # alias for readability

TOOL_MOTION_MAP: dict[str, dict[str, _TOOL_TRIGGER]] = {
    # Reading — the agent leans into the user's file
    "file_read": {
        "start": {"expression": "ntd_focused", "motion": "lean_in", "emotion": "focused"},
        "end":   {"expression": "ntd_calm",    "motion": "idle",    "emotion": "calm"},
    },
    # Writing — the agent commits; resolve posture
    "file_write": {
        "start": {"expression": "ntd_resolve", "motion": "stand",   "emotion": "resolve"},
        "end":   {"expression": "ntd_calm",    "motion": "idle",    "emotion": "calm"},
    },
    # Shell exec — alert, scanning output
    "shell_exec": {
        "start": {"expression": "ntd_alert",   "motion": "scan",    "emotion": "alert"},
        "end":   {"expression": "ntd_calm",    "motion": "idle",    "emotion": "calm"},
    },
    # Spotlight search — scanning posture, alert
    "spotlight_search": {
        "start": {"expression": "ntd_alert",   "motion": "scan",    "emotion": "alert"},
        "end":   {"expression": "ntd_calm",    "motion": "idle",    "emotion": "calm"},
    },
    # Open an app — small celebration
    "open_app": {
        "start": {"expression": "ntd_jubilant", "motion": "victory", "emotion": "jubilant"},
        "end":   {"expression": "ntd_calm",     "motion": "idle",    "emotion": "calm"},
    },
    # Delegate to Mavis — handing off, full psychoframe awakening
    "mavis_delegate": {
        "start": {"expression": "ntd_psychoframe", "motion": "awaken", "emotion": "awakening"},
        "end":   {"expression": "ntd_calm",        "motion": "idle",   "emotion": "calm"},
    },
}

# Fallback when the tool name isn't in the table (e.g. a new custom tool).
DEFAULT_TOOL_TRIGGER: _TOOL_TRIGGER = {
    "start": {"expression": "ntd_focused", "motion": "lean_in", "emotion": "focused"},
    "end":   {"expression": "ntd_calm",    "motion": "idle",    "emotion": "calm"},
}

# Failure frame — used when TOOL_CALL_END.ok is False. Overrides the tool's
# normal end frame so the avatar visibly flinches on error.
FAILURE_TRIGGER: _TOOL_TRIGGER = {
    "expression": "ntd_damage",
    "motion": "flinch",
    "emotion": "damage",
}


# ---------------------------------------------------------------------------
# Mapper
# ---------------------------------------------------------------------------


class ToolMotionMapper:
    """EventBus subscriber that publishes LIVE2D_TOOL_TRIGGER events.

    Lifecycle:
        mapper = ToolMotionMapper()   # no-op until start()
        mapper.start()                # subscribes to TOOL_CALL_*
        ...                           # events flow
        mapper.stop()                 # unsubscribes
    """

    def __init__(self, bus: Optional[EventBus] = None) -> None:
        self._bus = bus
        self._running = False
        # Store handler references so unsubscribe can find them
        self._on_start: Optional[Callable[[Event], None]] = None
        self._on_end: Optional[Callable[[Event], None]] = None

    def start(self) -> None:
        """Subscribe to TOOL_CALL_START / TOOL_CALL_END on the bus."""
        if self._running:
            return
        bus = self._bus or get_event_bus()

        self._on_start = self._handle_tool_start
        self._on_end = self._handle_tool_end

        bus.subscribe(EventType.TOOL_CALL_START, self._on_start)
        bus.subscribe(EventType.TOOL_CALL_END, self._on_end)
        self._running = True
        logger.info("ToolMotionMapper started")

    def stop(self) -> None:
        """Unsubscribe from the bus."""
        if not self._running:
            return
        bus = self._bus or get_event_bus()
        if self._on_start is not None:
            bus.unsubscribe(EventType.TOOL_CALL_START, self._on_start)
        if self._on_end is not None:
            bus.unsubscribe(EventType.TOOL_CALL_END, self._on_end)
        self._running = False
        logger.info("ToolMotionMapper stopped")

    # ------------------------------------------------------------------
    # Public helpers (also used by tests)
    # ------------------------------------------------------------------

    @staticmethod
    def map_start(tool: str) -> _TOOL_TRIGGER:
        """Resolve the 'start' trigger frame for *tool*."""
        return TOOL_MOTION_MAP.get(tool, DEFAULT_TOOL_TRIGGER)["start"]

    @staticmethod
    def map_end(tool: str, ok: bool) -> _TOOL_TRIGGER:
        """Resolve the 'end' trigger frame for *tool*.

        A failed tool call always uses FAILURE_TRIGGER so the avatar
        visibly flinches regardless of the tool's normal end frame.
        """
        if not ok:
            return FAILURE_TRIGGER
        return TOOL_MOTION_MAP.get(tool, DEFAULT_TOOL_TRIGGER)["end"]

    # ------------------------------------------------------------------
    # Internal handlers
    # ------------------------------------------------------------------

    def _handle_tool_start(self, event: Event) -> None:
        tool = event.data.get("tool", "unknown")
        trigger = self.map_start(tool)
        self._publish(tool, "start", trigger, event.data)

    def _handle_tool_end(self, event: Event) -> None:
        tool = event.data.get("tool", "unknown")
        ok = bool(event.data.get("ok", False))
        trigger = self.map_end(tool, ok)
        self._publish(tool, "end", trigger, event.data)

    def _publish(
        self,
        tool: str,
        phase: str,
        trigger: _TOOL_TRIGGER,
        source: dict,
    ) -> None:
        bus = self._bus or get_event_bus()
        bus.publish(
            EventType.LIVE2D_TOOL_TRIGGER,
            {
                "source": "tool",
                "tool": tool,
                "phase": phase,   # "start" | "end"
                "ok": source.get("ok"),  # only meaningful on end
                "call_id": source.get("call_id"),
                "session_id": source.get("session_id"),
                "project": source.get("project"),
                "expression": trigger["expression"],
                "motion": trigger["motion"],
                "emotion": trigger["emotion"],
            },
        )


__all__ = [
    "ToolMotionMapper",
    "TOOL_MOTION_MAP",
    "DEFAULT_TOOL_TRIGGER",
    "FAILURE_TRIGGER",
]

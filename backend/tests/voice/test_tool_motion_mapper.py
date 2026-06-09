"""Tests for ToolMotionMapper — tool calls → Live2D avatar triggers.

Verifies:
- Per-tool start/end frame selection
- Failure override (failed tool always flinches)
- Unknown-tool fallback
- EventBus wiring (subscriber receives TOOL_CALL_*, publishes LIVE2D_TOOL_TRIGGER)
- Lifecycle (start/stop is idempotent and cleans up subscribers)
"""

from __future__ import annotations

import pytest

from app.core.events import EventBus, EventType
from app.voice.live2d.tool_motion_mapper import (
    DEFAULT_TOOL_TRIGGER,
    FAILURE_TRIGGER,
    TOOL_MOTION_MAP,
    ToolMotionMapper,
)


# ---------------------------------------------------------------------------
# Pure-function mapping (no bus required)
# ---------------------------------------------------------------------------


class TestMapStart:
    """`map_start` returns the 'start' frame for known / unknown tools."""

    def test_file_read_leans_in(self) -> None:
        assert ToolMotionMapper.map_start("file_read") == {
            "expression": "ntd_focused",
            "motion": "lean_in",
            "emotion": "focused",
        }

    def test_open_app_is_jubilant(self) -> None:
        assert ToolMotionMapper.map_start("open_app") == {
            "expression": "ntd_jubilant",
            "motion": "victory",
            "emotion": "jubilant",
        }

    def test_mavis_delegate_is_psychoframe(self) -> None:
        assert ToolMotionMapper.map_start("mavis_delegate") == {
            "expression": "ntd_psychoframe",
            "motion": "awaken",
            "emotion": "awakening",
        }

    def test_unknown_tool_uses_default(self) -> None:
        assert ToolMotionMapper.map_start("totally_made_up") == DEFAULT_TOOL_TRIGGER["start"]

    def test_all_known_tools_have_start_frame(self) -> None:
        for tool, frames in TOOL_MOTION_MAP.items():
            assert "start" in frames, f"tool {tool!r} missing 'start' frame"
            for field in ("expression", "motion", "emotion"):
                assert field in frames["start"], (
                    f"tool {tool!r} start frame missing {field!r}"
                )


class TestMapEnd:
    """`map_end` respects ok=True/False; failure always flinch."""

    def test_success_uses_tool_end(self) -> None:
        assert ToolMotionMapper.map_end("file_read", ok=True) == {
            "expression": "ntd_calm",
            "motion": "idle",
            "emotion": "calm",
        }

    def test_failure_overrides_with_damage(self) -> None:
        # Even a tool that normally ends in 'calm' flinches on failure
        assert ToolMotionMapper.map_end("file_read", ok=False) == FAILURE_TRIGGER

    def test_failure_is_independent_of_tool(self) -> None:
        # No matter which tool failed, the avatar should flinch
        for tool in ("file_read", "open_app", "mavis_delegate", "shell_exec"):
            assert ToolMotionMapper.map_end(tool, ok=False) == FAILURE_TRIGGER

    def test_unknown_tool_end_uses_default(self) -> None:
        assert ToolMotionMapper.map_end("unknown_xyz", ok=True) == (
            DEFAULT_TOOL_TRIGGER["end"]
        )


# ---------------------------------------------------------------------------
# EventBus wiring
# ---------------------------------------------------------------------------


class TestEventBusWiring:
    """The mapper subscribes to TOOL_CALL_* and publishes LIVE2D_TOOL_TRIGGER."""

    def _build_bus_with_mapper(self) -> tuple[EventBus, ToolMotionMapper]:
        bus = EventBus(record_history=True)
        mapper = ToolMotionMapper(bus=bus)
        mapper.start()
        return bus, mapper

    def test_start_emits_live2d_trigger_with_start_frame(self) -> None:
        bus, mapper = self._build_bus_with_mapper()
        bus.publish(
            EventType.TOOL_CALL_START,
            {
                "call_id": "call-1",
                "tool": "file_read",
                "args": {"path": "/etc/hosts"},
                "session_id": "sess-1",
            },
        )
        triggers = [e for e in bus.history if e.event_type == EventType.LIVE2D_TOOL_TRIGGER]
        assert len(triggers) == 1
        data = triggers[0].data
        assert data["source"] == "tool"
        assert data["tool"] == "file_read"
        assert data["phase"] == "start"
        assert data["call_id"] == "call-1"
        assert data["session_id"] == "sess-1"
        assert data["emotion"] == "focused"
        assert data["expression"] == "ntd_focused"
        assert data["motion"] == "lean_in"

    def test_end_ok_emits_end_frame(self) -> None:
        bus, mapper = self._build_bus_with_mapper()
        bus.publish(
            EventType.TOOL_CALL_END,
            {
                "call_id": "call-2",
                "tool": "open_app",
                "ok": True,
                "duration_ms": 42,
            },
        )
        triggers = [e for e in bus.history if e.event_type == EventType.LIVE2D_TOOL_TRIGGER]
        assert len(triggers) == 1
        data = triggers[0].data
        assert data["phase"] == "end"
        assert data["ok"] is True
        # open_app's "end" frame is calm
        assert data["emotion"] == "calm"
        assert data["expression"] == "ntd_calm"

    def test_end_failure_emits_damage(self) -> None:
        bus, mapper = self._build_bus_with_mapper()
        bus.publish(
            EventType.TOOL_CALL_END,
            {
                "call_id": "call-3",
                "tool": "file_write",
                "ok": False,
                "duration_ms": 12,
            },
        )
        triggers = [e for e in bus.history if e.event_type == EventType.LIVE2D_TOOL_TRIGGER]
        assert len(triggers) == 1
        data = triggers[0].data
        assert data["emotion"] == "damage"
        assert data["expression"] == "ntd_damage"
        assert data["motion"] == "flinch"
        assert data["ok"] is False

    def test_multi_tool_sequence(self) -> None:
        """A start+end pair produces exactly 2 trigger events in order."""
        bus, mapper = self._build_bus_with_mapper()
        for tool in ("file_read", "file_write", "shell_exec"):
            bus.publish(
                EventType.TOOL_CALL_START,
                {"call_id": f"c-{tool}", "tool": tool},
            )
            bus.publish(
                EventType.TOOL_CALL_END,
                {"call_id": f"c-{tool}", "tool": tool, "ok": True},
            )
        triggers = [e for e in bus.history if e.event_type == EventType.LIVE2D_TOOL_TRIGGER]
        assert len(triggers) == 6
        # Verify the order: start, end, start, end, start, end
        phases = [t.data["phase"] for t in triggers]
        assert phases == ["start", "end", "start", "end", "start", "end"]
        # And the tools are interleaved correctly
        assert [t.data["tool"] for t in triggers] == [
            "file_read", "file_read",
            "file_write", "file_write",
            "shell_exec", "shell_exec",
        ]

    def test_unknown_tool_falls_back(self) -> None:
        bus, mapper = self._build_bus_with_mapper()
        bus.publish(
            EventType.TOOL_CALL_START,
            {"call_id": "c-unknown", "tool": "hypothetical_future_tool"},
        )
        triggers = [e for e in bus.history if e.event_type == EventType.LIVE2D_TOOL_TRIGGER]
        assert len(triggers) == 1
        # DEFAULT_TOOL_TRIGGER["start"] is focused
        assert triggers[0].data["emotion"] == "focused"


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


class TestLifecycle:
    """`start()` is idempotent; `stop()` unsubscribes cleanly."""

    def test_start_is_idempotent(self) -> None:
        bus = EventBus(record_history=True)
        mapper = ToolMotionMapper(bus=bus)
        mapper.start()
        mapper.start()  # should not double-subscribe
        # Publish a TOOL_CALL_START; should see exactly 1 trigger
        bus.publish(EventType.TOOL_CALL_START, {"call_id": "x", "tool": "file_read"})
        triggers = [e for e in bus.history if e.event_type == EventType.LIVE2D_TOOL_TRIGGER]
        assert len(triggers) == 1

    def test_stop_unsubscribes(self) -> None:
        bus = EventBus(record_history=True)
        mapper = ToolMotionMapper(bus=bus)
        mapper.start()
        mapper.stop()
        # After stop, publishing should not produce any trigger
        bus.publish(EventType.TOOL_CALL_START, {"call_id": "x", "tool": "file_read"})
        triggers = [e for e in bus.history if e.event_type == EventType.LIVE2D_TOOL_TRIGGER]
        assert len(triggers) == 0

    def test_stop_is_idempotent(self) -> None:
        bus = EventBus()
        mapper = ToolMotionMapper(bus=bus)
        mapper.start()
        mapper.stop()
        mapper.stop()  # no-op, no error

    def test_double_start_then_stop_publishes_once(self) -> None:
        bus = EventBus(record_history=True)
        mapper = ToolMotionMapper(bus=bus)
        mapper.start()
        mapper.start()  # idempotent
        bus.publish(EventType.TOOL_CALL_START, {"call_id": "x", "tool": "file_read"})
        bus.publish(EventType.TOOL_CALL_START, {"call_id": "y", "tool": "open_app"})
        triggers = [e for e in bus.history if e.event_type == EventType.LIVE2D_TOOL_TRIGGER]
        # Both events produce triggers, but each fires only once per publish.
        assert len(triggers) == 2
        mapper.stop()
        # After stop, no more triggers
        bus.publish(EventType.TOOL_CALL_START, {"call_id": "z", "tool": "file_read"})
        assert sum(
            1 for e in bus.history if e.event_type == EventType.LIVE2D_TOOL_TRIGGER
        ) == 2

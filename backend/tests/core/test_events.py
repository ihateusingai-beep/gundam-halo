"""Tests for the event bus."""
import pytest

from app.core.events import EventBus, EventType, get_event_bus, reset_event_bus


def test_publish_and_subscribe():
    bus = EventBus()
    received = []
    bus.subscribe(EventType.INFERENCE_START, lambda e: received.append(e))
    bus.publish(EventType.INFERENCE_START, {"foo": "bar"})
    assert len(received) == 1
    assert received[0].data == {"foo": "bar"}


def test_history_recording():
    bus = EventBus(record_history=True)
    bus.publish(EventType.TOOL_CALL_START, {"tool": "file_read"})
    bus.publish(EventType.TOOL_CALL_END, {"tool": "file_read", "ok": True})
    assert len(bus.history) == 2
    assert bus.history[0].event_type == EventType.TOOL_CALL_START


def test_subscriber_error_does_not_break_publisher():
    bus = EventBus()
    received = []

    def bad_cb(e):
        raise RuntimeError("oops")

    def good_cb(e):
        received.append(e)

    bus.subscribe(EventType.MAC_OP_START, bad_cb)
    bus.subscribe(EventType.MAC_OP_START, good_cb)
    bus.publish(EventType.MAC_OP_START, {})
    # good_cb should still be called even though bad_cb raised
    assert len(received) == 1


def test_unsubscribe_idempotent():
    bus = EventBus()
    cb = lambda e: None
    bus.unsubscribe(EventType.INFERENCE_END, cb)  # no-op, no error
    bus.subscribe(EventType.INFERENCE_END, cb)
    bus.unsubscribe(EventType.INFERENCE_END, cb)
    bus.unsubscribe(EventType.INFERENCE_END, cb)  # idempotent

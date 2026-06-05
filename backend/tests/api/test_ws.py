"""Tests for the /ws WebSocket endpoint."""

import concurrent.futures
import json
import time

import pytest
from fastapi.testclient import TestClient

from app.core.events import Event, EventType, get_event_bus, reset_event_bus
from app.main import halo_app


@pytest.fixture
def client():
    return TestClient(halo_app)


# All tests in this module need permissive policy
pytestmark = pytest.mark.usefixtures("permissive_test_config")


def _receive_with_timeout(ws, timeout=1.0):
    """Receive a JSON message from WS with a hard timeout.

    starlette's TestClient WebSocketTestSession.receive_json blocks forever
    — wrap it in a thread to enforce a timeout.
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        future = ex.submit(ws.receive_json)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            raise TimeoutError("WS receive_json timed out")


def test_websocket_hello_on_connect(client):
    """Connecting should immediately receive a hello event."""
    with client.websocket_connect("/ws") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "system_hello"
        assert "client_id" in msg["data"]
        assert "event_types" in msg["data"]


def test_websocket_receives_published_event(client):
    """Published events should be received by connected clients."""
    bus = get_event_bus()

    with client.websocket_connect("/ws") as ws:
        # Receive hello first
        hello = ws.receive_json()
        assert hello["type"] == "system_hello"

        # Publish an event
        bus.publish(
            EventType.SESSION_START,
            {"session_id": "test-1", "project": "test-proj"},
        )

        # Receive it
        msg = ws.receive_json()
        assert msg["type"] == "session_start"
        assert msg["data"]["session_id"] == "test-1"


def test_websocket_receives_gauges_periodically(client):
    """Gauges should be sent periodically when no other events arrive."""
    with client.websocket_connect("/ws") as ws:
        # Hello
        hello = ws.receive_json()
        assert hello["type"] == "system_hello"

        # Wait up to 3s for a gauges event (interval = 2s)
        got_gauges = False
        try:
            msg = _receive_with_timeout(ws, timeout=3.0)
            if msg["type"] == "system_gauges":
                got_gauges = True
        except TimeoutError:
            pass

        assert got_gauges, "expected a system_gauges event within 3s"


def test_websocket_unsubscribes_on_disconnect(client):
    """Disconnecting should clean up subscribers."""
    bus = get_event_bus()

    with client.websocket_connect("/ws") as ws:
        ws.receive_json()  # hello

    # Re-connect — should work without issue (and unsubscribed cleanly)
    with client.websocket_connect("/ws") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "system_hello"

        # Publish — should be received
        bus.publish(EventType.SESSION_END, {"session_id": "x"})
        msg = ws.receive_json()
        assert msg["type"] == "session_end"


def test_websocket_multiple_clients_broadcast(client):
    """Two connected clients should both receive the same published event."""
    bus = get_event_bus()

    with client.websocket_connect("/ws") as ws1:
        ws1.receive_json()  # hello for ws1

        with client.websocket_connect("/ws") as ws2:
            ws2.receive_json()  # hello for ws2

            bus.publish(
                EventType.AGENT_TURN_START,
                {"session_id": "broadcast-test"},
            )

            msg1 = ws1.receive_json()
            msg2 = ws2.receive_json()

            assert msg1["type"] == "agent_turn_start"
            assert msg2["type"] == "agent_turn_start"
            assert msg1["data"]["session_id"] == "broadcast-test"
            assert msg2["data"]["session_id"] == "broadcast-test"


def test_websocket_stats_endpoint(client):
    """The /ws/stats REST endpoint returns subscription info."""
    r = client.get("/ws/stats")
    assert r.status_code == 200
    data = r.json()
    assert "event_types" in data
    assert "system_gauges" in data["event_types"]
    assert "agent_turn_start" in data["event_types"]
    assert "total_subscribers" in data
    assert data["gauges_interval_sec"] == 2.0


def test_websocket_handles_rapid_publish():
    """Publishing many events rapidly should not crash the server."""
    bus = get_event_bus()

    with TestClient(halo_app) as client:
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()  # hello

            # Publish many events rapidly — server should not crash
            for i in range(20):
                bus.publish(
                    EventType.MAC_OP_AUDIT,
                    {"i": i, "action": "test", "target": "/x"},
                )

            # Receive events with a timeout — should get at least 1
            received = 0
            for _ in range(20):
                try:
                    msg = _receive_with_timeout(ws, timeout=0.3)
                    if msg["type"] == "mac_op_audit":
                        received += 1
                except TimeoutError:
                    break

            # Server didn't crash (we got this far) — and at least one event arrived
            assert received >= 1, f"expected at least 1 mac_op_audit, got {received}"

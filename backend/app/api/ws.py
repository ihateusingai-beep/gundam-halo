"""WebSocket endpoint — real-time event stream to clients.

Each connected client gets:
- All events from the EventBus (SESSION_*, AGENT_*, MAC_*, SECURITY_*, CHANNEL_*, etc.)
- Periodic system gauges (every 2s)

Per-connection design:
- Each WS gets its own asyncio.Queue
- EventBus subscribers (sync) put events into the queue
- A background async task reads from the queue and sends to WS
- On disconnect, all subscribers are unsubscribed

The WebSocketDisconnect and RuntimeError exceptions are caught and handled
gracefully so server shutdown doesn't leak.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.events import Event, EventBus, EventType, get_event_bus

logger = logging.getLogger(__name__)
router = APIRouter()


# How often to send system gauges (seconds)
GAUGES_INTERVAL_SEC = 2.0


def _get_gauges_snapshot() -> dict[str, Any]:
    """Snapshot current Mac system gauges. Same logic as /api/system/gauges."""
    import psutil
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    net = psutil.net_io_counters()
    return {
        "cpu_percent": psutil.cpu_percent(interval=None),
        "memory_percent": mem.percent,
        "disk_percent": disk.percent,
        "network_sent_mb": net.bytes_sent / 1024 / 1024,
        "network_recv_mb": net.bytes_recv / 1024 / 1024,
    }


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """WebSocket endpoint — streams all events + periodic gauges."""
    await websocket.accept()
    client_id = id(websocket)
    logger.info(f"WS client {client_id} connected from {websocket.client}")

    bus = get_event_bus()
    queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
    # Capture the loop we're running on so the sync subscriber can schedule
    # thread-safe puts onto it.
    loop = asyncio.get_running_loop()
    last_gauges_at = 0.0
    subscribed = False

    def sync_handler(event: Event) -> None:
        """Sync handler — called by EventBus in publisher's thread.

        Uses call_soon_threadsafe to schedule a put on the WS's event loop
        so the queue's internal Future is woken up correctly across threads.
        """
        def _put() -> None:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning(f"WS {client_id}: queue full, dropping {event.event_type.value}")
        try:
            loop.call_soon_threadsafe(_put)
        except RuntimeError:
            # Loop is closed (server shutting down) — drop silently
            pass

    try:
        # Subscribe to ALL event types
        for event_type in EventType:
            bus.subscribe(event_type, sync_handler)
        subscribed = True
        logger.debug(f"WS {client_id} subscribed to {len(list(EventType))} event types")

        # Send a hello event with server info
        await websocket.send_json({
            "type": "system_hello",
            "ts": time.time(),
            "data": {
                "client_id": client_id,
                "event_types": [et.value for et in EventType],
                "gauges_interval_sec": GAUGES_INTERVAL_SEC,
            },
        })

        # Main loop: dispatch events and periodic gauges
        while True:
            try:
                # Wait for next event with timeout (for gauges interval)
                event = await asyncio.wait_for(queue.get(), timeout=GAUGES_INTERVAL_SEC)
                await websocket.send_json({
                    "type": event.event_type.value,
                    "ts": event.timestamp,
                    "data": event.data,
                })
            except asyncio.TimeoutError:
                # No event — check if we should send gauges
                now = time.time()
                if now - last_gauges_at >= GAUGES_INTERVAL_SEC:
                    try:
                        await websocket.send_json({
                            "type": "system_gauges",
                            "ts": now,
                            "data": _get_gauges_snapshot(),
                        })
                        last_gauges_at = now
                    except Exception as e:
                        logger.debug(f"WS {client_id}: gauges send failed: {e}")
                        break

    except WebSocketDisconnect:
        logger.info(f"WS {client_id} disconnected")
    except Exception as e:
        logger.warning(f"WS {client_id} error: {e}")
    finally:
        # Always unsubscribe to avoid memory leak
        if subscribed:
            for event_type in EventType:
                bus.unsubscribe(event_type, sync_handler)
            logger.debug(f"WS {client_id} unsubscribed from all events")


# ---------------------------------------------------------------------------
# Health: list of currently-connected WS clients (for debugging)
# ---------------------------------------------------------------------------

_active_ws_count = 0


@router.get("/ws/stats")
async def ws_stats() -> dict:
    """Stats about the WS endpoint (number of subscribers, etc.)."""
    bus = get_event_bus()
    # Count subscribers across all event types
    total_subs = 0
    for et in EventType:
        total_subs += len(bus._subscribers.get(et, []))
    return {
        "event_types": [et.value for et in EventType],
        "gauges_interval_sec": GAUGES_INTERVAL_SEC,
        "total_subscribers": total_subs,
    }

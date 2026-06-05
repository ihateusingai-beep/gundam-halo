"""Tests for the audit log."""
import json
import os
import time
from pathlib import Path

import pytest

from app.core.events import Event, EventType, get_event_bus
from app.security.audit import AuditLogger, get_audit_logger, reset_audit_logger


def test_audit_write_and_read(tmp_path):
    log_path = tmp_path / "audit.log"
    logger = AuditLogger(log_path)

    event = Event(
        event_type=EventType.MAC_OP_AUDIT,
        timestamp=time.time(),
        data={"action": "test", "target": "/tmp/x"},
    )
    logger.write(event)

    assert log_path.exists()
    records = logger.tail(10)
    assert len(records) == 1
    assert records[0]["event_type"] == "mac_op_audit"
    assert records[0]["data"]["action"] == "test"


def test_audit_rotation(tmp_path):
    log_path = tmp_path / "audit.log"
    # max_size_mb very small (1 byte) to force rotation
    logger = AuditLogger(log_path, max_size_mb=0)  # 0 = 0 bytes, so first write triggers rotation

    for i in range(5):
        event = Event(
            event_type=EventType.MAC_OP_AUDIT,
            timestamp=time.time(),
            data={"i": i, "padding": "x" * 100},
        )
        logger.write(event)

    # After rotation, multiple .1.log, .2.log, .3.log files should exist
    rotated = list(tmp_path.glob("audit*.log"))
    assert len(rotated) > 1

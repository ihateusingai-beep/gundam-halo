"""Tests for the bluetooth tool.

We mock both `system_profiler` (for listing) and `blueutil` (for
connect / disconnect) so the tests are platform-independent. The
tool's logic (MAC normalization, missing-binary detection, JSON
shape parsing) is what's under test.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from unittest.mock import patch

import pytest

from app.tools.bluetooth import BluetoothTool


# ---- list ----

_LIST_JSON = json.dumps(
    [
        {
            "device_connected": [
                {
                    "device_name": "AirPods Pro",
                    "device_address": "AA-BB-CC-DD-EE-FF",
                }
            ],
            "device_paired_unconnected": [
                {
                    "device_name": "MX Master 3",
                    "device_address": "11-22-33-44-55-66",
                }
            ],
        }
    ]
)


@pytest.mark.asyncio
async def test_list_returns_connected_and_paired():
    cp = subprocess.CompletedProcess(
        args=(), returncode=0, stdout=_LIST_JSON, stderr=""
    )
    with patch("subprocess.run", return_value=cp):
        result = await BluetoothTool().run(operation="list")
    assert "AirPods Pro" in result
    assert "CONNECTED" in result
    assert "MX Master 3" in result
    assert "PAIRED" in result


@pytest.mark.asyncio
async def test_list_empty():
    cp = subprocess.CompletedProcess(
        args=(), returncode=0, stdout="[]", stderr=""
    )
    with patch("subprocess.run", return_value=cp):
        result = await BluetoothTool().run(operation="list")
    assert "No Bluetooth devices" in result


@pytest.mark.asyncio
async def test_list_handles_garbled_json():
    cp = subprocess.CompletedProcess(
        args=(), returncode=0, stdout="not json", stderr=""
    )
    with patch("subprocess.run", return_value=cp):
        result = await BluetoothTool().run(operation="list")
    assert "Error" in result
    assert "parse" in result.lower()


@pytest.mark.asyncio
async def test_list_subprocess_failure():
    cp = subprocess.CompletedProcess(
        args=(), returncode=1, stdout="", stderr="bluetooth off"
    )
    with patch("subprocess.run", return_value=cp):
        result = await BluetoothTool().run(operation="list")
    assert "Error" in result
    assert "bluetooth off" in result


# ---- connect / disconnect ----


def _mock_which_available():
    return patch.object(
        shutil, "which", return_value="/opt/homebrew/bin/blueutil"
    )


def _mock_which_missing():
    return patch.object(shutil, "which", return_value=None)


@pytest.mark.asyncio
async def test_connect_normalizes_mac_address():
    """User might pass `aa:bb:cc:dd:ee:ff` or `aabbccddeeff`; we
    normalize to `aa-bb-cc-dd-ee-ff` for blueutil."""
    captured: dict = {}
    real_run = subprocess.run

    def fake_run(args, **kwargs):
        captured["args"] = args
        return real_run(
            ["true"], capture_output=True, text=True, timeout=1, check=False
        )

    with _mock_which_available(), patch(
        "subprocess.run", side_effect=fake_run
    ):
        result = await BluetoothTool().run(
            operation="connect", mac_address="AA:BB:CC:DD:EE:FF"
        )
    # The arg passed to blueutil must be the dashed form
    arg_strs = [str(a) for a in captured["args"]]
    assert any("aa-bb-cc-dd-ee-ff" in s for s in arg_strs), arg_strs


@pytest.mark.asyncio
async def test_disconnect_missing_blueutil_returns_helpful_error():
    with _mock_which_missing():
        result = await BluetoothTool().run(
            operation="disconnect", mac_address="aa-bb-cc-dd-ee-ff"
        )
    assert "Error" in result
    assert "brew install blueutil" in result


@pytest.mark.asyncio
async def test_connect_requires_mac_address():
    """Even with blueutil available, missing MAC is an error."""
    with _mock_which_available():
        result = await BluetoothTool().run(operation="connect")
    assert "Error" in result
    assert "mac_address" in result


@pytest.mark.asyncio
async def test_rejects_invalid_mac_address():
    with _mock_which_available():
        result = await BluetoothTool().run(
            operation="connect", mac_address="not-a-mac"
        )
    assert "Error" in result
    assert "invalid" in result.lower() or "MAC" in result


@pytest.mark.asyncio
async def test_unknown_op():
    result = await BluetoothTool().run(operation="nope")
    assert "Error" in result
    assert "nope" in result

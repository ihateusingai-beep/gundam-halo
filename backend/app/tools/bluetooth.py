"""bluetooth tool — list / inspect / connect / disconnect Bluetooth devices.

Strategy:
  - For listing: `system_profiler SPBluetoothDataType` (built-in,
    no install). Returns paired devices with their MAC addresses.
  - For connecting: requires the `blueutil` CLI
    (https://github.com/toy/blueutil). It is NOT shipped with macOS —
    the user has to `brew install blueutil` first. We detect this and
    return a clear "install with Homebrew" message when it's missing.
  - We also support the "disconnect" op via blueutil.

Why not AppleScript: System Events has no first-class Bluetooth
control surface. The official approach is `blueutil` or
`defaults write com.apple.Bluetooth <key>`, neither of which is reliable
for runtime device control.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
from typing import Any, Dict

from app.tools._stubs import BaseTool
from app.core.registry import register_tool

logger = logging.getLogger(__name__)

BLUEUTIL = "blueutil"  # CLI binary; not on PATH by default


def _blueutil_available() -> bool:
    return shutil.which(BLUEUTIL) is not None


def _list_paired() -> str:
    """List paired Bluetooth devices via system_profiler."""
    try:
        r = subprocess.run(
            ["system_profiler", "-json", "SPBluetoothDataType"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except FileNotFoundError:
        return "Error: `system_profiler` not found (macOS only)"
    except subprocess.TimeoutExpired:
        return "Error: system_profiler timed out"
    except Exception as e:
        return f"Error: {e}"
    if r.returncode != 0:
        return f"Error: system_profiler failed (exit {r.returncode}): {r.stderr.strip()}"

    # The JSON shape is verbose; we pluck out the paired-devices list.
    # system_profiler JSON is a list of dicts, one per "Bluetooth"
    # controller entry. Each has a "device_title" + "device_address" +
    # (optionally) "device_isconnected" + "device_ispaired".
    import json

    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError as e:
        return f"Error: could not parse system_profiler JSON: {e}"

    lines: list[str] = []
    seen: set[str] = set()
    for entry in data:
        # Each "Bluetooth" controller has its own list
        for dev in entry.get("device_connected", []) or []:
            name = dev.get("device_name", "?")
            addr = dev.get("device_address", "?")
            key = f"{name}::{addr}"
            if key in seen:
                continue
            seen.add(key)
            lines.append(
                f"CONNECTED: {name} — {addr}"
            )
        for dev in entry.get("device_paired_unconnected", []) or []:
            name = dev.get("device_name", "?")
            addr = dev.get("device_address", "?")
            key = f"{name}::{addr}"
            if key in seen:
                continue
            seen.add(key)
            lines.append(
                f"PAIRED (not connected): {name} — {addr}"
            )
    if not lines:
        return "No Bluetooth devices found (or Bluetooth is off)"
    return f"Found {len(lines)} Bluetooth device(s):\n" + "\n".join(lines)


def _blueutil_run(args: list[str], timeout: int = 10) -> str:
    if not _blueutil_available():
        return (
            f"Error: {BLUEUTIL!r} CLI not installed. "
            "Install with: brew install blueutil"
        )
    try:
        r = subprocess.run(
            [BLUEUTIL, *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return f"Error: {BLUEUTIL} timed out"
    except Exception as e:
        return f"Error: {e}"
    if r.returncode != 0:
        return (
            f"Error: {BLUEUTIL} {args!r} failed (exit {r.returncode}): "
            f"{r.stderr.strip()}"
        )
    return r.stdout.strip() or "OK"


@register_tool("bluetooth")
class BluetoothTool(BaseTool):
    name = "bluetooth"
    description = (
        "List, connect, or disconnect Bluetooth devices. Operations: "
        "'list' returns paired devices and which are currently "
        "connected (uses `system_profiler`, no install needed); "
        "'connect' / 'disconnect' take a MAC address and toggle the "
        "connection (requires the `blueutil` CLI; install with "
        "'brew install blueutil' if missing). If the tool can't find "
        "blueutil, it returns a clear install hint rather than failing "
        "silently. Use sparingly — toggling BT at runtime is reversible "
        "but can disrupt the user's other audio devices."
    )
    parameters: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["list", "connect", "disconnect"],
                "description": "Which bluetooth op to run.",
            },
            "mac_address": {
                "type": "string",
                "description": (
                    "MAC address of the device, e.g. 'aa-bb-cc-dd-ee-ff' or "
                    "'aabbccddeeff'. Required for connect / disconnect."
                ),
            },
        },
        "required": ["operation"],
    }

    async def run(
        self,
        operation: str,
        mac_address: str = "",
        **kwargs: Any,
    ) -> str:
        if operation == "list":
            return _list_paired()
        if operation in ("connect", "disconnect"):
            if not mac_address:
                return f"Error: 'mac_address' is required for operation={operation!r}"
            verb = "connect" if operation == "connect" else "disconnect"
            # Normalize: blueutil accepts aa-bb-cc-dd-ee-ff or aabbccddeeff
            mac = mac_address.replace("-", "").replace(":", "").lower()
            if len(mac) != 12 or any(c not in "0123456789abcdef" for c in mac):
                return f"Error: invalid MAC address {mac_address!r}"
            pretty = "-".join(mac[i : i + 2] for i in range(0, 12, 2))
            return _blueutil_run([verb, pretty])
        return f"Error: unknown operation {operation!r}"


__all__ = ["BluetoothTool"]

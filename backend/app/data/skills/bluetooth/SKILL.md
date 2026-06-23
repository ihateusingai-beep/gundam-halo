---
name: bluetooth
description: Toggle Bluetooth on/off, list paired devices, or connect/disconnect a paired device by name.
user-invocable: true
---

# bluetooth

Control the Mac's Bluetooth radio via
`blueutil` (https://github.com/nriley/blueutil, bundled with
Homebrew). Supports: power on/off, list paired devices,
connect by name, disconnect by name.

## Operating Loop

1. **List first, act second.** When the user says
   "connect to my AirPods", call `list()` first to confirm
   the device name; partial-name matches return "not found".
2. **Connection takes ~3-5 seconds.** Don't poll the
   connect result; tell the user to check the menu-bar
   Bluetooth icon.

## Examples

```
bluetooth(action="status")                    → on/off
bluetooth(action="list")                      → [{name, address, connected}]
bluetooth(action="connect", device="Ken's AirPods Pro")
bluetooth(action="disconnect", device="Ken's AirPods Pro")
bluetooth(action="power", state="off")
```

## Red Lines

- Don't loop `connect` calls. Each one initiates a pairing
  handshake; doing it 10 times in 30s will lock the
  Bluetooth radio. Wait 10 seconds between attempts.

## Recovery

- "device not found" → call `list()` to see the exact
  device name (case-sensitive). Don't guess.
- "blueutil not installed" → `brew install blueutil`.
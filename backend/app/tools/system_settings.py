"""system_settings tool — toggle macOS DND / Focus modes + read prefs.

The macOS DND (Do Not Disturb) feature has been rebranded as
"Focus" in macOS 12+, but the underlying mechanism is the same:
the Night Shift / Do Not Disturb system pref. We use `defaults`
to flip the bit, which works on 11+ without a TCC prompt.

Ops:
  - `dnd` op with `enabled: bool` → toggle DND on/off
  - `dnd_status` op → read current DND state
  - `get` op with `key: str` → read a system pref by name
    (e.g. "AppleInterfaceStyle" for dark mode)

Notes:
  - `defaults write com.apple.controlcenter "NSStatusItem Visible FocusModes"`
    is the magic bit for newer macOS — it makes the Focus menu
    bar item appear, which is the most reliable way to verify
    the change took effect.
  - For `get`, we read from `~/Library/Preferences/.GlobalPreferences.plist`
    using `defaults read <domain> <key>`. Falls back to the explicit
    domain the user passed.
  - No TCC prompt (defaults is a user-mode tool).
"""
from __future__ import annotations

import logging
import subprocess
from typing import Any, Dict, Optional

from app.tools._stubs import BaseTool
from app.core.registry import register_tool

logger = logging.getLogger(__name__)


def _run_defaults(args: list[str], timeout: int = 5) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["defaults", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _set_dnd(enabled: bool) -> str:
    # The Focus / DND state is stored in
    # ~/Library/Preferences/.GlobalPreferences.plist under
    # com.apple.controlcenter "NSStatusItem Visible FocusModes".
    # For older macOS it's "doNotDisturb" in user-mode defaults.
    # We set both keys for compatibility (newer macOS ignores the
    # old one, older ignores the new).
    domain = "com.apple.controlcenter"
    if enabled:
        write_arg = "1"
    else:
        write_arg = "0"
    for key in ("NSStatusItem Visible FocusModes", "doNotDisturb"):
        r = _run_defaults(["write", domain, key, "-bool", write_arg])
        if r.returncode != 0:
            return (
                f"Error: defaults write {domain} {key!r} failed (exit {r.returncode}): "
                f"{r.stderr.strip()}"
            )
    # Force the cfprefsd daemon to re-read so the change is immediate.
    _run_defaults(["read-type", domain, "NSStatusItem Visible FocusModes"])
    return f"OK: Do Not Disturb {'enabled' if enabled else 'disabled'}"


def _get_dnd_status() -> str:
    r = _run_defaults(
        ["read", "com.apple.controlcenter", "NSStatusItem Visible FocusModes"]
    )
    # `defaults read` returns "1" / "0" / "0\n" for bool, or an error
    # if the key doesn't exist (older macOS).
    val = r.stdout.strip()
    if r.returncode == 0 and val in ("0", "1"):
        return "Do Not Disturb: " + ("enabled" if val == "1" else "disabled")
    # Fall back to the older key
    r2 = _run_defaults(["read", "com.apple.controlcenter", "doNotDisturb"])
    if r2.returncode == 0:
        return "Do Not Disturb: " + (
            "enabled" if r2.stdout.strip() == "1" else "disabled"
        )
    return f"Do Not Disturb: unknown (defaults read returned: {val!r})"


@register_tool("system_settings")
class SystemSettingsTool(BaseTool):
    name = "system_settings"
    description = (
        "Get or set macOS system preferences. Operations: 'dnd' toggles "
        "Do Not Disturb / Focus mode on or off (takes 'enabled' bool); "
        "'dnd_status' returns the current DND state; 'get' reads a system "
        "preference by domain + key (e.g. domain='NSGlobalDomain', "
        "key='AppleInterfaceStyle' for dark/light mode). No TCC prompt — "
        "this uses `defaults`, a built-in macOS tool. Audit-loggable "
        "because DND changes affect which notifications the user sees."
    )
    parameters: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["dnd", "dnd_status", "get"],
                "description": "Which system_settings op to run.",
            },
            "enabled": {
                "type": "boolean",
                "description": "True to enable DND, False to disable (operation='dnd').",
            },
            "domain": {
                "type": "string",
                "description": (
                    "Defaults domain (operation='get'). Examples: "
                    "'NSGlobalDomain', 'com.apple.dock', "
                    "'com.apple.finder'."
                ),
            },
            "key": {
                "type": "string",
                "description": "Defaults key within the domain (operation='get').",
            },
        },
        "required": ["operation"],
    }

    async def run(
        self,
        operation: str,
        enabled: Optional[bool] = None,
        domain: Optional[str] = None,
        key: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        if operation == "dnd":
            if enabled is None:
                return "Error: 'enabled' (bool) is required for operation='dnd'"
            return _set_dnd(bool(enabled))
        if operation == "dnd_status":
            return _get_dnd_status()
        if operation == "get":
            if not domain or not key:
                return "Error: both 'domain' and 'key' are required for operation='get'"
            r = _run_defaults(["read", domain, key])
            if r.returncode != 0:
                return (
                    f"Error: defaults read {domain} {key!r} failed "
                    f"(exit {r.returncode}): {r.stderr.strip()}"
                )
            return f"{domain}.{key} = {r.stdout.strip()}"
        return f"Error: unknown operation {operation!r}"


__all__ = ["SystemSettingsTool"]

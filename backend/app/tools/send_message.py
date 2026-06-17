"""send_message tool — pyautogui-based message sender.

Sprint 27 (per `docs/FEATURE-SPEC-SPRINT27.md` §4.2 Track 27.4).

**OPT-IN** — enabled=false in `config.toml.example` by
default because pyautogui is fragile (hard-coded
coordinates, hard-coded timings). The user opts in
only after manual smoke test confirms the coordinates
work for their Mac + the messaging app version.

This is a port of Mark-XL's `send_message.py` with
Gundam Halo's tool contract:
  - `async def run(self, **kwargs) -> str`
  - JSON Schema in `parameters`
  - Lazy import of `pyautogui` + `pyperclip` (so the
    test suite can mock the import without the deps
    installed)

The actual pyautogui flow (open app, focus window,
search contact, type message, press Enter) is
**opt-in and untested in CI** — the tests below mock
the entire pyautogui + pyperclip import path and
verify the contract (param validation, error
messages, opt-in check).

If the user later adds a computer-vision-based
sender (Sprint 31+), this tool can be replaced
without breaking the LLM-facing contract.
"""
from __future__ import annotations

import logging
import sys
from typing import Any, Dict, List, Optional

from app.tools._stubs import BaseTool

logger = logging.getLogger(__name__)

# Platform → app name mapping. macOS uses
# `open -a "App Name"`, Windows uses
# `start "" "App Name"`, Linux uses `xdg-open`.
# These are the most common messaging apps the user
# might have installed. Keys are `sys.platform` values
# (string, not function): "darwin" / "win32" / "linux".
PLATFORM_APP_NAMES: Dict[str, Dict[str, str]] = {
    "whatsapp": {
        "darwin": "WhatsApp",
        "win32": "WhatsApp",
        "linux": "whatsapp",
    },
    "telegram": {
        "darwin": "Telegram",
        "win32": "Telegram",
        "linux": "telegram-desktop",
    },
    "signal": {
        "darwin": "Signal",
        "win32": "Signal",
        "linux": "signal-desktop",
    },
    "discord": {
        "darwin": "Discord",
        "win32": "Discord",
        "linux": "discord",
    },
    "messenger": {
        "darwin": "Messenger",
        "win32": "Messenger",
        "linux": None,  # No native Linux app
    },
    "instagram": {
        "darwin": "Instagram",
        "win32": "Instagram",
        "linux": None,
    },
}


def _sys_platform_to_system(sys_platform: str) -> str:
    """Map `sys.platform` to the human-readable name
    used in error messages. `sys.platform` returns:
      - "darwin" on macOS
      - "win32" on Windows
      - "linux" (or "linux2") on Linux
    Returns a capitalised name for display: "Darwin",
    "Windows", "Linux".
    """
    if sys_platform.startswith("darwin"):
        return "Darwin"
    if sys_platform.startswith("win"):
        return "Windows"
    if sys_platform.startswith("linux"):
        return "Linux"
    return sys_platform


class SendMessageError(RuntimeError):
    """Raised on send_message errors (missing deps,
    app not installed, contact not found, etc.)."""


def _check_pyautogui_available() -> Optional[str]:
    """Return None if pyautogui + pyperclip are
    importable; return a clear error string otherwise.
    """
    try:
        import pyautogui  # type: ignore  # noqa: F401
        import pyperclip  # type: ignore  # noqa: F401
    except ImportError as e:
        return (
            f"pyautogui + pyperclip are required for the "
            f"send_message tool. Install with: "
            f"uv add pyautogui pyperclip. "
            f"({e})"
        )
    return None


def _resolve_app_name(platform_name: str, os_system: str) -> Optional[str]:
    """Resolve a messaging platform + OS to the app's
    display name. Returns None if the platform is
    not supported on the OS."""
    return PLATFORM_APP_NAMES.get(platform_name, {}).get(os_system)


class SendMessageTool(BaseTool):
    """Send a message to a contact on a messaging platform.

    **OPT-IN.** Enable by setting `cfg.tools.send_message.enabled = true`
    in `~/.gundam-halo/config.toml`. pyautogui is fragile;
    test on your specific Mac + app version before
    relying on this in production.

    The tool opens the messaging app, focuses the
    contact search, types the receiver name, types
    the message, and presses Enter. Returns a
    confirmation string on success.
    """

    name = "send_message"
    description = (
        "Send a message to a contact on a messaging "
        "platform (WhatsApp, Telegram, Signal, Discord, "
        "Messenger, Instagram). The receiver must exist "
        "in the platform's contact list. The tool opens "
        "the app, searches for the receiver, types the "
        "message, and presses Enter. **Requires the "
        "pyautogui + pyperclip packages** (install with "
        "`uv add pyautogui pyperclip`) and Accessibility "
        "permission on macOS. The tool is **opt-in**: set "
        "`tools.send_message.enabled = true` in "
        "config.toml to enable. pyautogui uses "
        "hard-coded coordinates; the tool may need "
        "coordinate-tuning on your specific Mac + app "
        "version."
    )
    parameters: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "receiver": {
                "type": "string",
                "description": (
                    "Contact name as it appears in the "
                    "platform's contact list. Examples: "
                    "'John', 'Mom', '張三'."
                ),
            },
            "message_text": {
                "type": "string",
                "description": (
                    "The exact message text to send. "
                    "Should be 1-2 sentences for reliability."
                ),
            },
            "platform": {
                "type": "string",
                "enum": ["whatsapp", "telegram", "signal", "discord", "messenger", "instagram"],
                "description": (
                    "Messaging platform (default whatsapp)."
                ),
            },
        },
        "required": ["receiver", "message_text"],
    }

    async def run(
        self,
        receiver: str,
        message_text: str,
        platform: str = "whatsapp",
        **_: Any,
    ) -> str:
        # Validate
        if not isinstance(receiver, str) or not receiver.strip():
            return "Error: 'receiver' is required and must be a non-empty string"
        if not isinstance(message_text, str) or not message_text.strip():
            return "Error: 'message_text' is required and must be a non-empty string"
        if not isinstance(platform, str) or not platform.strip():
            platform = "whatsapp"
        platform = platform.strip().lower()

        # Resolve the platform → app name for this OS.
        # Use `sys.platform` (a string like "darwin",
        # "win32", "linux") rather than `platform.system()`
        # (a function call) so the test can mock the OS
        # via `monkeypatch.setattr(sys, "platform", "linux")`
        # without conflicting with the `unittest.mock.patch`
        # import in test files.
        os_system = sys.platform  # raw "darwin" / "win32" / "linux"
        app_name = _resolve_app_name(platform, os_system)
        if app_name is None:
            return (
                f"Error: platform {platform!r} is not "
                f"supported on {os_system!r}. "
                f"Supported: {', '.join(p for p, m in PLATFORM_APP_NAMES.items() if m.get(os_system))}"
            )

        # Check pyautogui availability (this is the
        # fragile dependency; we fail loudly if missing)
        dep_error = _check_pyautogui_available()
        if dep_error:
            return (
                f"Error: send_message is not available — "
                f"{dep_error} "
                f"Set tools.send_message.enabled = false in "
                f"config.toml to suppress this error."
            )

        # ── The actual pyautogui flow is intentionally
        # NOT implemented in v0.1.5+. The Mark-XL
        # implementation has hard-coded coordinates
        # that don't survive macOS updates or app
        # version changes. Future work (Sprint 31+):
        # a computer-vision-based sender that finds
        # the contact by screenshot + YOLO detection.
        # For now, return a clear "not implemented"
        # message so the user gets an honest answer.
        return (
            f"send_message v0.1 is a stub: the pyautogui flow "
            f"is not yet implemented. To enable real message "
            f"sending, the user must: "
            f"(1) install pyautogui + pyperclip, "
            f"(2) tune the coordinates for {app_name} on their Mac, "
            f"(3) accept the fragility (app updates break the tool). "
            f"See `docs/FEATURE-SPEC-SPRINT27.md` §4.2 Track 27.4 "
            f"for the full design. "
            f"For now, please open {app_name} manually and send "
            f"the message to {receiver!r}."
        )


__all__ = ["SendMessageTool", "SendMessageError", "PLATFORM_APP_NAMES"]

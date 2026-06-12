"""Clipboard tool — read/write the system clipboard via pbcopy/pbpaste.

Wraps the macOS `pbcopy` (write) and `pbpaste` (read) CLI tools.
Suitable for:
- Reading what the user just copied
- Dropping a generated result into the clipboard so the user can
  paste it elsewhere

Audit-loggable. No path policy (clipboard is a single global slot,
not a filesystem location).
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from app.tools._stubs import BaseTool
from app.mac.clipboard import read_clipboard, write_clipboard

logger = logging.getLogger(__name__)


class ClipboardTool(BaseTool):
    name = "clipboard"
    description = (
        "Read or write the macOS system clipboard. Operations: 'read' returns "
        "the current clipboard text (empty string if non-text); 'write' takes "
        "a 'text' field and overwrites the clipboard. Use sparingly — every "
        "call is audit-logged because the clipboard may contain sensitive data."
    )
    parameters: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["read", "write"],
                "description": "Whether to read from or write to the clipboard.",
            },
            "text": {
                "type": "string",
                "description": "Text to write (required when operation='write').",
            },
        },
        "required": ["operation"],
    }

    async def run(
        self, operation: str, text: str = "", **kwargs: Any
    ) -> str:
        if operation == "read":
            try:
                return read_clipboard()
            except RuntimeError as e:
                return f"Error: {e}"
        if operation == "write":
            if not text:
                return "Error: 'text' is required for write operation"
            try:
                written = write_clipboard(text)
                return f"OK: wrote {written} bytes to clipboard"
            except ValueError as e:
                return f"Error: {e}"
            except RuntimeError as e:
                return f"Error: {e}"
        return f"Error: unknown operation {operation!r}"


__all__ = ["ClipboardTool"]

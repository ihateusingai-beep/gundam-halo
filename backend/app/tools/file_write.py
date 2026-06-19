"""file_write tool — write a file, policy-gated.

REQUIRES user confirmation in real use. The API layer will block writes
without an explicit confirmation token.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from app.mac.file_ops import write_file
from app.mac.policy import check_path_write
from app.tools._stubs import BaseTool
from app.core.registry import register_tool

logger = logging.getLogger(__name__)


@register_tool("file_write")
class FileWriteTool(BaseTool):
    name = "file_write"
    description = (
        "Write text content to a file. Creates parent directories as needed. "
        "REQUIRES USER CONFIRMATION before use — the user will be asked to approve. "
        "Path must be under a policy-allowed directory (e.g. ~/workspace). "
        "Use this for creating new files or modifying existing ones. "
        "Prefer appending/diffing over wholesale rewrites for existing files."
    )
    parameters: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Absolute or ~-prefixed path to write to.",
            },
            "content": {
                "type": "string",
                "description": "The full text content to write to the file.",
            },
        },
        "required": ["path", "content"],
    }

    async def run(self, path: str, content: str, **kwargs: Any) -> str:
        if not check_path_write(path):
            return f"Error: path not allowed by write policy: {path}"
        try:
            n = write_file(path, content)
            return f"OK: wrote {n} bytes to {path}"
        except Exception as e:
            logger.error(f"file_write error: {e}")
            return f"Error writing file: {e}"


__all__ = ["FileWriteTool"]

"""file_read tool — read a file from disk, policy-gated."""

from __future__ import annotations

import logging
from typing import Any, Dict

from app.mac.file_ops import read_file
from app.mac.policy import check_path_read
from app.tools._stubs import BaseTool

logger = logging.getLogger(__name__)


class FileReadTool(BaseTool):
    name = "file_read"
    description = (
        "Read the contents of a text file. Use this when you need to inspect a file's contents. "
        "The path must be under a policy-allowed directory (e.g. ~/workspace, ~/Documents). "
        "For binary files, use a different tool (not yet implemented)."
    )
    parameters: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Absolute or ~-prefixed path to the file to read.",
            },
        },
        "required": ["path"],
    }

    async def run(self, path: str, **kwargs: Any) -> str:
        if not check_path_read(path):
            return f"Error: path not allowed by policy: {path}"
        try:
            content = read_file(path)
        except FileNotFoundError:
            return f"Error: file not found: {path}"
        except Exception as e:
            logger.error(f"file_read error: {e}")
            return f"Error reading file: {e}"

        # Truncate very long files to avoid blowing up the LLM context
        MAX = 50_000
        if len(content) > MAX:
            return f"{content[:MAX]}\n\n[... truncated, {len(content) - MAX} more chars ...]"
        return content


__all__ = ["FileReadTool"]

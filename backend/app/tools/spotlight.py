"""Spotlight tool — search the macOS Spotlight index via `mdfind`.

Spotlight is the system-wide file index. `mdfind` accepts a query
in the same DSL Finder's search box uses (kMDItem predicates,
natural-language terms, etc.) and returns matching file paths.

Read-only by design.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from app.tools._stubs import BaseTool
from app.mac.spotlight import spotlight_search

logger = logging.getLogger(__name__)


class SpotlightTool(BaseTool):
    name = "spotlight"
    description = (
        "Search the macOS Spotlight index and return matching file paths. "
        "Use the same query syntax as Finder's search box: literal terms "
        "(e.g. 'meeting notes'), kMDItem predicates (e.g. 'kind:pdf', "
        "'kMDItemFSName == \"*.py\"'), or combinations. Optional `only_in` "
        "limits the search to a directory (Spotlight must have indexed it). "
        "Returns up to `max_results` paths (capped at 500)."
    )
    parameters: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "Spotlight query. Examples: 'kind:pdf', "
                    "'kMDItemFSName == \"*.py\"', 'meeting notes yesterday'."
                ),
            },
            "only_in": {
                "type": "string",
                "description": "Optional directory to limit the search to.",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum results to return. Default 50, max 500.",
            },
        },
        "required": ["query"],
    }

    async def run(
        self,
        query: str,
        only_in: str = "",
        max_results: int = 50,
        **kwargs: Any,
    ) -> str:
        try:
            result = spotlight_search(
                query=query,
                max_results=max_results,
                only_in=only_in or None,  # type: ignore[arg-type]
            )
        except ValueError as e:
            return f"Error: {e}"
        except RuntimeError as e:
            return f"Error: {e}"

        if result["exit_code"] != 0 and result["stderr"]:
            return (
                f"Error: mdfind failed (exit {result['exit_code']}): "
                f"{result['stderr']}"
            )

        results = result["results"]
        if not results:
            return f"No results for query: {query!r}"
        # Format as a numbered list for the agent to consume
        lines = [f"{i+1}. {p}" for i, p in enumerate(results)]
        return (
            f"Found {result['count']} result(s) for {query!r} "
            f"(max {result['max_results']}):\n"
            + "\n".join(lines)
        )


__all__ = ["SpotlightTool"]

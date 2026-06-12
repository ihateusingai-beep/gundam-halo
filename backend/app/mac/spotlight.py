"""Spotlight search via `mdfind`.

`mdfind` is the macOS Spotlight command-line interface. It accepts a
Spotlight query string (the same DSL Finder's search box uses) and
returns matching file paths, one per line. Examples:

  mdfind "kind:pdf"                    # all PDFs in indexed locations
  mdfind "kMDItemFSName == '*.py'"     # Python files
  mdfind "Meeting Notes"                # natural-language query

Why mdfind over `find`:
- Indexed → fast on large disks (no FS walk)
- Rich metadata: kind, author, dates, content, EXIF, etc.
- Same syntax the user uses in Finder

Policy:
- Read-only by design (mdfind doesn't take a write flag).
- We cap the result count to prevent runaway returns.
- We don't gate by `file_read_paths` because Spotlight's index
  covers locations the user has explicitly granted Spotlight access
  to — typically ~/Documents, ~/Downloads, etc. We're not touching
  files; we're querying the index.
"""
from __future__ import annotations

import logging
import shlex
import subprocess
from typing import Dict, List

logger = logging.getLogger(__name__)

DEFAULT_MAX_RESULTS = 50
ABSOLUTE_MAX_RESULTS = 500


def spotlight_search(
    query: str,
    max_results: int = DEFAULT_MAX_RESULTS,
    only_in: str = None,  # type: ignore[assignment]
    timeout: int = 15,
) -> Dict[str, object]:
    """Run a Spotlight query.

    Args:
        query: Spotlight query string. The same DSL Finder uses.
        max_results: cap on returned lines. Hard ceiling at
            ABSOLUTE_MAX_RESULTS to keep responses sane.
        only_in: optional path to limit the search to (passed as
            the `-onlyin` arg to mdfind).
        timeout: subprocess timeout in seconds.

    Returns:
        {
            "query": str,
            "max_results": int,
            "count": int,
            "results": List[str],  # file paths, one per match
            "exit_code": int,
            "stderr": str,
        }
    """
    if not query or not query.strip():
        raise ValueError("Spotlight query is empty")

    # Clamp max_results
    max_results = max(1, min(int(max_results), ABSOLUTE_MAX_RESULTS))

    # macOS mdfind doesn't support a -maxresults flag (as of macOS 15+).
    # We post-truncate the result list in Python.
    if only_in:
        cmd = ["mdfind", "-onlyin", only_in, query]
    else:
        cmd = ["mdfind", query]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        # Strip empty lines, then truncate to max_results
        all_lines: List[str] = [
            line.strip() for line in result.stdout.splitlines() if line.strip()
        ]
        results = all_lines[:max_results]
        return {
            "query": query,
            "max_results": max_results,
            "count": len(results),
            "results": results,
            "exit_code": result.returncode,
            "stderr": result.stderr.strip(),
        }
    except subprocess.TimeoutExpired as e:
        return {
            "query": query,
            "max_results": max_results,
            "count": 0,
            "results": [],
            "exit_code": -1,
            "stderr": f"Timeout after {timeout}s",
        }
    except FileNotFoundError:
        raise RuntimeError("`mdfind` not found in PATH. This tool requires macOS.")


__all__ = ["spotlight_search"]

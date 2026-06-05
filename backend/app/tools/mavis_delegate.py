"""mavis_delegate tool — hand off coding sub-tasks to Mavis.

Used when the agent needs to do something beyond simple shell execution:
- Semantic commit messages
- Multi-file refactors
- Branching
- Complex conflict resolution
- Anything that benefits from LLM-assisted coding judgment
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict

from app.bridge.mavis import MavisBridge
from app.tools._stubs import BaseTool

logger = logging.getLogger(__name__)


class MavisDelegateTool(BaseTool):
    name = "mavis_delegate"
    description = (
        "Delegate a coding sub-task to Mavis (Mavis) — the project's "
        "Mavis sub-agent. Mavis will read the relevant files, make "
        "changes, commit them with a semantic commit message, and "
        "(optionally) push. "
        "Use this when: a task is too complex for shell_exec, requires "
        "a meaningful commit message, involves multiple file changes, "
        "or needs branching. "
        "Returns: success, summary, commit SHA, list of files changed, "
        "and whether the change was pushed. "
        "In DRY-RUN mode (no Mavis CLI available), returns a marker "
        "result without actually doing anything."
    )
    parameters: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "What Mavis should do (e.g. 'fix the auth bug in src/auth.py — the issue is that tokens expire too aggressively').",
            },
            "project_dir": {
                "type": "string",
                "description": "Absolute path to the git repo where Mavis should work.",
            },
            "context": {
                "type": "object",
                "description": "Optional context: file paths, line numbers, related PRs, etc.",
            },
        },
        "required": ["task", "project_dir"],
    }

    def __init__(self, bridge: MavisBridge | None = None) -> None:
        # Bridge is shared singleton
        self._bridge = bridge or MavisBridge(mode="dry_run")

    async def run(
        self,
        task: str,
        project_dir: str,
        context: Dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> str:
        try:
            result = await self._bridge.delegate(
                task=task,
                project_dir=project_dir,
                context=context or {},
            )
        except Exception as e:
            logger.error(f"mavis_delegate error: {e}")
            return f"Error: {e}"

        if not result.success:
            return f"Error: {result.error or 'unknown failure'}"

        parts = [f"OK: {result.summary}"]
        if result.commit_sha:
            parts.append(f"Commit: {result.commit_sha}")
        if result.branch:
            parts.append(f"Branch: {result.branch}")
        if result.files_changed:
            parts.append(f"Files changed: {', '.join(result.files_changed)}")
        if result.pushed:
            parts.append("Pushed: yes")
        return "\n".join(parts)


__all__ = ["MavisDelegateTool"]

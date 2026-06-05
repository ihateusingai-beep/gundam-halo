"""Mavis bridge — delegate coding tasks to Mavis (Mavis) sub-agent.

Two modes:
- **real**: spawns a Mavis session via subprocess, sends task + context,
  waits for response
- **dry-run**: returns a fake result with marker (for development / tests)

The bridge is invoked by:
- The agent (via the `mavis_delegate` tool) when a coding task needs
  semantic commit messages, branching, or anything beyond simple
  shell execution
- Manually via the API for ad-hoc coding tasks
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class MavisResult:
    """Result of a Mavis delegation."""

    success: bool
    summary: str
    commit_sha: str = ""
    branch: str = ""
    files_changed: list[str] = None  # type: ignore[assignment]
    pushed: bool = False
    error: Optional[str] = None
    raw_output: str = ""  # full Mavis output for debugging

    def __post_init__(self) -> None:
        if self.files_changed is None:
            self.files_changed = []


class MavisBridge:
    """Bridge to Mavis (Mavis) for coding sub-tasks.

    In `dry_run` mode, no subprocess is spawned — we return a fake result.
    In `real` mode, we invoke `mavis communication send` with the task.
    """

    def __init__(
        self,
        mode: str = "dry_run",
        *,
        timeout_sec: int = 300,
        mavis_cli: str = "mavis",
    ) -> None:
        if mode not in ("real", "dry_run"):
            raise ValueError(f"Invalid mode: {mode!r}. Use 'real' or 'dry_run'.")
        self.mode = mode
        self.timeout_sec = timeout_sec
        self.mavis_cli = mavis_cli

    async def delegate(
        self,
        task: str,
        *,
        project_dir: str | Path,
        context: Optional[dict] = None,
    ) -> MavisResult:
        """Delegate a coding task to Mavis.

        Args:
            task: What to do (e.g. "fix the auth bug in src/auth.py")
            project_dir: Working directory for Mavis (the git repo)
            context: Optional context dict (commit message hints, related files, etc.)

        Returns:
            MavisResult with success, summary, commit_sha, etc.
        """
        project_dir = Path(project_dir)
        if not project_dir.exists():
            return MavisResult(
                success=False,
                summary="",
                error=f"project_dir does not exist: {project_dir}",
            )

        if self.mode == "dry_run":
            return self._dry_run_delegate(task, project_dir, context or {})

        return await self._real_delegate(task, project_dir, context or {})

    # ------------------------------------------------------------------
    # Dry-run mode
    # ------------------------------------------------------------------

    def _dry_run_delegate(
        self, task: str, project_dir: Path, context: dict
    ) -> MavisResult:
        """Return a fake result without spawning Mavis."""
        logger.info(
            f"[Mavis DRY-RUN] Would delegate to Mavis:\n"
            f"  project: {project_dir}\n"
            f"  task: {task[:200]}\n"
            f"  context: {list(context.keys())}"
        )
        return MavisResult(
            success=True,
            summary=f"[DRY-RUN] Would have spawned Mavis for: {task[:100]}",
            commit_sha="[DRY-RUN-no-commit]",
            branch="[DRY-RUN-no-branch]",
            files_changed=[],
            pushed=False,
            raw_output="[DRY-RUN mode — no actual Mavis invocation]",
        )

    # ------------------------------------------------------------------
    # Real mode
    # ------------------------------------------------------------------

    async def _real_delegate(
        self, task: str, project_dir: Path, context: dict
    ) -> MavisResult:
        """Spawn a Mavis session via subprocess and wait for result.

        Protocol:
        - We construct a JSON payload with `task` and `context`
        - We call `mavis communication send --command spawn` (or similar)
        - Mavis processes the task, makes changes, commits
        - We parse the response and return a MavisResult

        NOTE: The exact `mavis communication send` interface may evolve.
        This is the v1 implementation; refine as the API stabilizes.
        """
        payload = {
            "task": task,
            "project_dir": str(project_dir),
            "context": context,
        }

        try:
            result = subprocess.run(
                [
                    self.mavis_cli,
                    "communication", "send",
                    "--to", "self",  # placeholder — may need to be the active session
                    "--command", "spawn",
                    "--content", json.dumps(payload),
                ],
                capture_output=True,
                text=True,
                timeout=self.timeout_sec,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return MavisResult(
                success=False,
                summary="",
                error=f"Mavis timed out after {self.timeout_sec}s",
            )
        except FileNotFoundError:
            return MavisResult(
                success=False,
                summary="",
                error=f"Could not find {self.mavis_cli!r} CLI. Is it installed?",
            )
        except Exception as e:
            return MavisResult(
                success=False,
                summary="",
                error=f"Mavis invocation error: {e}",
            )

        if result.returncode != 0:
            return MavisResult(
                success=False,
                summary="",
                error=f"Mavis exited {result.returncode}: {result.stderr.strip()}",
                raw_output=result.stdout,
            )

        # Try to parse JSON response
        try:
            data = json.loads(result.stdout)
            return MavisResult(
                success=data.get("success", False),
                summary=data.get("summary", ""),
                commit_sha=data.get("commit_sha", ""),
                branch=data.get("branch", ""),
                files_changed=data.get("files_changed", []),
                pushed=data.get("pushed", False),
                error=data.get("error"),
                raw_output=result.stdout,
            )
        except json.JSONDecodeError:
            # Fallback: treat stdout as raw summary
            return MavisResult(
                success=True,
                summary=result.stdout.strip()[:500],
                raw_output=result.stdout,
            )


__all__ = ["MavisBridge", "MavisResult"]

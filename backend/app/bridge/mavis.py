"""Mavis bridge — delegate coding tasks to Mavis (Hermes Agent) sub-agent.

Protocol (v1, real mode):
    hermes chat -q "<task>" --worktree --checkpoints [--resume <sid>]

- `-q` (or `--query`): single non-interactive query
- `--worktree`: Mavis works in a git worktree, so changes don't pollute the main branch
- `--checkpoints`: auto-save checkpoints during the run
- `--resume <session-id>`: continue a previous Mavis session
- `-m` / `--model`: override model (optional)
- `--max-turns N`: cap agent turns (default unset = let Mavis decide)

After the run completes, we inspect the worktree's git state to extract:
- `commit_sha`     — `git log -1 --format=%H`
- `files_changed`  — `git diff <base>..HEAD --name-only`  (base = main, or HEAD~1)
- `pushed`         — whether the branch has been pushed to a remote

Output:
- stdout from `hermes chat` is the final assistant reply (truncated in result)
- Stderr is logged but not returned

Two modes:
- real: invoke `hermes` CLI, parse output + git state
- dry_run: log a fake result, no subprocess (default for tests)
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


# Known CLI names — Mavis / Hermes / etc.
KNOWN_MAVIS_BINARIES = ("mavis", "hermes")


def find_mavis_binary() -> Optional[str]:
    """Find the mavis/hermes binary on PATH. Returns the executable name or None."""
    for name in KNOWN_MAVIS_BINARIES:
        path = shutil.which(name)
        if path:
            return path
    return None


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
    mode: str = ""  # "real" or "dry_run"

    def __post_init__(self) -> None:
        if self.files_changed is None:
            self.files_changed = []


class MavisBridge:
    """Bridge to Mavis (Hermes Agent) for coding sub-tasks.

    In `real` mode, spawns `hermes chat -q <task>` and inspects git state.
    In `dry_run` mode, returns a fake result without subprocess.
    """

    def __init__(
        self,
        mode: str = "dry_run",
        *,
        timeout_sec: int = 1800,  # 30 min — coding tasks can take a while
        mavis_cli: Optional[str] = None,
        mavis_model: Optional[str] = None,
        use_worktree: bool = True,
        use_checkpoints: bool = True,
    ) -> None:
        if mode not in ("real", "dry_run"):
            raise ValueError(f"Invalid mode: {mode!r}. Use 'real' or 'dry_run'.")
        self.mode = mode
        self.timeout_sec = timeout_sec
        self.mavis_cli = mavis_cli  # auto-detect if None
        self.mavis_model = mavis_model
        self.use_worktree = use_worktree
        self.use_checkpoints = use_checkpoints

    async def delegate(
        self,
        task: str,
        *,
        project_dir: str | Path,
        context: Optional[dict] = None,
        session_id: Optional[str] = None,
    ) -> MavisResult:
        """Delegate a coding task to Mavis.

        Args:
            task: What to do (e.g. "fix the auth bug in src/auth.py — tokens expire too aggressively")
            project_dir: Working directory for Mavis (the git repo)
            context: Optional context (file paths, related PRs, etc.)
            session_id: Optional Mavis session_id to resume

        Returns:
            MavisResult with success, summary, commit_sha, files_changed, pushed, etc.
        """
        project_dir = Path(project_dir)
        if not project_dir.exists():
            return MavisResult(
                success=False,
                summary="",
                mode=self.mode,
                error=f"project_dir does not exist: {project_dir}",
            )

        # Auto-fallback: if real mode but no mavis binary, fall back to dry-run with a warning
        if self.mode == "real":
            cli = self.mavis_cli or find_mavis_binary()
            if not cli:
                logger.warning(
                    "Real mode requested but no mavis/hermes binary found on PATH. "
                    "Falling back to dry_run. Install mavis or set mavis_cli explicitly."
                )
                return self._dry_run_delegate(task, project_dir, context or {})

        if self.mode == "dry_run":
            return self._dry_run_delegate(task, project_dir, context or {})

        return self._real_delegate(task, project_dir, context or {}, session_id)

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
            mode="dry_run",
        )

    # ------------------------------------------------------------------
    # Real mode — invoke `hermes chat -q <task>`
    # ------------------------------------------------------------------

    def _real_delegate(
        self,
        task: str,
        project_dir: Path,
        context: dict,
        session_id: Optional[str],
    ) -> MavisResult:
        """Spawn Mavis via `hermes chat -q <task>` and inspect git state."""
        cli = self.mavis_cli or find_mavis_binary()
        assert cli is not None  # caller checks

        # Build command
        # Note: -q runs Mavis non-interactively. Output is the final reply.
        # --worktree puts Mavis in a worktree so changes don't pollute main.
        # --checkpoints lets us resume if needed.
        cmd = [
            cli, "chat",
            "-q", task,
            "--worktree" if self.use_worktree else "--no-worktree",
        ]
        if self.use_checkpoints:
            cmd.append("--checkpoints")
        if self.mavis_model:
            cmd.extend(["-m", self.mavis_model])
        if session_id:
            cmd.extend(["--resume", session_id])

        logger.info(f"Invoking Mavis: {' '.join(cmd[:6])}... (cwd={project_dir})")

        try:
            result = subprocess.run(
                cmd,
                cwd=str(project_dir),
                capture_output=True,
                text=True,
                timeout=self.timeout_sec,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return MavisResult(
                success=False,
                summary="",
                mode="real",
                error=f"Mavis timed out after {self.timeout_sec}s",
            )
        except FileNotFoundError:
            return MavisResult(
                success=False,
                summary="",
                mode="real",
                error=f"Could not find {cli!r} CLI. Is it installed?",
            )
        except Exception as e:
            return MavisResult(
                success=False,
                summary="",
                mode="real",
                error=f"Mavis invocation error: {e}",
            )

        if result.returncode != 0 and not result.stdout.strip():
            return MavisResult(
                success=False,
                summary="",
                mode="real",
                error=f"Mavis exited {result.returncode}: {result.stderr.strip()[:500]}",
                raw_output=result.stdout,
            )

        # Mavis did the work. Now inspect the worktree's git state.
        # The summary is the final assistant reply (stdout).
        summary = result.stdout.strip()

        # If --worktree was used, Mavis's changes are in a worktree, not project_dir.
        # Otherwise, changes are in project_dir.
        # For v1, we just inspect project_dir's git state.
        git_state = self._inspect_git_state(project_dir)

        return MavisResult(
            success=True,
            summary=summary[:2000] if summary else "(no output from Mavis)",
            commit_sha=git_state["commit_sha"],
            branch=git_state["branch"],
            files_changed=git_state["files_changed"],
            pushed=git_state["pushed"],
            raw_output=result.stdout + "\n--- stderr ---\n" + result.stderr,
            mode="real",
        )

    def _inspect_git_state(self, project_dir: Path) -> dict:
        """Inspect git state of project_dir after Mavis finished.

        Returns:
            {
                "commit_sha": "<short or full hash>",
                "branch": "<current branch>",
                "files_changed": ["path1", "path2", ...],
                "pushed": True/False,
            }
        """
        result = {
            "commit_sha": "",
            "branch": "",
            "files_changed": [],
            "pushed": False,
        }

        # 1. Current branch
        try:
            branch_out = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=str(project_dir), capture_output=True, text=True, timeout=5, check=False,
            ).stdout.strip()
            result["branch"] = branch_out
        except Exception as e:
            logger.debug(f"git rev-parse failed: {e}")

        # 2. Latest commit SHA
        try:
            sha_out = subprocess.run(
                ["git", "log", "-1", "--format=%H"],
                cwd=str(project_dir), capture_output=True, text=True, timeout=5, check=False,
            ).stdout.strip()
            result["commit_sha"] = sha_out
        except Exception as e:
            logger.debug(f"git log failed: {e}")

        # 3. Files changed in the last commit (most common case after Mavis does work)
        try:
            diff_out = subprocess.run(
                ["git", "show", "--name-only", "--format=", "HEAD"],
                cwd=str(project_dir), capture_output=True, text=True, timeout=5, check=False,
            ).stdout.strip()
            result["files_changed"] = [f for f in diff_out.splitlines() if f]
        except Exception as e:
            logger.debug(f"git show failed: {e}")

        # 4. Pushed? — check if upstream exists and is reachable
        try:
            upstream_check = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "@{u}"],
                cwd=str(project_dir), capture_output=True, text=True, timeout=5, check=False,
            )
            if upstream_check.returncode == 0:
                # Has upstream — check if local is ahead
                ahead_behind = subprocess.run(
                    ["git", "rev-list", "--left-right", "--count", "HEAD...@{u}"],
                    cwd=str(project_dir), capture_output=True, text=True, timeout=5, check=False,
                ).stdout.strip()
                # Format: "<ahead>\t<behind>"
                parts = ahead_behind.split()
                if len(parts) == 2:
                    ahead = int(parts[0])
                    result["pushed"] = ahead == 0
                else:
                    result["pushed"] = False
            else:
                result["pushed"] = False
        except Exception as e:
            logger.debug(f"git upstream check failed: {e}")

        return result


# ---------------------------------------------------------------------------
# Convenience: a default bridge instance
# ---------------------------------------------------------------------------

_default_bridge: Optional[MavisBridge] = None


def get_default_bridge() -> MavisBridge:
    global _default_bridge
    if _default_bridge is None:
        # Default to dry_run for safety — operator must explicitly set mode=real
        _default_bridge = MavisBridge(mode="dry_run")
    return _default_bridge


def set_default_bridge(bridge: MavisBridge) -> None:
    global _default_bridge
    _default_bridge = bridge


__all__ = [
    "MavisBridge",
    "MavisResult",
    "find_mavis_binary",
    "get_default_bridge",
    "set_default_bridge",
]

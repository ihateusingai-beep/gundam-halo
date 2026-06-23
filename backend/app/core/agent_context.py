"""Workspace markdown loader — agent context bootstrap (Sprint 36).

Pattern borrowed from OpenClaw's `~/.openclaw/workspace/` (see
`docs/FEATURE-SPEC-SPRINT36.md` §Tier 1). Loads the user's
personal `AGENTS.md` / `SOUL.md` / `USER.md` / `IDENTITY.md` /
`TOOLS.md` / `BOOTSTRAP.md` / `HEARTBEAT.md` from
`~/.gundam-halo/workspace/` and formats them into a block
that gets appended to every agent turn's system prompt via
`build_system_prompt()`.

First-run behaviour:
- If `~/.gundam-halo/workspace/` does not exist, the loader
  copies the starter files from `app/data/workspace/` (bundled
  with the install). This is the same pattern OpenClaw uses
  for its `AGENTS.md` boilerplate.
- Existing user-edited files are NEVER overwritten. Only
  missing files are seeded.

Failure modes (all soft — return empty results, log warning):
- Workspace dir exists but is empty → empty list, no copy
- Workspace dir exists, files present but unreadable →
  skip those files, log warning, continue with the rest
- Workspace dir creation fails (permission denied on
  `~/.gundam-halo/`) → log error, return empty list. The
  agent runs without workspace context (still functional,
  just less personal).

Performance:
- Module-level cache (`_cache`) keyed by `home` path. Repeated
  calls within the same process (one per agent turn) are
  O(1) after first load. Cache is invalidated on `reset_cache()`
  (exposed for tests).
- A `stat()`-based freshness check (mtime) is also done so
  edits the user makes to `AGENTS.md` get picked up on next
  load without needing a backend restart. This matters for
  the "edit personality → next turn uses it" UX.
"""

from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

# Workspace dir name (sibling to config.toml, logs/, recordings/, etc.)
WORKSPACE_DIR_NAME = "workspace"

# Stable order for the workspace docs in the system prompt.
# BOOTSTRAP.md is intentionally excluded from the prompt —
# it's a one-shot wizard the runtime deletes on first turn,
# and including it would dilute the prompt with stale
# instructions. The loader still surfaces it (so the agent
# can detect "first run") but `format_for_prompt` skips it.
PROMPT_ORDER = [
    "AGENTS.md",
    "SOUL.md",
    "USER.md",
    "IDENTITY.md",
    "TOOLS.md",
    "HEARTBEAT.md",
]


@dataclass(frozen=True)
class WorkspaceDoc:
    """One markdown file from `~/.gundam-halo/workspace/`.

    `name` is the file basename (e.g. `"AGENTS.md"`); `body` is
    the file's raw markdown content; `path` is the absolute
    path on disk.
    """

    name: str
    body: str
    path: Path


# Module-level cache, keyed by home path string. None means
# "no home resolved yet". The cache is intentionally not
# thread-safe — `app/agents/system_prompt.py` calls
# `load_workspace(home)` from the event loop, never from a
# worker thread.
_cache: dict[str, list[WorkspaceDoc]] = {}
_cache_mtimes: dict[str, float] = {}


def reset_cache() -> None:
    """Clear the module-level workspace cache.

    Test-only helper. Lets unit tests force a re-read of disk
    after monkeypatching files into `home`.
    """
    _cache.clear()
    _cache_mtimes.clear()


def _workspace_dir(home: Path) -> Path:
    """Return the absolute workspace dir for a given home."""
    return home / WORKSPACE_DIR_NAME


def _starter_resource(name: str) -> Optional[str]:
    """Read a starter markdown file from the package bundle.

    Returns the file's text content, or None if the bundled
    resource is missing (defensive — should never happen in
    a shipped install).
    """
    try:
        # Python 3.9+ API. `files("app.data.workspace")` returns
        # a traversable; `.joinpath(name).read_text(...)` reads
        # the file as UTF-8.
        return (
            resources.files("app.data.workspace")
            .joinpath(name)
            .read_text(encoding="utf-8")
        )
    except (FileNotFoundError, OSError):
        return None


def ensure_workspace_seeded(home: Path) -> bool:
    """Seed `~/.gundam-halo/workspace/` with starter files if missing.

    Returns True if the workspace dir was newly created (or any
    starter file was copied for the first time), False if all
    expected files were already present.

    Existing user-edited files are NEVER overwritten. Only
    files that don't exist yet are copied from the bundled
    starter set. This is the same pattern OpenClaw uses for
    its workspace seeding.

    Args:
        home: The config home path (typically `Config.home`).

    Returns:
        True on first-time seed, False if everything was
        already there. Used by tests to assert the seed
        ran; the runtime doesn't care which path it took.
    """
    ws_dir = _workspace_dir(home)
    copied_any = False
    try:
        ws_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        logger.warning(
            "ensure_workspace_seeded: cannot create %s: %s", ws_dir, e
        )
        return False
    for name in PROMPT_ORDER + ["BOOTSTRAP.md"]:
        target = ws_dir / name
        if target.exists():
            continue
        starter = _starter_resource(name)
        if starter is None:
            logger.debug("no starter bundled for %s (skipping)", name)
            continue
        try:
            target.write_text(starter, encoding="utf-8")
            copied_any = True
            logger.info("seeded workspace starter: %s", target)
        except OSError as e:
            logger.warning("failed to seed %s: %s", target, e)
    return copied_any


def load_workspace(home: Path, *, force: bool = False) -> List[WorkspaceDoc]:
    """Load `~/.gundam-halo/workspace/*.md` as a list of `WorkspaceDoc`.

    The list is sorted by `PROMPT_ORDER` so AGENTS.md appears
    before SOUL.md before USER.md (the agent reads top-down).

    Args:
        home: The config home path (typically `Config.home`).
        force: Bypass the module-level cache. Test-only.

    Returns:
        The ordered list of workspace docs that exist on disk.
        Empty list if the workspace dir is missing or empty.
    """
    cache_key = str(home)
    if not force:
        cached = _cache.get(cache_key)
        if cached is not None:
            # Freshness check — if any file's mtime changed,
            # invalidate and re-read.
            ws_dir = _workspace_dir(home)
            try:
                current_max_mtime = max(
                    (p.stat().st_mtime for p in ws_dir.glob("*.md")),
                    default=0.0,
                )
            except OSError:
                current_max_mtime = 0.0
            if _cache_mtimes.get(cache_key) == current_max_mtime:
                return cached
            # Stale — fall through to re-read.

    ws_dir = _workspace_dir(home)
    docs: list[WorkspaceDoc] = []
    max_mtime = 0.0
    if not ws_dir.is_dir():
        # First run — try to seed the workspace from the bundled
        # starter set. If seeding succeeds, ws_dir now exists
        # and we fall through to the load loop.
        if not ensure_workspace_seeded(home):
            _cache[cache_key] = docs
            _cache_mtimes[cache_key] = 0.0
            return docs
    for name in PROMPT_ORDER:
        path = ws_dir / name
        if not path.is_file():
            continue
        try:
            body = path.read_text(encoding="utf-8")
            mtime = path.stat().st_mtime
            max_mtime = max(max_mtime, mtime)
        except OSError as e:
            logger.warning("workspace: cannot read %s: %s", path, e)
            continue
        docs.append(WorkspaceDoc(name=name, body=body, path=path))

    # BOOTSTRAP.md is loaded but excluded from the system
    # prompt (one-shot wizard). Surface it as the last entry
    # so callers can detect "first run" via
    # `any(d.name == "BOOTSTRAP.md" for d in docs)`.
    bootstrap_path = ws_dir / "BOOTSTRAP.md"
    if bootstrap_path.is_file():
        try:
            docs.append(
                WorkspaceDoc(
                    name="BOOTSTRAP.md",
                    body=bootstrap_path.read_text(encoding="utf-8"),
                    path=bootstrap_path,
                )
            )
            max_mtime = max(max_mtime, bootstrap_path.stat().st_mtime)
        except OSError:
            pass

    _cache[cache_key] = docs
    _cache_mtimes[cache_key] = max_mtime
    return docs


def format_for_prompt(
    docs: List[WorkspaceDoc],
    *,
    max_chars: int = 12000,
) -> str:
    """Format workspace docs into a single string for the system prompt.

    Concatenates each doc's body under a `## <filename>` header.
    BOOTSTRAP.md is skipped (one-shot wizard, not stable context).

    Args:
        docs: List returned by `load_workspace()`.
        max_chars: Soft cap on the total length. When exceeded,
            the function returns a truncated version with a
            `_... truncated; edit workspace/<file> to keep
            full content_` note appended. The LLM still gets a
            signal that more context exists; it just can't
            act on it directly.

    Returns:
        A markdown-formatted block, ready to append after
        the base system prompt. Empty string if `docs` is
        empty.
    """
    blocks: list[str] = []
    for doc in docs:
        if doc.name == "BOOTSTRAP.md":
            # Skip — see PROMPT_ORDER comment.
            continue
        blocks.append(f"## {doc.name}\n\n{doc.body.strip()}")
    if not blocks:
        return ""
    body = "\n\n---\n\n".join(blocks)
    if len(body) > max_chars:
        body = (
            body[:max_chars]
            + "\n\n_(workspace context truncated at "
            f"{max_chars} chars; edit workspace/<file> to keep "
            "full content)_"
        )
    return body


def has_bootstrap(docs: List[WorkspaceDoc]) -> bool:
    """Return True if `BOOTSTRAP.md` is in the doc list.

    Convenience for callers that want to detect "first run"
    without iterating the doc list.
    """
    return any(d.name == "BOOTSTRAP.md" for d in docs)


# Eagerly silence an unused-import warning on platforms where
# `os` is only referenced indirectly via `os.path`-style paths
# in module-level constants (defensive — `os` may be unused on
# some Python builds but is imported for `os.path`-style API
# parity with the rest of `app/core/`).
_ = os.path


__all__ = [
    "WorkspaceDoc",
    "ensure_workspace_seeded",
    "format_for_prompt",
    "has_bootstrap",
    "load_workspace",
    "reset_cache",
    "WORKSPACE_DIR_NAME",
]
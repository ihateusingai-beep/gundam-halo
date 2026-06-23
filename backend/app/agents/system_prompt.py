"""System-prompt helpers — build the per-turn system prompt.

Currently this adds:
- The base REACT_SYSTEM_PROMPT (or SIMPLE_SYSTEM_PROMPT)
- The user's personal workspace markdown
  (`~/.gundam-halo/workspace/*.md` — Sprint 36 Tier 1,
  pattern from OpenClaw). Loaded via
  `app.core.agent_context.load_workspace`.
- A "user identity" line if we know who the user is
- An "auto-recall" block of the user's memory entries (M7-Phase-2)

Order of appended blocks (stable across runs so the LLM can
rely on it):
1. Workspace markdown (behaviour + personality)
2. "## Who you're talking to" (if display name known)
3. "## What you remember about this user" (memory recall)

The recall is **appended to the system message** rather than
the user message, so the LLM sees it as static context, not
as something the user just said.
"""
from __future__ import annotations

import logging
from typing import Optional

from app.core.agent_context import format_for_prompt, load_workspace
from app.core.config import get_config
from app.core.types import AgentContext
from app.memory.user_memory import (
    UserMemoryStore,
    get_user_memory_store,
    user_key_for,
)

logger = logging.getLogger(__name__)


def build_system_prompt(
    base_prompt: str,
    context: Optional[AgentContext] = None,
    *,
    store: Optional[UserMemoryStore] = None,
) -> str:
    """Augment the base system prompt with workspace + identity + memory recall.

    The returned string is the full system message that should be sent
    to the LLM. It always starts with `base_prompt` and then appends:

    - Sprint 36 Tier 1: workspace markdown from
      `~/.gundam-halo/workspace/` (AGENTS.md, SOUL.md, USER.md,
      IDENTITY.md, TOOLS.md, HEARTBEAT.md). Auto-seeded from
      bundled starter files on first run; subsequent user
      edits picked up via mtime check (no restart needed).
    - A "## Who you're talking to" block if we have a display name
    - A "## What you remember about this user" block listing memory entries
    """
    if context is None:
        # No context → no identity, no recall. Still try to
        # include workspace markdown (it's agent-wide context,
        # not per-turn context).
        try:
            cfg = get_config()
            docs = load_workspace(cfg.home)
            workspace_block = format_for_prompt(docs)
        except Exception as e:  # noqa: BLE001
            logger.debug("workspace markdown load failed: %s", e)
            workspace_block = ""
        if not workspace_block:
            return base_prompt
        return base_prompt + "\n\n---\n\n" + workspace_block

    # Resolve the user key the same way the memory tools do
    user_key = None
    if context.user_display_name:
        user_key = user_key_for(context.user_display_name)
    elif context.user_id:
        user_key = user_key_for(context.user_id)

    extra_blocks: list[str] = []

    # 1. Workspace markdown (Tier 1 — agent-wide context).
    #    Always included regardless of user_key; even without
    #    identity info, the agent still gets its personality
    #    contract.
    try:
        cfg = get_config()
        docs = load_workspace(cfg.home)
        workspace_block = format_for_prompt(docs)
        if workspace_block:
            extra_blocks.append(workspace_block)
    except Exception as e:  # noqa: BLE001
        logger.debug("workspace markdown load failed: %s", e)

    # 2. Identity
    if context.user_display_name:
        channel = context.channel or "chat"
        extra_blocks.append(
            f"## Who you're talking to\n"
            f"You are talking to **{context.user_display_name}** "
            f"via the {channel} channel. Use their name when it would feel natural."
        )

    # 3. Memory recall
    if user_key:
        try:
            store = store or get_user_memory_store()
            entries = store.list_keys(user_key)
        except Exception as e:  # noqa: BLE001
            logger.debug(f"memory recall failed: {e}")
            entries = []

        if entries:
            # Cap the recall to a sane number of entries; sort by
            # updated_at desc (already done by list_keys).
            MAX_RECALL_ENTRIES = 25
            lines = ["## What you remember about this user"]
            for e in entries[:MAX_RECALL_ENTRIES]:
                lines.append(f"- **{e.key}**: {e.value}")
            if len(entries) > MAX_RECALL_ENTRIES:
                lines.append(
                    f"_(+ {len(entries) - MAX_RECALL_ENTRIES} more entries; "
                    f"use `memory_read` to fetch them all)_"
                )
            extra_blocks.append("\n".join(lines))

    if not extra_blocks:
        return base_prompt

    return base_prompt + "\n\n---\n\n" + "\n\n".join(extra_blocks)


__all__ = ["build_system_prompt"]

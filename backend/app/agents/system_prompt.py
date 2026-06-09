"""System-prompt helpers — build the per-turn system prompt.

Currently this adds:
- The base REACT_SYSTEM_PROMPT (or SIMPLE_SYSTEM_PROMPT)
- A "user identity" line if we know who the user is
- An "auto-recall" block of the user's memory entries (M7-Phase-2)

The recall is **prepended to the system message** rather than to the
user message, so the LLM sees it as static context, not as something
the user just said.
"""
from __future__ import annotations

import logging
from typing import Optional

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
    """Augment the base system prompt with identity + memory recall.

    The returned string is the full system message that should be sent
    to the LLM. It always starts with `base_prompt` and then appends:

    - A "## Who you're talking to" block if we have a display name
    - A "## What you remember about this user" block listing memory entries
    """
    if context is None:
        return base_prompt

    # Resolve the user key the same way the memory tools do
    user_key = None
    if context.user_display_name:
        user_key = user_key_for(context.user_display_name)
    elif context.user_id:
        user_key = user_key_for(context.user_id)
    if not user_key:
        return base_prompt

    extra_blocks: list[str] = []

    # 1. Identity
    if context.user_display_name:
        channel = context.channel or "chat"
        extra_blocks.append(
            f"## Who you're talking to\n"
            f"You are talking to **{context.user_display_name}** "
            f"via the {channel} channel. Use their name when it would feel natural."
        )

    # 2. Memory recall
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

"""memory_read + memory_write tools — per-user key/value memory.

These are the agent's view of `UserMemoryStore`. The tools are scoped
to a specific user via the `AgentContext.user_id` (or
`user_display_name`) — so the agent always operates on "the user
who's talking to me right now", not some global store.

Why two tools instead of one combined `memory` tool?
- Simpler schema validation (the LLM doesn't have to branch on action)
- Cleaner audit log (read vs write are different tool types)
- Easier to restrict (you could grant read but not write later)

Naming convention for keys:
- We slugify on write. So "Preferred Name" becomes "preferred_name".
- The agent is told to use snake_case short slugs in the description.

Storage: see `app.memory.user_memory.UserMemoryStore`.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.memory.user_memory import (
    MemoryEntry,
    UserMemoryStore,
    get_user_memory_store,
    slugify_key,
    user_key_for,
)
from app.tools._stubs import BaseTool
from app.core.registry import register_tool

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_user_key(
    *,
    explicit_user: Optional[str] = None,
    display_name: Optional[str] = None,
    transport_id: Optional[str] = None,
) -> Optional[str]:
    """Resolve which user this tool call is for.

    Priority:
    1. explicit_user — the agent passed it (rare)
    2. display_name — from `AgentContext.user_display_name` (preferred)
    3. transport_id — fallback if no display name (e.g. web session
       without a configured name)
    4. None — caller is missing context, refuse to write silently
    """
    if explicit_user:
        return user_key_for(explicit_user)
    if display_name:
        return user_key_for(display_name)
    if transport_id:
        return user_key_for(transport_id)
    return None


def _format_entry(entry: MemoryEntry) -> str:
    """Format a memory entry for display to the LLM."""
    return f"{entry.key}: {entry.value}"


# ---------------------------------------------------------------------------
# MemoryReadTool
# ---------------------------------------------------------------------------


@register_tool("memory_read")
class MemoryReadTool(BaseTool):
    """Read one or all keys from a user's memory."""

    name = "memory_read"
    description = (
        "Read a value from the user's persistent memory. The memory is per-user "
        "(scoped to whoever is currently talking to you). Pass `key` to read a "
        "specific entry, or omit it to list all known entries. Keys are "
        "snake_case slugs (e.g. 'preferred_name', 'timezone', 'favorite_gundam'). "
        "Use this when you want to remember something the user told you earlier "
        "in this session or in a previous one."
    )
    parameters: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "key": {
                "type": "string",
                "description": (
                    "The key to read. Omit (or pass empty) to list all keys. "
                    "Examples: 'preferred_name', 'timezone', 'primary_language'."
                ),
            },
        },
    }

    async def run(
        self,
        key: str = "",
        *,
        store: Optional[UserMemoryStore] = None,
        display_name: Optional[str] = None,
        transport_id: Optional[str] = None,
        **_: Any,
    ) -> str:
        user_key = _resolve_user_key(display_name=display_name, transport_id=transport_id)
        if not user_key:
            return "Error: no user context (no display name or transport_id available)"
        store = store or get_user_memory_store()

        if not key or not key.strip():
            entries = store.list_keys(user_key)
            if not entries:
                return f"(no memory entries for user {user_key!r})"
            return "\n".join(_format_entry(e) for e in entries)

        slug = slugify_key(key)
        entry = store.get(user_key, slug)
        if entry is None:
            return f"(no entry for key {key!r} in user {user_key!r})"
        return _format_entry(entry)


# ---------------------------------------------------------------------------
# MemoryWriteTool
# ---------------------------------------------------------------------------


@register_tool("memory_write")
class MemoryWriteTool(BaseTool):
    """Write (or delete) a value in the user's memory."""

    name = "memory_write"
    description = (
        "Write a value to the user's persistent memory, scoped to whoever is "
        "currently talking to you. Pass `key` and `value` to write, or `key` "
        "with `delete=true` to remove an entry. Keys are snake_case slugs. "
        "Use this to remember preferences, facts, or context the user shared "
        "and that you'd want to recall in a future session (e.g. 'preferred "
        "name: Ken', 'timezone: Asia/Hong_Kong', 'favorite Gundam: Unicorn')."
    )
    parameters: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "key": {
                "type": "string",
                "description": "Snake_case key, e.g. 'preferred_name' or 'timezone'.",
            },
            "value": {
                "type": "string",
                "description": "The value to remember. Free-form text, max 8 KB.",
            },
            "delete": {
                "type": "boolean",
                "description": "If true, delete the key instead of writing. Default false.",
            },
        },
        "required": ["key"],
    }

    async def run(
        self,
        key: str,
        value: str = "",
        delete: bool = False,
        *,
        store: Optional[UserMemoryStore] = None,
        display_name: Optional[str] = None,
        transport_id: Optional[str] = None,
        **_: Any,
    ) -> str:
        user_key = _resolve_user_key(display_name=display_name, transport_id=transport_id)
        if not user_key:
            return "Error: no user context (no display name or transport_id available)"
        if not key or not key.strip():
            return "Error: 'key' is required"
        store = store or get_user_memory_store()

        if delete:
            removed = store.delete(user_key, key)
            if removed:
                return f"Deleted memory[{key!r}] for user {user_key!r}"
            return f"(no memory[{key!r}] to delete for user {user_key!r})"

        if not value:
            return "Error: 'value' is required (or pass delete=true)"

        try:
            entry = store.set(user_key, key, value)
        except ValueError as e:
            return f"Error: {e}"
        return f"Saved memory[{entry.key}] for user {entry.user!r} = {entry.value!r}"


__all__ = ["MemoryReadTool", "MemoryWriteTool"]

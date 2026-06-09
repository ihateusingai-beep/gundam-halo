"""User memory API — read-only dashboard viewer for the M7-Phase-2
UserMemoryStore.

Endpoints:
  GET /api/memory                        — list all user keys
  GET /api/memory/{user}                 — list all keys for a user
  GET /api/memory/{user}/{key}           — read a single entry
  DELETE /api/memory/{user}/{key}        — delete an entry

The dashboard is read-mostly (humans want to inspect what the agent
has learned, and fix wrong/oversharing entries). Writes go through
the agent via the memory_write tool, not from the dashboard, because:

1. Keeps the LLM-driven write path in one place (no race with a
   dashboard edit).
2. The dashboard is for review/cleanup, not authoring.
3. Single-user assumption: nobody else should be writing here anyway.

Like the secrets API, we never return things that would be sensitive
on purpose — but memory IS supposed to be user-visible (it's their
preferences, not secrets), so we return values normally.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException

from app.memory.user_memory import get_user_memory_store

logger = logging.getLogger(__name__)
router = APIRouter()


def _serialize_entry(e) -> Dict[str, Any]:
    return {
        "key": e.key,
        "value": e.value,
        "updated_at": e.updated_at,
        "created_at": e.created_at,
    }


@router.get("", response_model=Dict[str, Any])
async def list_users() -> Dict[str, Any]:
    """List all user keys that have at least one memory entry.

    Response shape:
      { "users": ["ken", "alice", ...] }
    """
    store = get_user_memory_store()
    return {"users": store.list_users()}


@router.get("/{user}", response_model=Dict[str, Any])
async def list_user_entries(user: str) -> Dict[str, Any]:
    """List all keys for *user*, newest first.

    Response shape:
      {
        "user": "ken",
        "entries": [
          {"key": "preferred_name", "value": "Ken", "updated_at": ..., "created_at": ...},
          ...
        ]
      }
    """
    store = get_user_memory_store()
    entries = store.list_keys(user)
    return {
        "user": user,
        "entries": [_serialize_entry(e) for e in entries],
    }


@router.get("/{user}/{key}", response_model=Dict[str, Any])
async def read_entry(user: str, key: str) -> Dict[str, Any]:
    """Read a single (user, key) entry.

    404 if missing.
    """
    store = get_user_memory_store()
    entry = store.get(user, key)
    if entry is None:
        raise HTTPException(
            status_code=404,
            detail=f"No memory entry for user={user!r} key={key!r}",
        )
    return _serialize_entry(entry)


@router.delete("/{user}/{key}", response_model=Dict[str, Any])
async def delete_entry(user: str, key: str) -> Dict[str, Any]:
    """Delete a (user, key) entry. Idempotent — 404 if missing."""
    store = get_user_memory_store()
    removed = store.delete(user, key)
    if not removed:
        raise HTTPException(
            status_code=404,
            detail=f"No memory entry for user={user!r} key={key!r}",
        )
    return {"deleted": True, "user": user, "key": key}


__all__ = ["router"]

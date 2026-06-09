"""Secrets API — manage runtime secrets from the dashboard.

Endpoints:
  GET    /api/secrets           — masked status of all known secrets
  POST   /api/secrets           — set one or more secrets
  DELETE /api/secrets/{name}    — clear a specific secret
  POST   /api/secrets/clear     — clear all managed secrets

Security:
- Values are NEVER returned in responses (only `configured` boolean)
- We audit-log the action (set / clear) WITHOUT the value
- File is 0600, atomic write
- The /api/secrets endpoint requires the server to be running
  locally — there's no auth middleware yet (single-user assumption)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.secrets_store import SECRET_KEYS, get_secret_store

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class SecretSetItem(BaseModel):
    name: str = Field(..., description="Env var name, e.g. MINIMAX_API_KEY")
    value: str = Field(..., min_length=1, max_length=2048)


class SecretSetRequest(BaseModel):
    secrets: List[SecretSetItem] = Field(..., min_length=1, max_length=10)


class SecretClearRequest(BaseModel):
    names: List[str] = Field(..., min_length=1, max_length=10)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=Dict[str, Any])
async def get_secrets() -> Dict[str, Any]:
    """Return masked status of every managed secret.

    Response shape:
      {
        "MINIMAX_API_KEY": {
          "label": "MiniMax API Key",
          "configured": true,
          "source": "override"     # override | env | none
        },
        ...
      }
    """
    return get_secret_store().status_payload()


@router.post("", response_model=Dict[str, Any])
async def set_secrets(payload: SecretSetRequest) -> Dict[str, Any]:
    """Set one or more secrets. Atomic write to .env + in-memory reload.

    The endpoint will reject unknown env var names so the dashboard
    can't accidentally write garbage into the .env file.
    """
    store = get_secret_store()
    set_count = 0
    for item in payload.secrets:
        try:
            store.set(item.name, item.value)
            set_count += 1
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    # Invalidate the config cache so the next get_config() reloads
    # from disk + env. This makes LLM and Telegram pick up the
    # new values on their next request without a server restart.
    if store.is_config_cache_dirty():
        store.invalidate_config_cache()

    # Audit log the action (without the value!)
    logger.info(
        f"secrets.set: count={set_count}, keys={[i.name for i in payload.secrets]}"
    )
    return store.status_payload()


@router.delete("/{name}", response_model=Dict[str, Any])
async def clear_secret(name: str) -> Dict[str, Any]:
    """Clear a specific secret."""
    try:
        store = get_secret_store()
        store.clear(name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if store.is_config_cache_dirty():
        store.invalidate_config_cache()

    logger.info(f"secrets.clear: name={name}")
    return store.status_payload()


@router.post("/clear", response_model=Dict[str, Any])
async def clear_all_secrets(payload: SecretClearRequest) -> Dict[str, Any]:
    """Clear a batch of secrets (only those listed in the request)."""
    store = get_secret_store()
    cleared: list[str] = []
    for name in payload.names:
        try:
            store.clear(name)
            cleared.append(name)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    if store.is_config_cache_dirty():
        store.invalidate_config_cache()

    logger.info(f"secrets.clear_batch: names={cleared}")
    return store.status_payload()


__all__ = ["router"]

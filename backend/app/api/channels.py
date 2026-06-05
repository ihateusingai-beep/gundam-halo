"""Channel status REST API."""

from __future__ import annotations

from fastapi import APIRouter

from app.channels.manager import get_channel_manager

router = APIRouter()


@router.get("")
async def list_channels() -> dict:
    """List all started channels and their status."""
    return {"channels": get_channel_manager().status()}

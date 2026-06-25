"""Health check endpoint."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app import __version__

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    version: str
    name: str


@router.get("", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Basic health check."""
    return HealthResponse(status="ok", version=__version__, name="gundam-halo")

"""Health check endpoint.

Sprint 42: `health.router` is now mounted at `prefix="/api/health"`.
The bare `/health` path is preserved as a legacy alias via a
separate router mounted at `prefix="/health"` (see `app/main.py`)
so existing smoke scripts + Tailscale health probes continue
to work regardless of which convention they follow.
"""

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


# Separate router for the legacy /health alias (mounted at prefix="/health"
# in main.py). Kept on a separate router so the OpenAPI schema
# (/api/health docs) only documents the canonical route.
legacy_router = APIRouter()


@legacy_router.get("", response_model=HealthResponse, include_in_schema=False)
async def health_legacy() -> HealthResponse:
    """Legacy alias — returns the same payload as /api/health.

    Kept for backwards compat with smoke scripts that predate
    the /api prefix convention (install.sh probes, Tailscale
    healthCheck ACL rules, etc.).
    """
    return await health()

"""Gundam Halo — FastAPI entry point.

Boot order:
1. Load config (TOML + env)
2. Initialize logging
3. Initialize core (registry, event bus)
4. Initialize engines (MiniMax)
5. Initialize agents, channels (deferred — lazy on first use)
6. Initialize security (audit log)
7. Mount API routes
8. Start uvicorn
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_config
from app.core.events import get_event_bus, reset_event_bus
from app.core.registry import (
    AgentRegistry,
    ChannelRegistry,
    EngineRegistry,
    ToolRegistry,
)
from app.core.logging import configure_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """App startup/shutdown."""
    cfg = get_config()
    configure_logging(level=cfg.log_level)
    logger.info(
        "Gundam Halo starting",
        extra={
            "version": app.version,
            "log_level": cfg.log_level,
            "minimax_model": cfg.llm.default_model,
        },
    )

    # Initialize event bus
    bus = get_event_bus(record_history=True)
    logger.debug("Event bus initialized")

    # Initialize core registries (already class-level, just confirm)
    for reg in [AgentRegistry, ChannelRegistry, EngineRegistry, ToolRegistry]:
        logger.debug(f"Registry ready: {reg.__name__}")

    yield

    # Shutdown
    logger.info("Gundam Halo shutting down")
    reset_event_bus()


def create_app() -> FastAPI:
    """Application factory."""
    cfg = get_config()

    app = FastAPI(
        title="Gundam Halo",
        description="Personal AI agent on Mac. Hermes-like feel, MiniMax brain, deep Mac control.",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS — open for local dev, restrict in production
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://localhost:8765"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount routes
    from app.api import health, projects, sessions, mac, system

    app.include_router(health.router, prefix="/health", tags=["health"])
    app.include_router(system.router, prefix="/api/system", tags=["system"])
    app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
    app.include_router(sessions.router, prefix="/api/sessions", tags=["sessions"])
    app.include_router(mac.router, prefix="/api/mac", tags=["mac"])

    return app


# Module-level app for `uvicorn app.main:app`
app = create_app()

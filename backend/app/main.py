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
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    """App startup/shutdown."""
    cfg = get_config()
    configure_logging(level=cfg.log_level)
    logger.info(
        "Gundam Halo starting",
        extra={
            "version": application.version,
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

    # Start all enabled channels (Telegram in dry-run if no token)
    from app.channels.manager import get_channel_manager
    manager = get_channel_manager()
    await manager.start_all()

    # Index on-disk sessions for the API to know about
    from app.api.sessions import init_persistence_on_startup
    init_persistence_on_startup()

    yield

    # Shutdown
    logger.info("Gundam Halo shutting down")
    await manager.stop_all()
    reset_event_bus()


def create_app() -> FastAPI:
    """Application factory.

    Note: we name the local variable `halo_app` (not `app`) to avoid a
    subtle Python scoping issue where the module-level `app` package
    shadowed the function-local FastAPI instance.
    """
    cfg = get_config()

    halo_app = FastAPI(
        title="Gundam Halo",
        description="Personal AI agent on Mac. Hermes-like feel, MiniMax brain, deep Mac control.",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS — open for local dev, restrict in production
    halo_app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://localhost:8765"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount routes
    from app.api import health, projects, sessions, mac, system, channels as channels_api, ws as ws_api, settings as settings_api
    from app.tools.builder import default_tools

    # Import agents so they register themselves (side-effect of @register decorator)
    import app.agents.simple  # noqa: F401
    import app.agents.native_react  # noqa: F401
    logger.debug(f"Registered agents: {list(AgentRegistry.keys())}")

    # Import channels so they register themselves
    import app.channels.telegram  # noqa: F401
    logger.debug(f"Registered channels: {list(ChannelRegistry.keys())}")

    # Register default tools in the ToolRegistry (so they're discoverable
    # even though we typically pass them explicitly to agents)
    for tool in default_tools():
        ToolRegistry.register_value(tool.name, tool)
    logger.debug(f"Registered {len(default_tools())} default tools")

    halo_app.include_router(health.router, prefix="/health", tags=["health"])
    halo_app.include_router(system.router, prefix="/api/system", tags=["system"])
    halo_app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
    halo_app.include_router(sessions.router, prefix="/api/sessions", tags=["sessions"])
    halo_app.include_router(mac.router, prefix="/api/mac", tags=["mac"])
    halo_app.include_router(channels_api.router, prefix="/api/channels", tags=["channels"])
    halo_app.include_router(ws_api.router, tags=["websocket"])
    halo_app.include_router(settings_api.router, prefix="/api", tags=["settings"])

    return halo_app


# Module-level instance for `uvicorn app.main:app`
halo_app = create_app()
# Compatibility alias for `uvicorn app.main:app`
app = halo_app

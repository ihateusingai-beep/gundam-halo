"""Gundam Halo — FastAPI entry point.

Boot order:
1. Load .env (HALO_HOME/.env) into os.environ — this MUST run
   before any module reads cfg.llm.api_key, otherwise the
   `RuntimeError("MINIMAX_API_KEY not set")` triggers even when
   the user has stored a key in the dashboard. We do a stdlib
   mini-parser here to avoid pulling in python-dotenv as a dep.
2. Load config (TOML + env)
3. Initialize logging
4. Initialize core (registry, event bus)
5. Initialize engines (MiniMax)
6. Initialize agents, channels (deferred — lazy on first use)
7. Initialize security (audit log)
8. Mount API routes
9. Start uvicorn
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_config
from app.core.events import get_event_bus, reset_event_bus
from app.core.lockfile import (
    LockHeldError,
    acquire as acquire_backend_lock,
    default_lock_path,
    release as release_backend_lock,
)
from app.core.registry import (
    PRODUCTION_READ_REGISTRIES,
    EngineRegistry,
)
from app.core.logging import configure_logging


def _load_halo_dotenv() -> int:
    """Best-effort load of $HALO_HOME/.env into os.environ.

    Mavis fix (2026-06-14, Sprint 16 follow-up): the previous
    Secrets-tab save path wrote the API key to .env but never told
    the OS about it on the next process start, so every restart
    required a manual `source .env && uvicorn ...`. We now do a
    minimal KEY=VALUE parser at module import time — before any
    cfg.llm.api_key is consulted.

    Format handled:
      - blank lines and `# ...` comments skipped
      - `KEY=VALUE` and `KEY="VALUE WITH SPACES"` both supported
      - leading `export ` is tolerated
      - existing os.environ values WIN (we never clobber)
    Format NOT handled (would require python-dotenv):
      - $OTHER_VAR interpolation
      - line continuations
      - multi-line quoted values
    These are not used by the current dashboard-written .env.
    """
    halo_home = os.environ.get("HALO_HOME", str(Path.home() / ".gundam-halo"))
    env_path = Path(halo_home) / ".env"
    if not env_path.exists():
        return 0
    n = 0
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip()
        if (v.startswith('"') and v.endswith('"')) or (
            v.startswith("'") and v.endswith("'")
        ):
            v = v[1:-1]
        if k and k not in os.environ:
            os.environ[k] = v
            n += 1
    return n


# Load .env before any other module reads config. This is
# intentionally at module-import time (not inside lifespan) so
# that config.py's get_config() finds the keys even on the first
# call.
_loaded = _load_halo_dotenv()
if _loaded:
    import sys
    print(f"[main] loaded {_loaded} env var(s) from $HALO_HOME/.env", file=sys.stderr)


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

    # Sprint 34 / Track 2 (Sprint 26 §4.2): acquire the single-instance
    # lock file BEFORE any other init. If the launchd-supervised
    # daemon is already running, or another manual dev process is
    # up, we exit cleanly with a clear error pointing at the holder.
    # The acquire() call is sync + fast (fcntl.flock is non-blocking);
    # the rare slow path is when the directory doesn't exist yet,
    # which we mkdir above.
    try:
        lock_info = acquire_backend_lock(path=default_lock_path(halo_home=cfg.home))
    except LockHeldError as e:
        logger.error(str(e))
        # Print to stderr so `uvicorn` and `launchd` both surface it
        # in their respective logs. We don't raise — we just exit
        # the lifespan so the app shuts down cleanly with code 1.
        import sys as _sys

        print(str(e), file=_sys.stderr)
        raise SystemExit(1) from None
    logger.debug(
        "Backend lock acquired (pid=%d host=%s path=%s)",
        lock_info.pid,
        lock_info.host,
        default_lock_path(halo_home=cfg.home),
    )

    # Initialize event bus
    bus = get_event_bus(record_history=True)
    logger.debug("Event bus initialized")

    # Initialize core registries (already class-level, just confirm).
    # `PRODUCTION_READ_REGISTRIES` is the canonical list (Sprint 32 P0-1
    # v2) — logging all 6 ensures the startup banner matches what
    # production code actually reads. EngineRegistry is also included
    # for completeness (reserved for future live2d backends).
    for reg in PRODUCTION_READ_REGISTRIES + (EngineRegistry,):
        logger.debug(f"Registry ready: {reg.__name__}")

    # Tool → Live2D motion mapper (M3-B4). Translates TOOL_CALL_START/END
    # into LIVE2D_TOOL_TRIGGER so the cockpit avatar reacts to agent actions
    # in real time, even when the user isn't speaking.
    from app.voice.live2d.tool_motion_mapper import ToolMotionMapper
    tool_motion_mapper = ToolMotionMapper(bus=bus)
    tool_motion_mapper.start()

    # Start all enabled channels (Telegram in dry-run if no token)
    from app.channels.manager import get_channel_manager
    from app.channels.telegram_handler import telegram_handler
    manager = get_channel_manager()

    # Wire the Telegram handler BEFORE start_all so the channel has
    # a callback to route messages through. If the channel is
    # disabled in config, the handler is unused but harmlessly set.
    manager.set_handler("telegram", telegram_handler)
    await manager.start_all()

    # Index on-disk sessions for the API to know about
    from app.api.sessions import init_persistence_on_startup
    init_persistence_on_startup()

    # M12: init the structured memory layer (SQLite + FAISS + embedder)
    from app.memory.lifecycle import init_memory_on_startup

    init_memory_on_startup()

    # M15: wire the voice WebSocket agent callback so a recorded audio
    # turn (release after hold-to-talk) actually runs the agent and
    # streams sentences to TTS in real time. Without this, finalize_turn()
    # skips the agent call and the TTS pipeline never fires — the user
    # sees no reply after ASR completes. Fresh agent per turn so the
    # config cache (invalidated by /api/secrets writes) is respected.
    from app.api.voice_ws import set_agent_callback
    from app.agents import native_react  # noqa: F401 — ensure registered
    from typing import AsyncIterator

    async def voice_agent_callback(
        sid: str, text: str
    ) -> AsyncIterator[str] | None:
        """Run the native_react agent streaming for a voice turn.

        Yields sentence-sized chunks as the LLM emits them. The
        voice WS handler forwards each chunk to TTS immediately,
        so the user hears the first sentence in ~1-2s instead of
        waiting for the entire reply + a full TTS synthesis.
        """
        cfg = get_config()
        if not cfg.llm.api_key:
            logger.warning(
                f"Voice turn {sid}: MINIMAX_API_KEY not configured, "
                "skipping agent"
            )
            return None
        try:
            from app.engines.minimax import MiniMaxEngine
            from app.tools.builder import default_tools
            from app.core.registry import AgentRegistry

            engine = MiniMaxEngine(
                api_key=cfg.llm.api_key,
                base_url=cfg.llm.base_url,
                model=cfg.llm.default_model,
            )
            tools = default_tools()
            agent_cls = AgentRegistry.get("native_react")
            agent = agent_cls(engine, cfg.llm.default_model, tools=tools)
            return agent.run_streaming(text)
        except Exception as e:
            logger.error(f"Voice agent callback error (sid={sid}): {e}")
            return None

    set_agent_callback(voice_agent_callback)
    logger.debug("Voice agent callback wired (native_react streaming, per-turn)")

    # M14-T1: wire the per-project filesystem manager as a singleton
    # on app.state so request handlers (and the new health probe)
    # can reach it without re-creating the manager per request.
    # Kept AFTER init_memory_on_startup so the manager is the
    # *last* thing initialised — the order matters for the test
    # suite that asserts on shared singleton state.
    from app.projects.manager import init_project_manager, set_project_manager

    set_project_manager(application, init_project_manager(home=cfg.home))
    logger.debug("ProjectManager singleton wired (home=%s)", cfg.home)

    yield

    # Shutdown
    logger.info("Gundam Halo shutting down")
    # M14-T1: drop the manager reference so a fresh lifespan can
    # pick up a new HALO_HOME (matters for tests that monkey-patch
    # the env var between lifespan invocations).
    from app.projects.manager import reset_project_manager

    reset_project_manager(application)
    tool_motion_mapper.stop()
    await manager.stop_all()
    reset_event_bus()
    # M12: stop the background embedder cleanly
    try:
        from app.memory.lifecycle import reset_background_embedder

        reset_background_embedder()
    except Exception:
        pass
    # Sprint 34 / Track 2: release the backend lock so the next
    # process (manual `./run.sh` or launchd's respawn) can acquire
    # it cleanly. Best-effort; the file may already be gone.
    try:
        release_backend_lock(path=default_lock_path(halo_home=cfg.home))
    except Exception as e:
        logger.debug("Lock release at shutdown failed (non-fatal): %s", e)


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
        allow_origins=[
            "http://localhost:5173",
            "http://localhost:8765",
            "http://localhost:8766",
            "http://127.0.0.1:5173",
            "http://127.0.0.1:8765",
            "http://127.0.0.1:8766",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount routes
    from app.api import health, projects, sessions, mac, system, channels as channels_api, ws as ws_api, settings as settings_api, secrets as secrets_api, memory as memory_api
    # M12 recall router: register BEFORE the legacy /api/memory/{user}
    # router so the new sub-paths (`/sessions`, `/search`, `/recall`,
    # `/rebuild`) don't get shadowed by the catch-all `{user}` route.
    from app.api import memory_recall as memory_recall_api

    halo_app.include_router(memory_recall_api.router, prefix="/api/memory", tags=["memory-recall"])
    halo_app.include_router(memory_api.router, prefix="/api/memory", tags=["memory"])

    # Mount 8 of the 9 missing routers that were imported on line 151
    # but never wired up — caused 53 pre-existing 404s in pytest and
    # 5/7 smoke-test failures. The 9th (`projects`) is mounted below
    # immediately after `projects_health` so its static `/health` path
    # wins registration-order over the catch-all `/{name}` route.
    # `health` mounts with prefix="/api/health" (Sprint 42 — matches
    # REST convention; external health probes like Tailscale ACLs
    # expect this path). The legacy bare `/health` mount is preserved
    # via `health.legacy_router` for backwards compat with the
    # frontend `api.ts:health` helper + older smoke scripts.
    halo_app.include_router(health.router, prefix="/api/health", tags=["health"])
    halo_app.include_router(
        health.legacy_router, prefix="/health", tags=["health-legacy"]
    )
    halo_app.include_router(sessions.router, prefix="/api/sessions", tags=["sessions"])
    halo_app.include_router(mac.router, prefix="/api/mac", tags=["mac"])
    halo_app.include_router(system.router, prefix="/api/system", tags=["system"])
    halo_app.include_router(channels_api.router, prefix="/api/channels", tags=["channels"])
    halo_app.include_router(ws_api.router, tags=["ws"])
    halo_app.include_router(settings_api.router, prefix="/api/settings", tags=["settings"])
    halo_app.include_router(secrets_api.router, prefix="/api/secrets", tags=["secrets"])

    # M14-T1: per-project filesystem health probe at
    # `/api/projects/health`. Returns `{ok, count}`. Full CRUD
    # endpoints are T2's job — the existing `app.api.projects`
    # router (mounted below) is the M4-era scaffolding that T2
    # will refactor on top of `ProjectManager`.
    from app.api import projects_health

    halo_app.include_router(projects_health.router, prefix="/api/projects", tags=["projects"])

    # Mount the full `projects` CRUD router AFTER `projects_health`
    # so the static `/api/projects/health` route is registered first
    # and the catch-all `GET/DELETE /{name}` below doesn't shadow it.
    halo_app.include_router(projects.router, prefix="/api/projects", tags=["projects"])

    # M13 first-run wizard — 11 endpoints. Always mounted (the wizard
    # itself decides whether to show, based on the live detected state).
    from app.api import setup as setup_api

    halo_app.include_router(setup_api.router, prefix="/api/setup", tags=["setup"])

    # Voice layer (M1) — only mount if enabled in config
    if get_config().voice.enabled:
        from app.api import voice_ws

        halo_app.include_router(voice_ws.router, tags=["voice"])
        logger.info("Voice layer mounted at /ws/voice")
    else:
        logger.info("Voice layer disabled (set voice.enabled=true in config.toml)")

    return halo_app


# Module-level instance for `uvicorn app.main:app`
halo_app = create_app()
# Compatibility alias for `uvicorn app.main:app`
app = halo_app

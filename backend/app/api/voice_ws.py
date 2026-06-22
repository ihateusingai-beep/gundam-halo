"""Voice WebSocket — back-compat shim.

Sprint 32 P1.1: `voice_ws.py` was 1137 LoC (4 endpoint decorators
+ 1 637-line WS handler + 3 helper categories + a config
persistence block + a restart coordination flag). This shim
preserves the **public import surface** while delegating the
real work to 4 focused modules:

  - `app.api.ws_protocol` — the `/ws/voice` route + agent-callback
    plumbing + JSON/binary frame helpers.
  - `app.api.voice_pipeline_handler` — the per-sentence
    streaming helper that consumes the agent's iterator and
    forwards each chunk to TTS / Live2D.
  - `app.api.voice_config_api` — the REST endpoints
    (`/voice/status`, `/voice/config` GET + PUT) including
    validation + config.toml persistence.
  - `app.api.restart_handler` — the process-local
    "restart_required" flag and the 5-second auto-restart
    scheduler.

`voice_ws.py` is now a 30-line shim. The shared `router`
object lives in `ws_protocol.py` (the only module that
creates an `APIRouter()` instance); `voice_config_api.py`
imports and decorates the same instance, so `app/main.py`'s
`include_router(voice_ws.router, tags=["voice"])` continues
to work without changing the import.

Every symbol previously exported from this module is
re-exported from its new home (see `__all__` below).
"""
from __future__ import annotations

# Public re-exports — preserved 1:1 from the pre-P1.1 surface.
from app.api.restart_handler import (  # noqa: F401
    get_restart_required,
    schedule_restart_if_needed,
    set_restart_required,
)
from app.api.voice_config_api import (  # noqa: F401
    get_voice_config,
    put_voice_config,
    voice_status,
)
from app.api.ws_protocol import (  # noqa: F401
    AgentStreamCallback,
    get_agent_callback,
    router,
    set_agent_callback,
    set_responder,
)

# Internal helper that some tests reach into — keep accessible
# from the shim path so existing test imports don't break.
from app.api.ws_protocol import (  # noqa: F401
    _build_responder,
    _resolve_stream_iter,
    _send_json,
    _send_text_then_binary,
)


__all__ = [
    # Router — main.py does `include_router(voice_ws.router, tags=["voice"])`
    "router",
    # Agent callback API — called from main.py
    "AgentStreamCallback",
    "set_agent_callback",
    "get_agent_callback",
    "set_responder",
    # REST endpoints — called from tests + main.py auto-routing
    "voice_status",
    "get_voice_config",
    "put_voice_config",
    # Restart coordination — called from put_voice_config (now
    # internal) but kept public so tests can drive it directly.
    "get_restart_required",
    "set_restart_required",
    "schedule_restart_if_needed",
    # Internal helpers — re-exported so legacy imports keep working.
    "_build_responder",
    "_resolve_stream_iter",
    "_send_json",
    "_send_text_then_binary",
]
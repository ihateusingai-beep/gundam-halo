"""Agents — ReAct + simple conversational agents.

The decorator-based registry (`@AgentRegistry.register(...)`) only fires
when a module is *imported*. Without eager imports here, downstream code
that uses `AgentRegistry.contains("native_react")` (e.g. the
`/api/sessions` POST handler) would see an empty registry and raise
`Unknown agent type: native_react` on every send_message.

Eager import order also lets a future agent raise ImportError at app
start (not at first session create), so we surface dependency problems
upfront instead of in production traffic.
"""

from app.agents.system_prompt import build_system_prompt

# Eagerly import agent modules so their `@AgentRegistry.register(...)`
# decorators run. Keep both known agents here; add new ones below.
from app.agents import native_react  # noqa: E402, F401  -- registers "native_react"
from app.agents import simple  # noqa: E402, F401  -- registers "simple"

__all__ = ["build_system_prompt", "native_react", "simple"]

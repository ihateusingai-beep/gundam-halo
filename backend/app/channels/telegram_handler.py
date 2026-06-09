"""Telegram handler — wires incoming Telegram messages to the agent.

This module is what `ChannelManager.set_handler("telegram", ...)` should
be called with. It:

1. Maps each Telegram `chat_id` to a persistent session (via
   `TelegramSessionManager`).
2. Loads (or creates) an agent for that session.
3. Runs the agent on the user's text and returns its reply.
4. Persists the conversation so resumption works after a restart.

The handler is a no-op if the agent is unavailable — it returns a
canned apology rather than raising, so the Telegram channel stays
clean in dry-run mode (no real LLM) and in misconfigured deployments.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from app.channels.telegram_session import (
    TELEGRAM_PROJECT,
    TelegramSessionInfo,
    get_telegram_session_manager,
)
from app.core.config import get_config
from app.core.events import EventType, get_event_bus
from app.core.registry import AgentRegistry
from app.core.types import AgentContext, Message, Role
from app.tools.builder import default_tools

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Engine + agent cache (mirrors app.api.sessions but is channel-local)
# ---------------------------------------------------------------------------

_engine: Any = None
_agents: Dict[str, Any] = {}  # session_id -> BaseAgent


def _get_or_create_engine() -> Any:
    """Lazy-init the LLM engine. Mirrors sessions._get_or_create_engine."""
    global _engine
    if _engine is None:
        from app.engines.minimax import MiniMaxEngine

        cfg = get_config()
        _engine = MiniMaxEngine(
            api_key=cfg.llm.api_key,
            base_url=cfg.llm.base_url,
            model=cfg.llm.default_model,
        )
    return _engine


def _load_history(session_id: str) -> Optional[list[Message]]:
    """Load prior messages from the persistence layer, if any."""
    try:
        from app.projects import persistence

        return persistence.load_messages(TELEGRAM_PROJECT, session_id)
    except Exception as e:
        logger.warning(f"Could not load history for {session_id}: {e}")
        return None


def _save_history(session_id: str, messages: list[Message]) -> None:
    """Persist the full conversation to disk."""
    try:
        from app.projects import persistence

        persistence.save_messages(TELEGRAM_PROJECT, session_id, messages)
    except Exception as e:
        logger.warning(f"Could not save history for {session_id}: {e}")


def _get_or_create_agent(session_id: str) -> Any:
    """Cache an agent for the session. Loaded with prior history if any."""
    if session_id in _agents:
        return _agents[session_id]

    agent_type = "native_react"
    agent_cls = AgentRegistry.get(agent_type)
    if agent_cls is None:
        raise RuntimeError(f"agent type {agent_type!r} not registered")

    initial_messages = _load_history(session_id) or []
    agent = agent_cls(
        _get_or_create_engine(),
        get_config().llm.default_model,
        tools=default_tools(),
        initial_messages=initial_messages,
    )
    _agents[session_id] = agent
    logger.debug(
        f"Created Telegram agent for session {session_id} "
        f"(resumed with {len(initial_messages)} prior messages)"
    )
    return agent


# ---------------------------------------------------------------------------
# Public entry point — used as the ChannelHandler
# ---------------------------------------------------------------------------


async def telegram_handler(channel_id: str, sender: str, text: str) -> Optional[str]:
    """ChannelHandler: run *text* through the agent and return the reply.

    Parameters
    ----------
    channel_id:
        Always "telegram" today; accepted for compatibility with the
        generic ChannelHandler signature.
    sender:
        The Telegram `chat_id` as a string.
    text:
        The user's message text. Already de-prefixed for commands by
        `TelegramChannel`.

    Returns
    -------
    The agent's reply (or a fallback message on error). Returned as a
    string so the channel can `send()` it. `None` means "don't reply"
    (the channel treats it as silent).
    """
    session_manager = get_telegram_session_manager()
    info = session_manager.get_or_create(sender)

    # Mark the chat as active
    session_manager.touch(sender)

    # Resolve user identity (chat_id → display name) for the system prompt.
    # M7-Phase-2: this is what makes the agent know "I'm talking to Ken".
    from app.channels.identity import resolve_telegram_identity_cached

    try:
        cfg = get_config()
        identity = resolve_telegram_identity_cached(
            chat_id=sender,
            config_display_names=cfg.telegram.display_names,
            is_group=False,  # TODO: detect from update when handler is
                             # extended to receive full update payload
        )
    except Exception as e:
        logger.warning(f"Identity resolution failed for {sender}: {e}")
        identity = None
    display_name = identity.display_name if identity else None

    # Build / fetch agent
    try:
        agent = _get_or_create_agent(info.session_id)
    except Exception as e:
        logger.error(f"Failed to create agent for Telegram chat {sender}: {e}")
        return (
            "⚠ Gundam Halo is not fully configured. "
            "The LLM engine is unreachable. See server logs."
        )

    # Run the agent
    get_event_bus().publish(
        EventType.AGENT_TURN_START,
        {
            "session_id": info.session_id,
            "project": TELEGRAM_PROJECT,
            "agent_type": "native_react",
            "channel": "telegram",
            "user_message": text,
            "user_display_name": display_name,
        },
    )

    try:
        ctx = AgentContext(
            project_id=TELEGRAM_PROJECT,
            session_id=info.session_id,
            channel="telegram",
            user_id=sender,
            user_display_name=display_name,
        )
        result = await agent.run(text, context=ctx)
    except Exception as e:
        logger.error(f"Agent run error in Telegram session {info.session_id}: {e}")
        get_event_bus().publish(
            EventType.AGENT_TURN_END,
            {
                "session_id": info.session_id,
                "success": False,
                "error": str(e),
            },
        )
        return "⚠ Something went wrong while I was thinking. Try /new to reset."

    get_event_bus().publish(
        EventType.AGENT_TURN_END,
        {
            "session_id": info.session_id,
            "success": result.success,
            "tool_calls_made": result.tool_calls_made,
        },
    )

    # Persist the full conversation (initial_messages + this turn's
    # messages). result.messages includes both sides.
    if result.messages:
        _save_history(info.session_id, result.messages)

    if not result.success:
        return result.error or "⚠ The agent didn't return a final answer."

    reply = (result.output or "").strip()
    return reply or "✓ (no response text — see agent logs)"


# ---------------------------------------------------------------------------
# Command handlers — used by TelegramChannel before dispatching to the agent
# ---------------------------------------------------------------------------

HELP_TEXT = """\
🤖 *Gundam Halo* — Telegram control surface

*Commands*
/help   — Show this help
/new    — Reset the chat's session (start a fresh conversation)
/status — Show current session info
/echo   — Reply with the same text (debug)

*Anything else* gets routed to the agent, which has access to:
  • File I/O (read/write with policy)
  • Shell command execution (allowlist)
  • App launching (open <app>)
  • AppleScript / Accessibility API
  • Tailscale + clipboard + notifications

_Messages are scoped per chat. Your DMs and group chats each have \
their own session._"""

ECHO_TEXT = "🔊 echo"


async def handle_command(
    command: str,
    sender: str,
    session_manager: Optional[TelegramSessionManager] = None,
) -> Optional[str]:
    """Run a Telegram command. Returns the reply, or None if not a command.

    Recognized commands (case-insensitive, no prefix):
      help, new, status, echo

    The command word is passed WITHOUT the leading `/` (the channel
    strips it before calling).
    """
    cmd = command.strip().lower()
    if session_manager is None:
        session_manager = get_telegram_session_manager()

    if cmd == "help":
        return HELP_TEXT

    if cmd == "start":
        # /start is the conventional first-contact greeting. The
        # session is already created upstream by the channel
        # (see _handle_incoming's pre-dispatch ensure-session).
        return (
            "👋 Gundam Halo online. Send any text to start a conversation, "
            "or /help for available commands."
        )

    if cmd == "new":
        info = session_manager.reset(sender)
        # Drop the cached agent so the next message gets a fresh one
        if info is not None:
            _agents.pop(info.session_id, None)
        return "✓ Session reset. Next message starts a fresh conversation."

    if cmd == "status":
        info = session_manager.get(sender)
        if info is None:
            # Should not happen if channel did its pre-dispatch
            # ensure-session, but be defensive.
            return "ℹ No session yet for this chat. Send any message to start."
        from datetime import datetime

        started = datetime.utcfromtimestamp(info.started_at).isoformat() + "Z"
        last = datetime.utcfromtimestamp(info.last_active).isoformat() + "Z"
        return (
            f"📊 *Session status*\n"
            f"  session_id: `{info.session_id}`\n"
            f"  chat_id: `{info.chat_id}`\n"
            f"  started: `{started}`\n"
            f"  last_active: `{last}`\n"
            f"  message_count: `{info.message_count}`"
        )

    if cmd == "echo":
        return ECHO_TEXT

    # Not a recognized command — return None so the caller can
    # decide what to do (treat as a regular message, or error).
    return None


def reset_for_tests() -> None:
    """Clear the in-memory caches (engine + agent cache)."""
    global _engine
    _engine = None
    _agents.clear()


__all__ = [
    "telegram_handler",
    "handle_command",
    "HELP_TEXT",
    "reset_for_tests",
]

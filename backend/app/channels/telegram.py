"""Telegram channel — uses `python-telegram-bot` v22+.

Two modes:
- **real**: connects to Telegram via bot token, long-polls for messages
- **dry-run**: simulates message receipt (for development / tests / no token)

Configured via `cfg.telegram.bot_token`. If empty → dry-run mode.

Message flow (M4+):
1. Inbound message → auth check (whitelisted chat_ids)
2. If it starts with `cfg.telegram.command_prefix` (`/` by default) →
   strip the prefix and run `handle_command()`.
3. Otherwise → dispatch to the channel handler (set via
   `ChannelManager.set_handler("telegram", telegram_handler)`).
4. If a reply is produced, send it back to the user.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from app.channels.base import BaseChannel, ChannelHandler
from app.channels.telegram_handler import handle_command
from app.core.config import get_config
from app.core.registry import ChannelRegistry
from app.core.events import EventType, get_event_bus

logger = logging.getLogger(__name__)


@ChannelRegistry.register("telegram")
class TelegramChannel(BaseChannel):
    """Native Telegram Bot API adapter.

    Real mode: uses python-telegram-bot's ApplicationBuilder + polling.
    Dry-run mode: no connection, send() prints to log, message dispatch
    only happens via test injection or simulated events.
    """

    channel_id = "telegram"

    def __init__(self, handler: Optional[ChannelHandler] = None) -> None:
        super().__init__(handler=handler)
        cfg = get_config().telegram
        self._bot_token = cfg.bot_token
        self._allowed_chat_ids = set(cfg.allowed_chat_ids)
        self._command_prefix = cfg.command_prefix
        self._application: Any = None  # telegram.ext.Application
        self._mode = "real" if self._bot_token else "dry-run"

        if self._mode == "dry-run":
            logger.info(
                "Telegram channel: DRY-RUN mode (no bot token). "
                "Set GUNDAM_HALO_TG_TOKEN to enable real mode."
            )

    async def start(self) -> None:
        if self._running:
            return

        if self._mode == "dry-run":
            logger.info("Telegram channel started (DRY-RUN)")
            self._running = True
            return

        # Real mode: start polling
        try:
            from telegram.ext import ApplicationBuilder

            self._application = (
                ApplicationBuilder()
                .token(self._bot_token)
                .build()
            )

            # Register message handler
            self._application.add_handler(
                __import__("telegram.ext", fromlist=["MessageHandler"]).MessageHandler(
                    __import__("telegram.ext", fromlist=["filters"]).filters.TEXT
                    & ~__import__("telegram.ext", fromlist=["filters"]).filters.COMMAND,
                    self._on_telegram_message,
                )
            )
            self._application.add_handler(
                __import__("telegram.ext", fromlist=["CommandHandler"]).CommandHandler(
                    "start", self._on_telegram_command
                )
            )

            # Initialize and start
            await self._application.initialize()
            await self._application.start()
            await self._application.updater.start_polling()

            logger.info(f"Telegram channel connected (allowed chat_ids: {self._allowed_chat_ids})")
            self._running = True
        except Exception as e:
            logger.error(f"Failed to start Telegram channel: {e}")
            self._running = False
            raise

    async def stop(self) -> None:
        if not self._running:
            return
        if self._application is not None:
            try:
                await self._application.updater.stop_polling()
                await self._application.stop()
                await self._application.shutdown()
            except Exception as e:
                logger.warning(f"Error stopping Telegram channel: {e}")
            self._application = None
        self._running = False
        logger.info("Telegram channel stopped")

    async def send(self, recipient: str, content: str) -> bool:
        """Send a message to a Telegram chat.

        In dry-run mode: logs the message. In real mode: calls the
        Telegram Bot API via the bot object.
        """
        if self._mode == "dry-run":
            logger.info(f"[TG DRY-RUN] → {recipient}: {content[:200]}")
            return True

        if self._application is None:
            logger.warning("Cannot send: Telegram channel not started")
            return False

        try:
            chat_id = int(recipient)
            # Use the bot object to send
            await self._application.bot.send_message(chat_id=chat_id, text=content)
            get_event_bus().publish(
                EventType.CHANNEL_MESSAGE_SENT,
                {"channel": "telegram", "recipient": recipient, "length": len(content)},
            )
            return True
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return False

    # ------------------------------------------------------------------
    # Internal: real-mode message handlers
    # ------------------------------------------------------------------

    async def _on_telegram_message(self, update: Any, context: Any) -> None:
        """Handle an incoming Telegram message (real mode)."""
        if not update.message or not update.message.text:
            return
        chat_id = str(update.message.chat_id)
        text = update.message.text

        await self._handle_incoming(chat_id, text, sender_name=update.message.from_user.first_name or "user")

    async def _on_telegram_command(self, update: Any, context: Any) -> None:
        """Handle /start command."""
        chat_id = str(update.message.chat_id)
        await self.send(chat_id, "Gundam Halo online. Send a message to start, or /help for commands.")

    # ------------------------------------------------------------------
    # Common: dispatch + auth
    # ------------------------------------------------------------------

    async def _handle_incoming(
        self, chat_id: str, text: str, sender_name: str = ""
    ) -> None:
        """Authenticate + dispatch an incoming message.

        Order:
        1. Auth: chat_id must be in `allowed_chat_ids` (if set).
        2. Ensure a session exists for this chat (so `/status`,
           `/new`, etc. work even on the very first message).
        3. If text starts with the command prefix, run a command.
        4. Otherwise dispatch to the registered handler.
        5. Send any reply back to the user.
        """
        # Auth: check chat_id is in allowed list
        if self._allowed_chat_ids and int(chat_id) not in self._allowed_chat_ids:
            logger.warning(
                f"Refused Telegram message from non-whitelisted chat_id: {chat_id}"
            )
            return

        get_event_bus().publish(
            EventType.CHANNEL_MESSAGE_RECEIVED,
            {"channel": "telegram", "sender": chat_id, "length": len(text)},
        )

        # Ensure a session exists for this chat BEFORE command dispatch
        # — so `/status` works on first contact, `/new` always
        # succeeds, and downstream tools that look up the session by
        # chat_id see a real entry.
        from app.channels.telegram_session import get_telegram_session_manager
        try:
            get_telegram_session_manager().get_or_create(chat_id)
        except Exception as e:
            logger.warning(f"Could not ensure session for {chat_id}: {e}")

        # Command interception (M4+)
        prefix = self._command_prefix or "/"
        stripped = text.strip()
        if stripped.startswith(prefix):
            command_word = stripped[len(prefix):].split()[0] if stripped[len(prefix):] else ""
            command_response = await handle_command(command_word, chat_id)
            if command_response is not None:
                await self.send(chat_id, command_response)
                return
            # Unrecognized command — fall through to handler so the
            # agent can decide what to do (e.g. tell the user the
            # command doesn't exist).

        # Dispatch to handler (which routes to the agent)
        response = await self._dispatch_message(chat_id, text)
        if response:
            await self.send(chat_id, response)


__all__ = ["TelegramChannel"]

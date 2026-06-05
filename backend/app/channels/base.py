"""Channel adapters — base, telegram, manager.

A channel is a long-running adapter that receives user messages from
outside the web (Telegram, Signal, etc.) and routes them into the agent
pipeline. Each channel implements the BaseChannel ABC and registers
itself in the ChannelRegistry.

v1: only Telegram.
v2: Signal (TBD).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Awaitable, Callable, Optional


# Type alias for message handlers
# A channel handler takes (channel_id, sender_id, text) and returns the
# agent's reply (or None if the channel is just emitting events).
ChannelHandler = Callable[[str, str, str], Awaitable[Optional[str]]]


class BaseChannel(ABC):
    """Abstract base for all Gundam Halo channels.

    Lifecycle:
        channel = TelegramChannel(config)
        await channel.start()        # connect, begin listening
        # ... user messages come in via _dispatch_message() ...
        await channel.stop()         # disconnect

    Concrete channels must:
    - Set `channel_id` (e.g. "telegram")
    - Implement `start()` and `stop()` (async)
    - Implement `send()` (send message to user)
    - Register themselves in ChannelRegistry (decorator)
    """

    channel_id: str

    def __init__(self, handler: Optional[ChannelHandler] = None) -> None:
        self._handler = handler
        self._running = False

    @abstractmethod
    async def start(self) -> None:
        """Connect to the channel and start listening."""

    @abstractmethod
    async def stop(self) -> None:
        """Disconnect and stop listening."""

    @abstractmethod
    async def send(self, recipient: str, content: str) -> bool:
        """Send a message to a specific recipient (chat_id, phone, etc.)."""

    async def _dispatch_message(
        self, sender: str, text: str, sender_name: str = ""
    ) -> Optional[str]:
        """Called by the channel when a message arrives. Routes through the handler."""
        if self._handler is None:
            return None
        return await self._handler(self.channel_id, sender, text)

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def mode(self) -> str:
        """Return "real" or "dry-run" for status display."""
        return getattr(self, "_mode", "real")


__all__ = ["BaseChannel", "ChannelHandler"]

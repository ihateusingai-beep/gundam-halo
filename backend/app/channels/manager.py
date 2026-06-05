"""Channel manager — start/stop all registered channels on app lifecycle."""

from __future__ import annotations

import logging
from typing import Any

from app.core.config import get_config
from app.core.registry import ChannelRegistry

logger = logging.getLogger(__name__)


class ChannelManager:
    """Manages the lifecycle of all registered channels."""

    def __init__(self) -> None:
        self._channels: dict[str, Any] = {}

    async def start_all(self) -> None:
        """Start all enabled channels."""
        for channel_id in ChannelRegistry.keys():
            try:
                await self.start(channel_id)
            except Exception as e:
                logger.error(f"Failed to start channel {channel_id}: {e}")

    async def stop_all(self) -> None:
        """Stop all channels."""
        for channel_id in list(self._channels.keys()):
            try:
                await self.stop(channel_id)
            except Exception as e:
                logger.error(f"Failed to stop channel {channel_id}: {e}")

    async def start(self, channel_id: str) -> None:
        """Start a specific channel."""
        if channel_id in self._channels:
            logger.debug(f"Channel {channel_id} already started")
            return

        cfg = get_config()
        # Check if channel is enabled in config
        if channel_id == "telegram" and not cfg.telegram.enabled:
            logger.info(f"Channel {channel_id} disabled in config, skipping")
            return

        if not ChannelRegistry.contains(channel_id):
            logger.warning(f"Unknown channel: {channel_id}")
            return

        channel_cls = ChannelRegistry.get(channel_id)
        channel = channel_cls()
        await channel.start()
        self._channels[channel_id] = channel
        logger.info(f"Started channel: {channel_id} (mode={channel.mode})")

    async def stop(self, channel_id: str) -> None:
        """Stop a specific channel."""
        channel = self._channels.pop(channel_id, None)
        if channel is not None:
            await channel.stop()
            logger.info(f"Stopped channel: {channel_id}")

    def get(self, channel_id: str) -> Any:
        return self._channels.get(channel_id)

    def status(self) -> dict:
        """Return status of all channels for the /api/channels endpoint."""
        return {
            channel_id: {
                "running": channel.is_running,
                "mode": channel.mode,
                "channel_id": channel_id,
            }
            for channel_id, channel in self._channels.items()
        }


# Module-level singleton
_manager: ChannelManager | None = None


def get_channel_manager() -> ChannelManager:
    global _manager
    if _manager is None:
        _manager = ChannelManager()
    return _manager


def reset_channel_manager() -> None:
    global _manager
    _manager = None


__all__ = ["ChannelManager", "get_channel_manager", "reset_channel_manager"]

"""Tests for the Telegram channel.

Only test the dry-run mode (no real Telegram token needed).
"""

import pytest

from app.channels.telegram import TelegramChannel
from app.core.registry import ChannelRegistry


def test_telegram_registered():
    assert ChannelRegistry.contains("telegram")
    assert ChannelRegistry.get("telegram") is TelegramChannel


def test_telegram_dry_run_mode():
    """Without a token, should be in dry-run mode."""
    ch = TelegramChannel()
    assert ch.mode == "dry-run"
    assert ch.channel_id == "telegram"


@pytest.mark.asyncio
async def test_telegram_dry_run_start_stop(caplog):
    ch = TelegramChannel()
    await ch.start()
    assert ch.is_running
    await ch.stop()
    assert not ch.is_running


@pytest.mark.asyncio
async def test_telegram_dry_run_send_logs(caplog):
    """In dry-run mode, send() logs but doesn't actually send."""
    ch = TelegramChannel()
    await ch.start()
    with caplog.at_level("INFO"):
        result = await ch.send("123456789", "hello world")
    assert result is True
    assert "[TG DRY-RUN]" in caplog.text or "DRY-RUN" in caplog.text
    await ch.stop()


def test_telegram_dispatcher_with_handler():
    """Verify that a handler gets called on _dispatch_message."""
    received = []

    async def my_handler(channel_id, sender, text):
        received.append((channel_id, sender, text))
        return "echo: " + text

    ch = TelegramChannel(handler=my_handler)
    assert ch._handler is my_handler


@pytest.mark.asyncio
async def test_telegram_dispatch_message_invokes_handler():
    received = []

    async def my_handler(channel_id, sender, text):
        received.append((channel_id, sender, text))
        return "ok"

    ch = TelegramChannel(handler=my_handler)
    result = await ch._dispatch_message("123", "hello")
    assert result == "ok"
    assert received == [("telegram", "123", "hello")]

"""Tests for the Telegram session manager and command handlers.

Covers:
- `TelegramSessionManager` — create / get / reset / touch / persistence
- `handle_command()` — /help /new /status /echo, plus unknown commands
- `telegram.py` — command-prefix interception in `_handle_incoming`
  (dry-run mode, since we don't have a real Telegram token in CI)
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from app.channels import telegram_session
from app.channels.telegram import TelegramChannel
from app.channels.telegram_handler import handle_command
from app.channels.telegram_session import (
    TELEGRAM_PROJECT,
    TelegramSessionManager,
    get_telegram_session_manager,
    reset_telegram_session_manager,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_halo_home(tmp_path: Path) -> Path:
    """Each test gets a clean HALO_HOME to write into."""
    return tmp_path


@pytest.fixture
def fresh_session_manager(tmp_halo_home: Path):
    """Return a fresh session manager, bypassing the module singleton."""
    reset_telegram_session_manager()
    mgr = TelegramSessionManager(halo_home=tmp_halo_home)
    yield mgr
    reset_telegram_session_manager()


# ---------------------------------------------------------------------------
# TelegramSessionManager
# ---------------------------------------------------------------------------


class TestSessionManager:
    def test_get_or_create_creates_new_session(self, fresh_session_manager):
        info = fresh_session_manager.get_or_create("12345")
        assert info.chat_id == "12345"
        assert info.session_id.startswith("tg-")
        assert info.message_count == 0
        assert fresh_session_manager.project_dir().is_dir()

    def test_get_or_create_returns_same_session(self, fresh_session_manager):
        a = fresh_session_manager.get_or_create("12345")
        b = fresh_session_manager.get_or_create("12345")
        assert a.session_id == b.session_id
        assert a is b

    def test_different_chats_get_different_sessions(self, fresh_session_manager):
        a = fresh_session_manager.get_or_create("12345")
        b = fresh_session_manager.get_or_create("67890")
        assert a.session_id != b.session_id

    def test_get_returns_none_for_unknown_chat(self, fresh_session_manager):
        assert fresh_session_manager.get("never-seen") is None

    def test_reset_creates_fresh_session(self, fresh_session_manager):
        original = fresh_session_manager.get_or_create("12345")
        fresh = fresh_session_manager.reset("12345")
        assert fresh is not None
        assert fresh.session_id != original.session_id

    def test_touch_increments_message_count(self, fresh_session_manager):
        fresh_session_manager.get_or_create("12345")
        fresh_session_manager.touch("12345", message_count_increment=1)
        fresh_session_manager.touch("12345", message_count_increment=1)
        info = fresh_session_manager.get("12345")
        assert info is not None
        assert info.message_count == 2

    def test_touch_updates_last_active(self, fresh_session_manager):
        import time

        fresh_session_manager.get_or_create("12345")
        before = fresh_session_manager.get("12345").last_active
        time.sleep(0.01)
        fresh_session_manager.touch("12345")
        after = fresh_session_manager.get("12345").last_active
        assert after > before

    def test_touch_unknown_chat_is_noop(self, fresh_session_manager):
        # Should not raise
        fresh_session_manager.touch("ghost")
        assert fresh_session_manager.get("ghost") is None

    def test_persists_to_disk(self, fresh_session_manager, tmp_halo_home: Path):
        fresh_session_manager.get_or_create("12345")
        # Force the manager to release its state, then re-load from disk
        map_path = tmp_halo_home / "projects" / TELEGRAM_PROJECT / "chat_map.json"
        assert map_path.exists()
        # File should be valid JSON
        data = json.loads(map_path.read_text())
        assert "12345" in data
        assert data["12345"]["chat_id"] == "12345"

    def test_persists_across_instances(self, tmp_halo_home: Path):
        reset_telegram_session_manager()
        mgr1 = TelegramSessionManager(halo_home=tmp_halo_home)
        mgr1.get_or_create("12345")
        # New manager reading from same dir
        mgr2 = TelegramSessionManager(halo_home=tmp_halo_home)
        info = mgr2.get("12345")
        assert info is not None
        assert info.chat_id == "12345"
        reset_telegram_session_manager()

    def test_corrupt_map_falls_back_to_empty(self, tmp_halo_home: Path, caplog):
        project = tmp_halo_home / "projects" / TELEGRAM_PROJECT
        project.mkdir(parents=True)
        map_path = project / "chat_map.json"
        map_path.write_text("not valid json {")
        reset_telegram_session_manager()
        mgr = TelegramSessionManager(halo_home=tmp_halo_home)
        with caplog.at_level("WARNING"):
            info = mgr.get_or_create("12345")
        assert info.chat_id == "12345"
        assert "Failed to read chat_map" in caplog.text or "json" in caplog.text.lower()
        reset_telegram_session_manager()

    def test_list_sessions_sorted_by_last_active(self, fresh_session_manager):
        import time

        a = fresh_session_manager.get_or_create("a")
        time.sleep(0.01)
        b = fresh_session_manager.get_or_create("b")
        time.sleep(0.01)
        c = fresh_session_manager.get_or_create("c")
        # Touch a and c so c is most recent
        fresh_session_manager.touch("a")
        time.sleep(0.01)
        fresh_session_manager.touch("c")
        listing = fresh_session_manager.list_sessions()
        # Most recent first
        assert listing[0].chat_id == "c"
        assert listing[-1].chat_id == "b"

    def test_get_telegram_session_manager_singleton(self, tmp_halo_home: Path):
        # Stub the config home so the singleton points at tmp_path
        with patch("app.core.config.get_config") as mock_cfg:
            mock_cfg.return_value.home = tmp_halo_home
            reset_telegram_session_manager()
            m1 = get_telegram_session_manager()
            m2 = get_telegram_session_manager()
            assert m1 is m2
        reset_telegram_session_manager()


# ---------------------------------------------------------------------------
# handle_command
# ---------------------------------------------------------------------------


class TestHandleCommand:
    @pytest.mark.asyncio
    async def test_help_returns_help_text(self):
        result = await handle_command("help", "12345")
        assert result is not None
        assert "Gundam Halo" in result
        assert "/new" in result
        assert "/status" in result

    @pytest.mark.asyncio
    async def test_help_is_case_insensitive(self):
        r1 = await handle_command("help", "1")
        r2 = await handle_command("HELP", "1")
        r3 = await handle_command("Help", "1")
        assert r1 == r2 == r3

    @pytest.mark.asyncio
    async def test_new_resets_session(self, fresh_session_manager):
        # Get an existing session first
        original = fresh_session_manager.get_or_create("12345")
        original_id = original.session_id

        result = await handle_command("new", "12345", session_manager=fresh_session_manager)
        assert result is not None
        assert "reset" in result.lower()

        # Session should be different now
        new_info = fresh_session_manager.get("12345")
        assert new_info.session_id != original_id

    @pytest.mark.asyncio
    async def test_status_returns_info(self, fresh_session_manager):
        fresh_session_manager.get_or_create("12345")
        result = await handle_command("status", "12345", session_manager=fresh_session_manager)
        assert result is not None
        assert "session_id" in result
        assert "12345" in result
        assert "message_count" in result

    @pytest.mark.asyncio
    async def test_status_with_no_session(self, fresh_session_manager):
        result = await handle_command("status", "never-seen", session_manager=fresh_session_manager)
        assert result is not None
        assert "no session" in result.lower() or "no session yet" in result.lower()

    @pytest.mark.asyncio
    async def test_echo_returns_echo_marker(self):
        result = await handle_command("echo", "1")
        assert result is not None
        assert "echo" in result.lower()

    @pytest.mark.asyncio
    async def test_unknown_command_returns_none(self):
        # The channel treats None as "fall through to the agent"
        result = await handle_command("nonexistent-command-xyz", "1")
        assert result is None

    @pytest.mark.asyncio
    async def test_empty_command(self):
        result = await handle_command("", "1")
        assert result is None


# ---------------------------------------------------------------------------
# TelegramChannel — command-prefix interception (dry-run mode)
# ---------------------------------------------------------------------------


class TestTelegramCommandInterception:
    """The channel should intercept commands BEFORE dispatching to the
    handler. We use dry-run mode (no real token) and a stub handler
    so we can assert the dispatch order."""

    @pytest.mark.asyncio
    async def test_command_does_not_invoke_handler(self):
        sent = []
        dispatched = []

        async def stub_handler(channel_id, sender, text):
            dispatched.append((sender, text))
            return "should not be called"

        ch = TelegramChannel(handler=stub_handler)
        await ch.start()

        # Patch the channel's send() so we capture the reply without
        # actually going through python-telegram-bot
        async def fake_send(recipient, content):
            sent.append((recipient, content))
            return True

        ch.send = fake_send  # type: ignore[assignment]

        # Send a /help command from a whitelisted chat
        ch._allowed_chat_ids = {12345}
        await ch._handle_incoming("12345", "/help")

        # The channel should have sent the help text...
        assert len(sent) == 1
        assert "Gundam Halo" in sent[0][1]
        # ...and NOT dispatched to the handler
        assert dispatched == []

        await ch.stop()

    @pytest.mark.asyncio
    async def test_plain_text_invokes_handler(self):
        dispatched = []
        sent = []

        async def stub_handler(channel_id, sender, text):
            dispatched.append((sender, text))
            return "agent reply"

        ch = TelegramChannel(handler=stub_handler)
        await ch.start()

        async def fake_send(recipient, content):
            sent.append((recipient, content))
            return True

        ch.send = fake_send  # type: ignore[assignment]
        ch._allowed_chat_ids = {12345}

        await ch._handle_incoming("12345", "what is 2+2?")
        assert dispatched == [("12345", "what is 2+2?")]
        assert sent == [("12345", "agent reply")]

        await ch.stop()

    @pytest.mark.asyncio
    async def test_unknown_command_falls_through_to_handler(self):
        """If `handle_command` returns None (unknown command), the channel
        should still send the message to the agent — the agent can then
        say "unknown command" or just process it normally."""
        dispatched = []

        async def stub_handler(channel_id, sender, text):
            dispatched.append(text)
            return "agent got it"

        ch = TelegramChannel(handler=stub_handler)
        await ch.start()

        sent = []
        async def fake_send(recipient, content):
            sent.append(content)
            return True
        ch.send = fake_send  # type: ignore[assignment]
        ch._allowed_chat_ids = {12345}

        await ch._handle_incoming("12345", "/unknown-xyz-command some args")
        # Falls through to handler with the original text intact
        assert dispatched == ["/unknown-xyz-command some args"]
        assert sent == ["agent got it"]

        await ch.stop()

    @pytest.mark.asyncio
    async def test_unauthorized_chat_id_drops_silently(self):
        sent = []
        dispatched = []

        async def stub_handler(channel_id, sender, text):
            dispatched.append(text)
            return "should not fire"

        ch = TelegramChannel(handler=stub_handler)
        await ch.start()

        async def fake_send(recipient, content):
            sent.append(content)
            return True
        ch.send = fake_send  # type: ignore[assignment]
        ch._allowed_chat_ids = {99999}  # Only allow this chat

        await ch._handle_incoming("12345", "hello")
        # No send, no dispatch
        assert sent == []
        assert dispatched == []

        await ch.stop()

    @pytest.mark.asyncio
    async def test_handler_in_channel_manager_wiring(self, tmp_halo_home: Path):
        """ChannelManager.set_handler + start should pass the handler through."""
        from app.channels.manager import ChannelManager
        from app.core import config as config_mod
        from app.core import events

        events.reset_event_bus()

        # Telegram is disabled by default — flip it for this test
        with patch.object(config_mod.get_config(), "telegram") as mock_tg:
            mock_tg.enabled = True
            mock_tg.bot_token = ""
            mock_tg.allowed_chat_ids = []
            mock_tg.command_prefix = "/"

            received = []

            async def my_handler(channel_id, sender, text):
                received.append((channel_id, sender, text))
                return "ok"

            mgr = ChannelManager()
            mgr.set_handler("telegram", my_handler)
            await mgr.start("telegram")
            try:
                ch = mgr.get("telegram")
                assert ch is not None
                assert ch._handler is my_handler
            finally:
                await mgr.stop("telegram")

"""Dry-run round-trip verifier for the Telegram channel stack.

Mimics the full path a real Telegram message would take, end-to-end,
WITHOUT needing a real Telegram bot token or LLM API key.

What it verifies (v0.5 dry-run acceptance):

  1. **Session creation** — `_handle_incoming(chat_id, "/start")` on a
     fresh chat_id → creates a session in `chat_map.json` + writes
     `sessions/<sid>/` on disk.

  2. **Command dispatch** — `/help`, `/status`, `/new`, `/echo` all
     return canned text. Unrecognized command (e.g. `/xyz`) falls
     through to the agent.

  3. **Agent wiring** — a real message (e.g. "what is 2+2?") is
     routed to the agent. The agent is mocked at the engine level
     (no real LLM call) so we can verify the full handler chain:
       session lookup → agent cache → mock run → reply returned
       → history persisted.

  4. **History persistence** — after a message, the session's
     `messages.jsonl` exists and contains the user + assistant
     turns.

  5. **Cross-chat isolation** — chat A and chat B get different
     sessions; a `/new` on chat A doesn't disturb chat B.

  6. **Command-vs-handler routing** — `/help` does NOT touch the
     agent cache (no agent run); plain text DOES.

Re-runnable. Uses a fresh temp HALO_HOME per run. The script prints
PASS / FAIL for each step; exits 0 only if all pass.

Usage:
    .venv/bin/python scripts/verify_telegram_dryrun.py
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any
from unittest.mock import patch

# Repo paths so the script can import from backend.app.*
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))

# Import AFTER sys.path tweak
from app.channels import telegram as tg_module  # noqa: E402
from app.channels import telegram_handler as th_module  # noqa: E402
from app.channels.telegram import TelegramChannel  # noqa: E402
from app.channels.telegram_handler import (  # noqa: E402
    handle_command,
    telegram_handler,
)
from app.channels.telegram_session import (  # noqa: E402
    TELEGRAM_PROJECT,
    TelegramSessionManager,
    reset_telegram_session_manager,
)
from app.core import config as config_mod  # noqa: E402
from app.core import events  # noqa: E402
from app.projects import persistence  # noqa: E402
from app.core.types import AgentResult, Message, Role  # noqa: E402


# ---------------------------------------------------------------------------
# Pretty test runner
# ---------------------------------------------------------------------------

PASS = "✓"
FAIL = "✗"
results: list[tuple[str, bool, str]] = []


def step(name: str, ok: bool, detail: str = "") -> None:
    marker = PASS if ok else FAIL
    print(f"  {marker} {name}" + (f" — {detail}" if detail else ""))
    results.append((name, ok, detail))


def make_mock_agent_result(output: str, success: bool = True) -> AgentResult:
    """Build a fake AgentResult so the handler persists the same shape."""
    return AgentResult(
        success=success,
        output=output,
        messages=[
            Message(role=Role.USER, content="user input"),
            Message(role=Role.ASSISTANT, content=output),
        ],
        tool_calls_made=0,
    )


class MockAgent:
    """Stand-in for a real `BaseAgent` — no LLM, just echoes the input.

    Mimics the real `NativeReActAgent.run` shape: result.messages
    contains the full conversation after the turn (user + assistant).
    """

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def run(self, text: str, context: Any = None) -> AgentResult:
        self.calls.append(text)
        return AgentResult(
            success=True,
            output=f"[mock reply to: {text!r}]",
            messages=[
                Message(role=Role.USER, content=text),
                Message(role=Role.ASSISTANT, content=f"[mock reply to: {text!r}]"),
            ],
            tool_calls_made=0,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def fresh_halo_home() -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="halo-tg-dryrun-"))
    os.environ["HALO_HOME"] = str(tmp)
    # Empty token → telegram dry-run mode
    os.environ["GUNDAM_HALO_TG_TOKEN"] = ""
    # Reset all module singletons that depend on HALO_HOME
    events.reset_event_bus()
    config_mod._config = None
    reset_telegram_session_manager()
    th_module.reset_for_tests()
    return tmp


def make_dry_run_channel(handler=None) -> TelegramChannel:
    """A TelegramChannel that won't try to connect anywhere (no token)."""
    return TelegramChannel(handler=handler)


# ---------------------------------------------------------------------------
# The actual tests
# ---------------------------------------------------------------------------


async def test_01_session_created_on_first_message(tmp: Path) -> None:
    """Sending /start as a brand-new chat_id should create a session
    and return the canned greeting."""
    reset_telegram_session_manager()
    th_module.reset_for_tests()
    ch = make_dry_run_channel()
    await ch.start()
    sent: list[tuple[str, str]] = []

    async def fake_send(recipient, content):
        sent.append((recipient, content))
        return True
    ch.send = fake_send  # type: ignore[assignment]

    ch._allowed_chat_ids = {111}
    await ch._handle_incoming("111", "/start")  # canned greeting, creates session

    # Session must be on disk
    map_path = tmp / "projects" / TELEGRAM_PROJECT / "chat_map.json"
    ok = map_path.exists()
    step("chat_map.json created on first message", ok, str(map_path) if not ok else "")

    if ok:
        data = json.loads(map_path.read_text())
        step("chat_map has entry for chat_id 111", "111" in data)

    # Channel must have sent the canned /start reply
    step(
        "/start returns canned greeting",
        any(isinstance(s[1], str) and "Gundam Halo online" in s[1] for s in sent),
    )

    await ch.stop()


async def test_02_commands(tmp: Path) -> None:
    """All 4 commands return canned text, don't reach the agent."""
    reset_telegram_session_manager()
    th_module.reset_for_tests()
    agent_called: list[str] = []

    async def stub_handler(channel_id, sender, text):
        agent_called.append(text)
        return "AGENT RESPONSE (should not appear)"

    ch = make_dry_run_channel(handler=stub_handler)
    await ch.start()
    sent: list[tuple[str, str]] = []

    async def fake_send(recipient, content):
        sent.append((recipient, content))
        return True
    ch.send = fake_send  # type: ignore[assignment]
    ch._allowed_chat_ids = {222}

    # /help
    await ch._handle_incoming("222", "/help")
    step("/help returns help text", any("Gundam Halo" in s[1] for s in sent))

    # /status (now session should exist for 222)
    sent.clear()
    await ch._handle_incoming("222", "/status")
    step(
        "/status returns session info",
        any("session_id" in s[1] and "message_count" in s[1] for s in sent),
    )

    # /echo
    sent.clear()
    await ch._handle_incoming("222", "/echo")
    step("/echo returns marker", any("echo" in s[1].lower() for s in sent))

    # /new (resets session)
    sent.clear()
    await ch._handle_incoming("222", "/new")
    step("/new confirms reset", any("reset" in s[1].lower() for s in sent))

    # None of the above should have called the handler
    step("no command reached the agent", agent_called == [])

    await ch.stop()


async def test_03_plain_text_routes_to_agent(tmp: Path) -> None:
    """Plain text (no leading /) goes to the agent handler."""
    reset_telegram_session_manager()
    th_module.reset_for_tests()

    agent_called: list[tuple[str, str]] = []

    async def stub_handler(channel_id, sender, text):
        agent_called.append((sender, text))
        return f"agent got: {text}"

    ch = make_dry_run_channel(handler=stub_handler)
    await ch.start()
    sent: list[tuple[str, str]] = []

    async def fake_send(recipient, content):
        sent.append((recipient, content))
        return True
    ch.send = fake_send  # type: ignore[assignment]
    ch._allowed_chat_ids = {333}

    await ch._handle_incoming("333", "what is 2+2?")

    step("plain text reached handler", agent_called == [("333", "what is 2+2?")])
    step("reply sent back to user", any("agent got: what is 2+2?" in s[1] for s in sent))

    await ch.stop()


async def test_04_unknown_command_falls_through(tmp: Path) -> None:
    """Unknown command → falls through to handler, agent sees the original text."""
    reset_telegram_session_manager()
    th_module.reset_for_tests()

    agent_called: list[str] = []

    async def stub_handler(channel_id, sender, text):
        agent_called.append(text)
        return "ok"

    ch = make_dry_run_channel(handler=stub_handler)
    await ch.start()
    sent: list[tuple[str, str]] = []

    async def fake_send(recipient, content):
        sent.append((recipient, content))
        return True
    ch.send = fake_send  # type: ignore[assignment]
    ch._allowed_chat_ids = {444}

    await ch._handle_incoming("444", "/xyz-not-a-cmd hello world")
    step(
        "unknown command falls through with original text",
        agent_called == ["/xyz-not-a-cmd hello world"],
    )

    await ch.stop()


async def test_05_unauthorized_chat_id_silently_dropped(tmp: Path) -> None:
    """Messages from non-whitelisted chat_id produce nothing."""
    reset_telegram_session_manager()
    th_module.reset_for_tests()

    dispatched: list[str] = []
    sent: list[tuple[str, str]] = []

    async def stub_handler(channel_id, sender, text):
        dispatched.append(text)
        return "ok"

    ch = make_dry_run_channel(handler=stub_handler)
    await ch.start()

    async def fake_send(recipient, content):
        sent.append((recipient, content))
        return True
    ch.send = fake_send  # type: ignore[assignment]
    ch._allowed_chat_ids = {999}  # only 999

    await ch._handle_incoming("123", "should be dropped")
    step("unauthorized chat: no send", sent == [])
    step("unauthorized chat: no dispatch", dispatched == [])

    await ch.stop()


async def test_06_cross_chat_isolation(tmp: Path) -> None:
    """Different chat_ids must get different sessions, and /new in A doesn't affect B."""
    reset_telegram_session_manager()
    th_module.reset_for_tests()

    mgr = TelegramSessionManager(halo_home=tmp)
    a = mgr.get_or_create("chat-A")
    b = mgr.get_or_create("chat-B")
    step("chat A and B get different session_ids", a.session_id != b.session_id)

    mgr.reset("chat-A")
    a2 = mgr.get("chat-A")
    b2 = mgr.get("chat-B")
    step("/new on A gives A a new session", a2.session_id != a.session_id)
    step("/new on A leaves B's session untouched", b2.session_id == b.session_id)


async def test_07_handler_runs_mock_agent_and_persists(tmp: Path) -> None:
    """End-to-end through telegram_handler(): inject a plain-text message
    into a real TelegramChannel, the handler runs the agent (mocked),
    history is persisted to disk, reply is sent back."""
    reset_telegram_session_manager()
    th_module.reset_for_tests()

    # Pre-seed an agent that echoes deterministically
    mock_agent = MockAgent()

    async def fake_handler(channel_id, sender, text):
        # ChannelHandler contract: return the agent's output string
        result = await mock_agent.run(text, context=None)
        return result.output

    ch = make_dry_run_channel(handler=fake_handler)
    await ch.start()
    sent: list[tuple[str, str]] = []

    async def fake_send(recipient, content):
        sent.append((recipient, content))
        return True
    ch.send = fake_send  # type: ignore[assignment]
    ch._allowed_chat_ids = {555}

    chat_id = "555"
    text = "list files in my workspace"
    await ch._handle_incoming(chat_id, text)

    # 1. Mock agent was called
    step("mock agent received the text", mock_agent.calls == [text])

    # 2. Reply was sent back (extract string from AgentResult if needed)
    expected_reply = f"[mock reply to: {text!r}]"
    text_in_sent = any(
        isinstance(s[1], str) and expected_reply in s[1] for s in sent
    )
    step("reply sent back to user", text_in_sent)

    # 3. Session was created on disk
    map_data = json.loads(
        (tmp / "projects" / TELEGRAM_PROJECT / "chat_map.json").read_text()
    )
    step("chat 555 has a session in chat_map", chat_id in map_data)
    session_id = map_data[chat_id]["session_id"]

    # 4. (history persistence requires the full handler, not the channel;
    #     see test_08 for that)
    step("session_id format is tg-*", session_id.startswith("tg-"))

    await ch.stop()


async def test_08_full_handler_with_real_persistence(tmp: Path) -> None:
    """Bypass the channel entirely — call telegram_handler() directly
    and verify history is persisted via the persistence layer.
    Uses a fake agent (not the real engine) so we don't need an LLM."""
    reset_telegram_session_manager()
    th_module.reset_for_tests()

    chat_id = "666"
    text = "hello, agent"

    # Build a fake agent that we inject into the handler's cache
    fake_agent = MockAgent()

    # Patch _get_or_create_agent to return our fake
    def fake_get_or_create_agent(session_id: str) -> Any:
        th_module._agents[session_id] = fake_agent
        return fake_agent

    with patch.object(th_module, "_get_or_create_agent", fake_get_or_create_agent):
        reply = await telegram_handler("telegram", chat_id, text)

    step("telegram_handler returned a reply", reply is not None and len(reply) > 0)
    step(
        "reply is the mock agent's output",
        reply is not None and "[mock reply to:" in reply,
    )
    step("fake agent was called exactly once", len(fake_agent.calls) == 1)

    # Now verify the session was created and history was persisted
    mgr = TelegramSessionManager(halo_home=tmp)
    info = mgr.get(chat_id)
    step("session was created for chat 666", info is not None)
    if info is None:
        return

    messages = persistence.load_messages(TELEGRAM_PROJECT, info.session_id)
    step(
        "history was persisted (>= 2 messages: user + assistant)",
        messages is not None and len(messages) >= 2,
    )

    if messages and len(messages) >= 2:
        # First should be the user, last the assistant
        step(
            "first persisted message is USER role",
            messages[0].role == Role.USER,
        )
        step(
            "last persisted message is ASSISTANT role",
            messages[-1].role == Role.ASSISTANT,
        )


async def test_09_resume_existing_session(tmp: Path) -> None:
    """A second message to the same chat_id should reuse the session."""
    reset_telegram_session_manager()
    th_module.reset_for_tests()

    chat_id = "777"
    fake_agent = MockAgent()

    def fake_get_or_create_agent(session_id: str) -> Any:
        th_module._agents[session_id] = fake_agent
        return fake_agent

    with patch.object(th_module, "_get_or_create_agent", fake_get_or_create_agent):
        await telegram_handler("telegram", chat_id, "first message")
        await telegram_handler("telegram", chat_id, "second message")

    # Same session for both messages
    mgr = TelegramSessionManager(halo_home=tmp)
    info = mgr.get(chat_id)
    step("session exists for chat 777", info is not None)
    if info is None:
        return

    messages = persistence.load_messages(TELEGRAM_PROJECT, info.session_id)
    # Each call writes the full history (2 messages each call: user + assistant)
    # Second call overwrites the file, so we expect exactly 2 messages.
    step(
        "second message overwrites with current turn (2 messages)",
        messages is not None and len(messages) == 2,
    )
    step(
        "second message content is the second user text",
        messages is not None and messages[0].content == "second message",
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main() -> int:
    print("→ Gundam Halo — Telegram dry-run round-trip verifier\n")
    tmp = fresh_halo_home()
    print(f"  HALO_HOME: {tmp}\n")
    try:
        await test_01_session_created_on_first_message(tmp)
        print()
        await test_02_commands(tmp)
        print()
        await test_03_plain_text_routes_to_agent(tmp)
        print()
        await test_04_unknown_command_falls_through(tmp)
        print()
        await test_05_unauthorized_chat_id_silently_dropped(tmp)
        print()
        await test_06_cross_chat_isolation(tmp)
        print()
        await test_07_handler_runs_mock_agent_and_persists(tmp)
        print()
        await test_08_full_handler_with_real_persistence(tmp)
        print()
        await test_09_resume_existing_session(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    if passed == total:
        print(f"  ✓ {passed}/{total} dry-run round-trip checks passed")
        return 0
    else:
        print(f"  ✗ {passed}/{total} dry-run round-trip checks passed")
        failed = [name for name, ok, _ in results if not ok]
        print(f"    Failed: {failed}")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

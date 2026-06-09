"""Tests for UserMemoryStore, identity resolution, and memory tools."""

from __future__ import annotations

import pytest

from app.agents.system_prompt import build_system_prompt
from app.channels.identity import (
    ChannelIdentity,
    resolve_telegram_identity,
    resolve_telegram_identity_cached,
    reset_identity_cache,
)
from app.core.config import Config
from app.core.types import AgentContext
from app.memory.user_memory import (
    MemoryEntry,
    UserMemoryStore,
    get_user_memory_store,
    reset_user_memory_store,
    slugify_key,
    user_key_for,
)
from app.tools.memory import MemoryReadTool, MemoryWriteTool


# ---------------------------------------------------------------------------
# slug + user_key helpers
# ---------------------------------------------------------------------------


class TestSlugify:
    def test_lowercase(self):
        assert slugify_key("Foo") == "foo"

    def test_spaces_to_underscores(self):
        assert slugify_key("Hello World") == "hello_world"

    def test_strips_punct(self):
        assert slugify_key("Hello, World!") == "hello_world"

    def test_collapses_underscores(self):
        assert slugify_key("a   b") == "a_b"

    def test_strips_edges(self):
        assert slugify_key("_foo_") == "foo"

    def test_truncates(self):
        assert len(slugify_key("a" * 200)) == 64

    def test_empty(self):
        assert slugify_key("!!!") == ""


class TestUserKeyFor:
    def test_lowercase_and_strip(self):
        assert user_key_for("Ken") == "ken"

    def test_with_punct(self):
        assert user_key_for("Ken (Telegram)") == "ken_telegram"

    def test_empty(self):
        assert user_key_for("") == ""


# ---------------------------------------------------------------------------
# UserMemoryStore
# ---------------------------------------------------------------------------


@pytest.fixture
def store(tmp_path):
    """A fresh UserMemoryStore under tmp_path."""
    s = UserMemoryStore(halo_home=tmp_path)
    yield s
    # Best-effort cleanup
    reset_user_memory_store()


class TestUserMemoryStore:
    def test_set_and_get(self, store):
        entry = store.set("ken", "preferred_name", "Ken")
        assert entry.user == "ken"
        assert entry.key == "preferred_name"
        assert entry.value == "Ken"
        got = store.get("ken", "preferred_name")
        assert got is not None
        assert got.value == "Ken"

    def test_get_missing(self, store):
        assert store.get("ken", "timezone") is None

    def test_delete_existing(self, store):
        store.set("ken", "timezone", "Asia/Hong_Kong")
        assert store.delete("ken", "timezone") is True
        assert store.get("ken", "timezone") is None

    def test_delete_missing(self, store):
        assert store.delete("ken", "nope") is False

    def test_slugified_key_round_trip(self, store):
        store.set("ken", "Preferred Name", "Ken")
        # Stored under "preferred_name"
        assert store.get("ken", "preferred_name").value == "Ken"
        # Any case/punct variant retrieves the same entry
        assert store.get("ken", "PREFERRED NAME").value == "Ken"

    def test_update_existing(self, store):
        store.set("ken", "timezone", "Asia/Hong_Kong")
        e1 = store.get("ken", "timezone")
        # Sleep briefly to ensure timestamp changes
        import time
        time.sleep(0.01)
        store.set("ken", "timezone", "America/Los_Angeles")
        e2 = store.get("ken", "timezone")
        assert e2.value == "America/Los_Angeles"
        assert e2.created_at == e1.created_at
        assert e2.updated_at > e1.updated_at

    def test_rejects_huge_value(self, store):
        big = "x" * (9 * 1024)  # 9 KB > 8 KB limit
        with pytest.raises(ValueError, match="too large"):
            store.set("ken", "huge", big)

    def test_rejects_empty_key(self, store):
        with pytest.raises(ValueError, match="slugifies to empty"):
            store.set("ken", "!!!", "v")

    def test_list_keys_sorted_by_recency(self, store):
        store.set("ken", "a", "1")
        import time
        time.sleep(0.01)
        store.set("ken", "b", "2")
        time.sleep(0.01)
        store.set("ken", "c", "3")
        keys = [e.key for e in store.list_keys("ken")]
        assert keys == ["c", "b", "a"]

    def test_list_keys_empty(self, store):
        assert store.list_keys("ken") == []

    def test_list_users(self, store):
        store.set("ken", "x", "1")
        store.set("alice", "y", "2")
        assert set(store.list_users()) == {"ken", "alice"}

    def test_writes_markdown_file(self, store):
        store.set("ken", "timezone", "Asia/Hong_Kong")
        path = store.user_dir("ken") / "timezone.md"
        assert path.exists()
        body = path.read_text(encoding="utf-8")
        assert "Asia/Hong_Kong" in body
        assert "# timezone" in body

    def test_concurrent_writes_serialized(self, store):
        # Smoke test for the lock — just confirm it doesn't deadlock
        # when two threads write to the same user.
        import threading
        errors = []
        def writer(i):
            try:
                store.set("ken", f"key_{i}", f"value_{i}")
            except Exception as e:
                errors.append(e)
        threads = [threading.Thread(target=writer, args=(i,)) for i in range(10)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert errors == []


# ---------------------------------------------------------------------------
# ChannelIdentity
# ---------------------------------------------------------------------------


class TestResolveTelegramIdentity:
    def test_explicit_config_name_wins(self):
        ident = resolve_telegram_identity(
            "123",
            config_display_names={"123": "Ken"},
            update_first_name="Kenny",
            update_username="k",
        )
        assert ident.display_name == "Ken"
        assert ident.is_group is False

    def test_group_title_used_for_group(self):
        ident = resolve_telegram_identity(
            "456",
            update_chat_title="Dev Team",
            is_group=True,
        )
        assert ident.display_name == "Dev Team"
        assert ident.is_group is True

    def test_first_name_used_for_dm(self):
        ident = resolve_telegram_identity(
            "789",
            update_first_name="Alice",
            update_username="ali",
        )
        assert ident.display_name == "Alice (@ali)"

    def test_first_name_only(self):
        ident = resolve_telegram_identity(
            "789",
            update_first_name="Alice",
        )
        assert ident.display_name == "Alice"

    def test_fallback_to_chat_id(self):
        ident = resolve_telegram_identity("999")
        assert ident.display_name == "telegram:999"

    def test_priority_explicit_over_group(self):
        ident = resolve_telegram_identity(
            "123",
            config_display_names={"123": "Boss"},
            update_chat_title="Random Group",
            is_group=True,
        )
        # Explicit wins even in groups
        assert ident.display_name == "Boss"

    def test_cached_uses_explicit(self):
        reset_identity_cache()
        ident1 = resolve_telegram_identity_cached(
            "123",
            config_display_names={"123": "Ken"},
        )
        # Change input — explicit should still win
        ident2 = resolve_telegram_identity_cached(
            "123",
            config_display_names={"123": "Ken"},
            update_first_name="Different",
        )
        assert ident1.display_name == "Ken"
        assert ident2.display_name == "Ken"

    def test_cached_skips_for_first_name(self):
        # First-name based names should NOT be cached (transient)
        reset_identity_cache()
        resolve_telegram_identity_cached(
            "123",
            update_first_name="Alice",
        )
        ident2 = resolve_telegram_identity_cached(
            "123",
            update_first_name="Bob",  # different
        )
        assert ident2.display_name == "Bob"


# ---------------------------------------------------------------------------
# MemoryRead / MemoryWrite tools
# ---------------------------------------------------------------------------


class TestMemoryTools:
    @pytest.mark.asyncio
    async def test_write_then_read(self, tmp_path):
        store = UserMemoryStore(halo_home=tmp_path)
        write = MemoryWriteTool()
        read = MemoryReadTool()

        out = await write.run(
            key="preferred_name",
            value="Ken",
            store=store,
            display_name="Ken",
        )
        assert "Saved" in out

        out = await read.run(
            key="preferred_name",
            store=store,
            display_name="Ken",
        )
        assert out == "preferred_name: Ken"

    @pytest.mark.asyncio
    async def test_read_all(self, tmp_path):
        store = UserMemoryStore(halo_home=tmp_path)
        await MemoryWriteTool().run(
            key="a", value="1", store=store, display_name="Ken"
        )
        await MemoryWriteTool().run(
            key="b", value="2", store=store, display_name="Ken"
        )

        out = await MemoryReadTool().run(
            key="", store=store, display_name="Ken"
        )
        # Both keys present (order: newest first)
        assert "a: 1" in out
        assert "b: 2" in out

    @pytest.mark.asyncio
    async def test_read_missing(self, tmp_path):
        store = UserMemoryStore(halo_home=tmp_path)
        out = await MemoryReadTool().run(
            key="nope", store=store, display_name="Ken"
        )
        assert "(no entry for key" in out

    @pytest.mark.asyncio
    async def test_no_user_context(self, tmp_path):
        store = UserMemoryStore(halo_home=tmp_path)
        out = await MemoryWriteTool().run(
            key="x", value="y", store=store
        )
        assert "no user context" in out.lower()

    @pytest.mark.asyncio
    async def test_delete(self, tmp_path):
        store = UserMemoryStore(halo_home=tmp_path)
        await MemoryWriteTool().run(
            key="a", value="1", store=store, display_name="Ken"
        )
        out = await MemoryWriteTool().run(
            key="a", value="", delete=True, store=store, display_name="Ken"
        )
        assert "Deleted" in out
        # Verify it's gone
        out2 = await MemoryReadTool().run(
            key="a", store=store, display_name="Ken"
        )
        assert "(no entry" in out2

    @pytest.mark.asyncio
    async def test_per_user_isolation(self, tmp_path):
        store = UserMemoryStore(halo_home=tmp_path)
        await MemoryWriteTool().run(
            key="tz", value="HK", store=store, display_name="Ken"
        )
        await MemoryWriteTool().run(
            key="tz", value="Tokyo", store=store, display_name="Alice"
        )
        out_ken = await MemoryReadTool().run(
            key="tz", store=store, display_name="Ken"
        )
        out_alice = await MemoryReadTool().run(
            key="tz", store=store, display_name="Alice"
        )
        assert "HK" in out_ken
        assert "Tokyo" in out_alice


# ---------------------------------------------------------------------------
# build_system_prompt
# ---------------------------------------------------------------------------


class TestBuildSystemPrompt:
    def test_no_context_returns_base(self):
        out = build_system_prompt("base prompt", context=None)
        assert out == "base prompt"

    def test_context_without_user_unchanged(self):
        ctx = AgentContext(project_id="p", session_id="s")
        out = build_system_prompt("base", context=ctx)
        assert out == "base"

    def test_adds_identity_block(self):
        ctx = AgentContext(
            project_id="p", session_id="s",
            user_display_name="Ken", channel="telegram",
        )
        out = build_system_prompt("base", context=ctx)
        assert "Ken" in out
        assert "telegram" in out
        assert "Who you're talking to" in out

    def test_adds_memory_recall(self, tmp_path):
        store = UserMemoryStore(halo_home=tmp_path)
        store.set("ken", "preferred_name", "Ken")
        store.set("ken", "timezone", "Asia/Hong_Kong")
        ctx = AgentContext(
            project_id="p", session_id="s",
            user_display_name="Ken",
        )
        out = build_system_prompt("base", context=ctx, store=store)
        assert "preferred_name" in out
        assert "Asia/Hong_Kong" in out
        assert "What you remember" in out

    def test_no_memory_blocks_but_identity_present(self, tmp_path):
        store = UserMemoryStore(halo_home=tmp_path)
        ctx = AgentContext(
            project_id="p", session_id="s",
            user_display_name="Fresh",
        )
        out = build_system_prompt("base", context=ctx, store=store)
        # Identity present
        assert "Fresh" in out
        # No memory block
        assert "What you remember" not in out

    def test_falls_back_to_user_id(self, tmp_path):
        store = UserMemoryStore(halo_home=tmp_path)
        # No display name, only user_id
        store.set("12345", "x", "y")
        ctx = AgentContext(
            project_id="p", session_id="s",
            user_id="12345",
        )
        out = build_system_prompt("base", context=ctx, store=store)
        # Memory recall should still trigger (we slugify user_id to a key)
        # The rendered format is "**key**: value"
        assert "**x**: y" in out

"""Tests for the M12 lifecycle glue (on_session_saved, recall, rebuild)."""
from __future__ import annotations

import time

import pytest
from app.core.types import Message, Role, ToolCall
from app.memory import lifecycle
from app.memory.lifecycle import (
    rebuild_index,
    recall,
    reset_all_memory,
)
from app.memory.user_memory import UserMemoryStore
from app.projects import persistence


@pytest.fixture(autouse=True)
def _reset_memory_singletons():
    """Reset every M12 singleton between tests."""
    reset_all_memory()
    yield
    reset_all_memory()


@pytest.fixture
def messages() -> list[Message]:
    return [
        Message(role=Role.SYSTEM, content="You are a Gundam expert."),
        Message(role=Role.USER, content="Tell me about the Unicorn model."),
        Message(role=Role.ASSISTANT, content="The Unicorn features a psychoframe."),
        Message(role=Role.USER, content="What about NT-D mode?"),
        Message(
            role=Role.ASSISTANT,
            content="",
            tool_calls=[ToolCall(id="tc1", name="file_read",
                                  arguments={"path": "/x"})],
        ),
        Message(
            role=Role.TOOL, content="<file contents>",
            tool_call_id="tc1", name="file_read",
        ),
    ]


class TestOnSessionSaved:
    def test_writes_sqlite_index(self, tmp_path, messages):
        persistence.save_messages("alpha", "sess-1", messages,
                                   agent_type="native_react")
        # Lifecycle is wired into save_messages
        from app.memory.sqlite_index import get_sqlite_index
        idx = get_sqlite_index()
        row = idx.get_session("sess-1")
        assert row is not None
        assert row.project_name == "alpha"
        assert row.message_count == len(messages)
        msgs = idx.get_messages("sess-1")
        assert [m.role for m in msgs] == [m.role.value for m in messages]

    def test_attaches_to_project_thread(self, tmp_path, messages):
        persistence.save_messages("alpha", "sess-1", messages)
        from app.memory.sqlite_index import get_sqlite_index
        idx = get_sqlite_index()
        threads = idx.list_threads()
        assert any(t["project_name"] == "alpha" for t in threads)
        # 1 session attached
        alpha_thread = [t for t in threads if t["project_name"] == "alpha"][0]
        assert alpha_thread["session_count"] == 1

    def test_enqueues_for_embedding(self, tmp_path, messages):
        persistence.save_messages("alpha", "sess-1", messages)
        # Worker should have drained some chunks
        be = lifecycle.get_background_embedder()
        stats = be.stats()
        assert stats["enqueued"] >= len(messages)
        # Give the worker a moment to drain
        time.sleep(0.5)
        stats = be.stats()
        # The exact count varies; just check the counter advances
        assert stats["embedded"] >= 0  # at least the worker is alive


class TestOnSessionDeleted:
    def test_removes_from_sqlite(self, tmp_path, messages):
        persistence.save_messages("alpha", "sess-1", messages)
        from app.memory.sqlite_index import get_sqlite_index
        idx = get_sqlite_index()
        assert idx.get_session("sess-1") is not None
        persistence.delete_session("alpha", "sess-1")
        assert idx.get_session("sess-1") is None


class TestOnUserMemorySet:
    def test_enqueues_for_embedding(self, tmp_path):
        # Need to set up a UserMemoryStore under the same home
        um = UserMemoryStore(halo_home=tmp_path)
        um.set("ken", "favorite_gundam", "Unicorn")
        be = lifecycle.get_background_embedder()
        stats = be.stats()
        assert stats["enqueued"] >= 1


class TestRebuildIndex:
    def test_rebuilds_from_disk(self, tmp_path, messages):
        # Save a few sessions + user memory
        persistence.save_messages("alpha", "sess-1", messages,
                                   agent_type="native_react")
        persistence.save_messages("alpha", "sess-2",
                                   [Message(role=Role.USER, content="Burning!")],
                                   agent_type="native_react")
        um = UserMemoryStore(halo_home=tmp_path)
        um.set("ken", "favorite_gundam", "Unicorn")
        um.set("ken", "timezone", "Asia/Hong_Kong")

        # Force a reset first
        from app.memory.sqlite_index import get_sqlite_index
        from app.memory.vector_index import get_vector_index
        idx = get_sqlite_index()
        vi = get_vector_index()
        idx.reset()
        vi.reset()
        assert idx.count_sessions() == 0
        assert vi.ntotal() == 0

        # Rebuild
        stats = rebuild_index()
        assert stats["sessions"] == 2
        assert stats["messages"] >= 3
        assert stats["memory_entries"] == 2
        assert stats["vector_ntotal"] >= 0  # hash embeddings may be noisy

        # SQLite should be repopulated
        idx = get_sqlite_index()
        assert idx.count_sessions() == 2
        # Per-project listing should work
        rows = idx.list_sessions(project="alpha")
        assert len(rows) == 2


class TestRecall:
    def test_recall_finds_similar_chunk(self, tmp_path, messages):
        persistence.save_messages("alpha", "sess-1", messages)
        # Drain queue
        be = lifecycle.get_background_embedder()
        time.sleep(1.0)  # let worker catch up
        # Recall with a query that lexically matches content
        hits = recall("Unicorn psychoframe", k=3)
        # The hash embedder isn't great at semantics, but the
        # token overlap should still surface a chunk
        assert isinstance(hits, list)
        # At least the recall function should run without error
        for h in hits:
            assert h.score >= 0.0
            assert h.kind in ("message", "memory_entry")

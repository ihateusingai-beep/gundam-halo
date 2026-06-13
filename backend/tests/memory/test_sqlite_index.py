"""Tests for SqliteIndex (M12)."""
from __future__ import annotations

import time

import pytest
from app.memory.sqlite_index import (
    SCHEMA_VERSION,
    SqliteIndex,
)


@pytest.fixture
def index(tmp_path):
    idx = SqliteIndex(halo_home=tmp_path, wal=False)
    idx.init()
    yield idx
    idx.close()


def _row(seq, role, content, *, tool_calls=None, tool_call_id=None, name=None):
    return (seq, role, content, tool_calls, tool_call_id, name, time.time() + seq)


# ---------------------------------------------------------------------------
# Schema bootstrap
# ---------------------------------------------------------------------------


class TestSchemaBootstrap:
    def test_init_creates_tables(self, tmp_path):
        idx = SqliteIndex(halo_home=tmp_path, wal=False)
        idx.init()
        # Query sqlite_master
        rows = idx.conn().execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        names = {r["name"] for r in rows}
        assert "sessions" in names
        assert "messages" in names
        assert "threads" in names
        assert "session_thread" in names
        idx.close()

    def test_init_records_schema_version(self, index):
        assert index.schema_version() == SCHEMA_VERSION

    def test_init_is_idempotent(self, tmp_path):
        idx = SqliteIndex(halo_home=tmp_path, wal=False)
        idx.init()
        idx.init()
        idx.init()
        assert idx.schema_version() == SCHEMA_VERSION
        idx.close()

    def test_needs_rebuild_when_no_db(self, tmp_path):
        idx = SqliteIndex(halo_home=tmp_path, wal=False)
        # No init → no file
        assert idx.needs_rebuild() is True

    def test_reset_wipes_and_recreates(self, index, tmp_path):
        index.upsert_session(
            session_id="abc",
            project_name="p",
            agent_type="native_react",
            created_at=1.0,
            updated_at=2.0,
        )
        assert index.count_sessions() == 1
        index.reset()
        assert index.count_sessions() == 0
        assert index.schema_version() == SCHEMA_VERSION


# ---------------------------------------------------------------------------
# Session upsert
# ---------------------------------------------------------------------------


class TestSessionUpsert:
    def test_insert(self, index):
        index.upsert_session(
            session_id="s1",
            project_name="proj",
            agent_type="native_react",
            created_at=1.0,
            updated_at=2.0,
            channel="web",
            message_count=3,
        )
        row = index.get_session("s1")
        assert row is not None
        assert row.session_id == "s1"
        assert row.project_name == "proj"
        assert row.agent_type == "native_react"
        assert row.channel == "web"
        assert row.message_count == 3
        assert row.created_at == 1.0
        assert row.updated_at == 2.0

    def test_update_overwrites(self, index):
        index.upsert_session(
            session_id="s1",
            project_name="proj",
            agent_type="native_react",
            created_at=1.0,
            updated_at=2.0,
            message_count=0,
        )
        index.upsert_session(
            session_id="s1",
            project_name="proj",
            agent_type="native_react",
            created_at=1.0,
            updated_at=3.0,
            message_count=5,
        )
        row = index.get_session("s1")
        assert row is not None
        assert row.updated_at == 3.0
        assert row.message_count == 5

    def test_delete(self, index):
        index.upsert_session(
            session_id="s1",
            project_name="p",
            agent_type="native_react",
            created_at=1.0,
            updated_at=2.0,
        )
        assert index.delete_session("s1") is True
        assert index.delete_session("s1") is False
        assert index.get_session("s1") is None

    def test_list_newest_first(self, index):
        for i, ts in enumerate([3.0, 1.0, 2.0]):
            index.upsert_session(
                session_id=f"s{i}",
                project_name="p",
                agent_type="native_react",
                created_at=ts,
                updated_at=ts,
            )
        rows = index.list_sessions()
        assert [r.session_id for r in rows] == ["s0", "s2", "s1"]

    def test_list_filter_by_project(self, index):
        index.upsert_session(
            session_id="a", project_name="alpha",
            agent_type="native_react", created_at=1.0, updated_at=1.0,
        )
        index.upsert_session(
            session_id="b", project_name="beta",
            agent_type="native_react", created_at=1.0, updated_at=1.0,
        )
        rows = index.list_sessions(project="alpha")
        assert [r.session_id for r in rows] == ["a"]
        assert index.count_sessions(project="alpha") == 1
        assert index.count_sessions() == 2

    def test_list_pagination(self, index):
        for i in range(10):
            index.upsert_session(
                session_id=f"s{i}",
                project_name="p",
                agent_type="native_react",
                created_at=float(i),
                updated_at=float(i),
            )
        page1 = index.list_sessions(limit=3, offset=0)
        page2 = index.list_sessions(limit=3, offset=3)
        assert len(page1) == 3
        assert len(page2) == 3
        assert page1[0].session_id != page2[0].session_id


# ---------------------------------------------------------------------------
# Message upsert
# ---------------------------------------------------------------------------


class TestMessageUpsert:
    def test_insert_messages(self, index):
        index.upsert_session(
            session_id="s1",
            project_name="p",
            agent_type="native_react",
            created_at=1.0,
            updated_at=2.0,
        )
        rows = [
            _row(0, "user", "hello"),
            _row(1, "assistant", "hi there"),
            _row(2, "user", "how are you?"),
        ]
        index.upsert_messages("s1", rows)
        msgs = index.get_messages("s1")
        assert [m.seq for m in msgs] == [0, 1, 2]
        assert [m.role for m in msgs] == ["user", "assistant", "user"]
        assert msgs[1].content == "hi there"

    def test_get_messages_ordered(self, index):
        index.upsert_session(
            session_id="s1", project_name="p",
            agent_type="native_react", created_at=1.0, updated_at=2.0,
        )
        # Insert out of order
        index.upsert_messages("s1", [
            _row(2, "user", "third"),
            _row(0, "user", "first"),
            _row(1, "assistant", "second"),
        ])
        msgs = index.get_messages("s1")
        assert [m.content for m in msgs] == ["first", "second", "third"]

    def test_upsert_replaces_existing(self, index):
        index.upsert_session(
            session_id="s1", project_name="p",
            agent_type="native_react", created_at=1.0, updated_at=2.0,
        )
        index.upsert_messages("s1", [
            _row(0, "user", "v1"),
            _row(1, "assistant", "v1"),
        ])
        # Re-save with different content
        index.upsert_messages("s1", [
            _row(0, "user", "v2"),
            _row(1, "assistant", "v2"),
            _row(2, "user", "new"),
        ])
        msgs = index.get_messages("s1")
        assert [m.content for m in msgs] == ["v2", "v2", "new"]

    def test_get_message_by_id(self, index):
        index.upsert_session(
            session_id="s1", project_name="p",
            agent_type="native_react", created_at=1.0, updated_at=2.0,
        )
        index.upsert_messages("s1", [
            _row(0, "user", "hi"),
        ])
        msgs = index.get_messages("s1")
        mid = msgs[0].message_id
        fetched = index.get_message(mid)
        assert fetched is not None
        assert fetched.content == "hi"

    def test_tool_calls_roundtrip(self, index):
        index.upsert_session(
            session_id="s1", project_name="p",
            agent_type="native_react", created_at=1.0, updated_at=2.0,
        )
        tcs = [{"id": "tc1", "name": "file_read", "arguments": {"path": "/x"}}]
        index.upsert_messages("s1", [
            (0, "assistant", "", tcs, None, None, 1.0),
        ])
        msgs = index.get_messages("s1")
        assert msgs[0].tool_calls is not None
        import json
        decoded = json.loads(msgs[0].tool_calls)
        assert decoded == tcs

    def test_message_limit_offset(self, index):
        index.upsert_session(
            session_id="s1", project_name="p",
            agent_type="native_react", created_at=1.0, updated_at=2.0,
        )
        index.upsert_messages("s1", [
            _row(i, "user", f"msg {i}") for i in range(10)
        ])
        page = index.get_messages("s1", limit=3, offset=2)
        assert [m.content for m in page] == ["msg 2", "msg 3", "msg 4"]

    def test_iter_all_messages_streams(self, index):
        index.upsert_session(
            session_id="s1", project_name="p",
            agent_type="native_react", created_at=1.0, updated_at=2.0,
        )
        index.upsert_messages("s1", [
            _row(i, "user", f"msg {i}") for i in range(50)
        ])
        all_msgs = list(index.iter_all_messages())
        assert len(all_msgs) == 50


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


class TestSearch:
    def test_search_messages(self, index):
        index.upsert_session(
            session_id="s1", project_name="p",
            agent_type="native_react", created_at=1.0, updated_at=2.0,
        )
        index.upsert_messages("s1", [
            _row(0, "user", "Unicorn psychoframe awakens"),
            _row(1, "assistant", "Burning mode activated"),
            _row(2, "user", "I like Unicorn model"),
        ])
        hits = index.search_messages("Unicorn")
        assert len(hits) == 2
        assert all("Unicorn" in h.content for h in hits)

    def test_search_with_project_filter(self, index):
        for sid, proj in [("a", "alpha"), ("b", "beta")]:
            index.upsert_session(
                session_id=sid, project_name=proj,
                agent_type="native_react", created_at=1.0, updated_at=2.0,
            )
            index.upsert_messages(sid, [
                _row(0, "user", "Unicorn in " + proj),
            ])
        hits = index.search_messages("Unicorn", project="alpha")
        assert len(hits) == 1
        assert hits[0].session_id == "a"

    def test_search_no_hits(self, index):
        index.upsert_session(
            session_id="s1", project_name="p",
            agent_type="native_react", created_at=1.0, updated_at=2.0,
        )
        index.upsert_messages("s1", [_row(0, "user", "hi")])
        assert index.search_messages("xyz_no_match") == []


# ---------------------------------------------------------------------------
# Threads
# ---------------------------------------------------------------------------


class TestThreads:
    def test_ensure_project_thread_creates(self, index):
        tid = index.ensure_project_thread("alpha")
        assert tid == "proj-alpha"

    def test_ensure_project_thread_idempotent(self, index):
        t1 = index.ensure_project_thread("alpha")
        t2 = index.ensure_project_thread("alpha")
        assert t1 == t2

    def test_attach_session(self, index):
        index.upsert_session(
            session_id="s1", project_name="p",
            agent_type="native_react", created_at=1.0, updated_at=2.0,
        )
        tid = index.ensure_project_thread("p")
        index.attach_session_to_thread("s1", tid)
        threads = index.list_threads()
        assert len(threads) == 1
        assert threads[0]["session_count"] == 1

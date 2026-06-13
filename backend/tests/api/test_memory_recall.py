"""API tests for /api/memory/{sessions,search,recall,rebuild} (M12)."""
from __future__ import annotations

import time

import pytest
from app.core import config as _config_module
from app.core.types import Message, Role
from app.main import create_app
from app.projects import persistence
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _reset_singletons():
    from app.memory.lifecycle import reset_all_memory

    reset_all_memory()
    _config_module.reset_config()
    yield
    from app.memory.lifecycle import reset_all_memory

    reset_all_memory()
    _config_module.reset_config()


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HALO_HOME", str(tmp_path))
    monkeypatch.setenv("MINIMAX_API_KEY", "test-fake-key")
    _config_module.reset_config()
    _config_module.get_config(home=tmp_path)
    # Force-disable the vector index AFTER the config reset so the
    # FAISS native module never loads. (The autouse fixture sets
    # this flag too, but ``reset_config()`` wipes it.)
    cfg = _config_module.get_config()
    cfg.memory.disable_vector_index = True
    app = create_app()
    with TestClient(app) as c:
        yield c
    from app.memory.lifecycle import reset_all_memory

    reset_all_memory()
    _config_module.reset_config()


def _seed(client, messages_by_session):
    for project, sid, msgs in messages_by_session:
        persistence.save_messages(
            project, sid, msgs, agent_type="native_react"
        )
    time.sleep(0.5)


class TestSessionsList:
    def test_empty(self, client):
        r = client.get("/api/memory/sessions")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 0
        assert data["sessions"] == []

    def test_returns_indexed_sessions(self, client):
        _seed(client, [
            (
                "alpha", "s1",
                [Message(role=Role.USER, content="hi")],
            ),
            (
                "beta", "s2",
                [Message(role=Role.USER, content="hello")],
            ),
        ])
        r = client.get("/api/memory/sessions")
        data = r.json()
        assert data["total"] == 2
        # Newest first
        assert data["sessions"][0]["session_id"] == "s2"
        assert data["sessions"][0]["project_name"] == "beta"

    def test_filter_by_project(self, client):
        _seed(client, [
            ("alpha", "s1", [Message(role=Role.USER, content="a")]),
            ("beta", "s2", [Message(role=Role.USER, content="b")]),
        ])
        r = client.get("/api/memory/sessions", params={"project": "alpha"})
        data = r.json()
        assert data["total"] == 1
        assert data["sessions"][0]["project_name"] == "alpha"

    def test_pagination(self, client):
        msgs = [
            (f"p{i}", f"s{i}", [Message(role=Role.USER, content="x")])
            for i in range(5)
        ]
        _seed(client, msgs)
        r = client.get("/api/memory/sessions", params={"limit": 2, "offset": 0})
        data = r.json()
        assert len(data["sessions"]) == 2
        assert data["total"] == 5


class TestSessionMessages:
    def test_returns_messages(self, client):
        _seed(client, [
            (
                "alpha", "s1",
                [
                    Message(role=Role.SYSTEM, content="sys"),
                    Message(role=Role.USER, content="hi"),
                ],
            ),
        ])
        r = client.get("/api/memory/sessions/s1/messages")
        assert r.status_code == 200
        data = r.json()
        assert data["message_count"] == 2
        assert data["messages"][0]["role"] == "system"
        assert data["messages"][1]["content"] == "hi"

    def test_404_for_unknown_session(self, client):
        r = client.get("/api/memory/sessions/nope/messages")
        assert r.status_code == 404


class TestSearch:
    def test_finds_matching_content(self, client):
        _seed(client, [
            (
                "alpha", "s1",
                [
                    Message(role=Role.USER, content="Unicorn psychoframe"),
                    Message(role=Role.USER, content="Freedom hiMAT"),
                ],
            ),
        ])
        r = client.get("/api/memory/search", params={"q": "Unicorn"})
        data = r.json()
        assert data["count"] == 1
        assert "Unicorn" in data["results"][0]["snippet"]

    def test_no_results(self, client):
        _seed(client, [
            ("p", "s1", [Message(role=Role.USER, content="hi")]),
        ])
        r = client.get("/api/memory/search", params={"q": "xyz_nothing"})
        data = r.json()
        assert data["count"] == 0


class TestRecall:
    def test_returns_results(self, client):
        _seed(client, [
            (
                "alpha", "s1",
                [
                    Message(role=Role.USER, content="The Unicorn has a psychoframe"),
                    Message(role=Role.ASSISTANT, content="Yes, NT-D mode awakens it"),
                ],
            ),
        ])
        r = client.get("/api/memory/recall", params={"q": "Unicorn", "k": 3})
        assert r.status_code == 200
        data = r.json()
        assert data["query"] == "Unicorn"
        assert data["k"] == 3
        assert isinstance(data["results"], list)

    def test_k_clamps(self, client):
        # k=100 exceeds the Query(le=50) cap → 422 validation error
        r = client.get("/api/memory/recall", params={"q": "x", "k": 100})
        assert r.status_code == 422
        # k=50 is the cap → accepted
        r = client.get("/api/memory/recall", params={"q": "x", "k": 50})
        assert r.status_code == 200


class TestRebuild:
    def test_rebuild_endpoint(self, client):
        _seed(client, [
            ("alpha", "s1", [Message(role=Role.USER, content="hi")]),
        ])
        r = client.post("/api/memory/rebuild")
        assert r.status_code == 200
        data = r.json()
        assert data["sessions"] == 1
        assert data["messages"] == 1
        assert data["vector_ntotal"] >= 0

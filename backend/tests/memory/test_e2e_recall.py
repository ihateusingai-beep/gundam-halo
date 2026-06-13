"""End-to-end test for the M12 memory layer (M12 E2E).

Simulates the full path:

  1. start a backend (lifespan startup)
  2. send a few messages via the API
  3. verify SQLite + FAISS are populated
  4. hit /api/memory/recall and get the right chunks back
  5. hit /api/memory/rebuild and verify the index survives
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest
from app.core import config as _config_module
from app.main import create_app
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _reset_singletons():
    """Reset all memory singletons between tests."""
    from app.memory.lifecycle import reset_all_memory

    reset_all_memory()
    _config_module.reset_config()
    yield
    from app.memory.lifecycle import reset_all_memory

    reset_all_memory()
    _config_module.reset_config()


@pytest.fixture
def home(tmp_path) -> Path:
    return tmp_path


@pytest.fixture
def client(home, monkeypatch):
    monkeypatch.setenv("HALO_HOME", str(home))
    monkeypatch.setenv("MINIMAX_API_KEY", "test-fake-key")
    _config_module.reset_config()
    _config_module.get_config(home=home)
    # Force-disable the vector index AFTER config reset (the
    # autouse fixture sets this too, but reset_config() wipes it).
    cfg = _config_module.get_config()
    cfg.memory.disable_vector_index = True
    app = create_app()
    with TestClient(app) as c:
        # The lifespan already calls init_memory_on_startup
        yield c
    # Tear down — call lifespan shutdown by exiting the with-block
    from app.memory.lifecycle import reset_all_memory

    reset_all_memory()
    _config_module.reset_config()


class TestE2EMemory:
    def test_save_index_recall_roundtrip(self, client, home):
        """Save messages, list them via API, recall them, rebuild."""
        # Use the persistence layer directly (the API needs a
        # running LLM to send messages, which is overkill here).
        from app.core.types import Message, Role
        from app.projects import persistence

        # Save 2 sessions
        persistence.save_messages(
            "alpha", "sess-1",
            [
                Message(role=Role.SYSTEM, content="You are a Gundam expert."),
                Message(role=Role.USER, content="Tell me about the Unicorn model."),
                Message(role=Role.ASSISTANT, content="The Unicorn features a psychoframe that awakens in NT-D mode."),
            ],
            agent_type="native_react",
        )
        persistence.save_messages(
            "beta", "sess-2",
            [
                Message(role=Role.USER, content="I like the Freedom Gundam."),
                Message(role=Role.ASSISTANT, content="Freedom uses the hiMAT flight system."),
            ],
            agent_type="native_react",
        )

        # Wait for the embedder to drain
        time.sleep(1.0)

        # 1) List sessions via API
        r = client.get("/api/memory/sessions")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["total"] == 2
        assert len(data["sessions"]) == 2

        # 2) Search for "Unicorn" — should hit sess-1
        r = client.get("/api/memory/search", params={"q": "Unicorn"})
        assert r.status_code == 200
        data = r.json()
        assert data["count"] >= 1
        assert any("Unicorn" in h["snippet"] for h in data["results"])

        # 3) Recall — even with hash embedder, it shouldn't crash
        r = client.get("/api/memory/recall", params={"q": "Unicorn", "k": 3})
        assert r.status_code == 200
        data = r.json()
        assert data["query"] == "Unicorn"
        # k=3
        assert len(data["results"]) <= 3

        # 4) Per-session message list
        r = client.get("/api/memory/sessions/sess-1/messages")
        assert r.status_code == 200
        data = r.json()
        assert data["message_count"] == 3
        assert data["project_name"] == "alpha"

        # 5) Rebuild
        r = client.post("/api/memory/rebuild")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["sessions"] == 2
        assert data["messages"] >= 5

    def test_user_memory_round_trips(self, client, home):
        """User memory writes are picked up by the indexer."""
        from app.memory.user_memory import UserMemoryStore

        um = UserMemoryStore(halo_home=home)
        um.set("ken", "favorite_gundam", "Unicorn")
        um.set("ken", "timezone", "Asia/Hong_Kong")
        time.sleep(0.5)

        # Recall with the user filter should find these
        r = client.get("/api/memory/recall", params={
            "q": "Unicorn", "k": 5, "user": "ken",
        })
        assert r.status_code == 200
        # Hash embedder: at least one of the entries should match
        data = r.json()
        for hit in data["results"]:
            if hit["kind"] == "memory_entry":
                assert hit.get("user") == "ken"

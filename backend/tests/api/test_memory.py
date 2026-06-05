"""Tests for the memory browse endpoints."""

import pytest

from app.projects import persistence
from app.core.types import Message, Role


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from app.main import halo_app
    return TestClient(halo_app)


# All tests in this module need permissive policy
pytestmark = pytest.mark.usefixtures("permissive_test_config")


def test_list_project_memory_empty(client, tmp_path, monkeypatch):
    """When no sessions exist, return empty list."""
    monkeypatch.setenv("HALO_HOME", str(tmp_path))
    # Create a project
    r = client.post("/api/projects", json={"name": "empty-proj"})
    assert r.status_code == 201

    r = client.get("/api/projects/empty-proj/memory")
    assert r.status_code == 200
    assert r.json() == []


def test_list_project_memory_with_sessions(client, tmp_path, monkeypatch):
    """List returns all sessions for the project."""
    monkeypatch.setenv("HALO_HOME", str(tmp_path))
    # Create a project and a few saved sessions
    client.post("/api/projects", json={"name": "with-sessions"})
    persistence.save_messages(
        "with-sessions", "sess1", [Message(role=Role.USER, content="hi")]
    )
    persistence.save_messages(
        "with-sessions",
        "sess2",
        [Message(role=Role.USER, content="a"), Message(role=Role.ASSISTANT, content="b")],
    )

    r = client.get("/api/projects/with-sessions/memory")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2
    sids = {s["id"] for s in data}
    assert sids == {"sess1", "sess2"}
    counts = {s["id"]: s["message_count"] for s in data}
    assert counts["sess1"] == 1
    assert counts["sess2"] == 2


def test_get_session_messages(client, tmp_path, monkeypatch):
    """Fetch full message history for a session."""
    monkeypatch.setenv("HALO_HOME", str(tmp_path))
    client.post("/api/projects", json={"name": "msgs-proj"})
    persistence.save_messages(
        "msgs-proj",
        "sessA",
        [
            Message(role=Role.SYSTEM, content="system prompt"),
            Message(role=Role.USER, content="hello"),
            Message(role=Role.ASSISTANT, content="hi there"),
        ],
    )

    r = client.get("/api/projects/msgs-proj/memory/sessA")
    assert r.status_code == 200
    data = r.json()
    assert data["session_id"] == "sessA"
    assert data["project_name"] == "msgs-proj"
    assert data["message_count"] == 3
    assert len(data["messages"]) == 3
    assert data["messages"][0]["role"] == "system"
    assert data["messages"][2]["content"] == "hi there"


def test_get_session_messages_404(client, tmp_path, monkeypatch):
    monkeypatch.setenv("HALO_HOME", str(tmp_path))
    client.post("/api/projects", json={"name": "nope-proj"})
    r = client.get("/api/projects/nope-proj/memory/nonexistent")
    assert r.status_code == 404

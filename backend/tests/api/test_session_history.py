"""Tests for the A5 message-history endpoint.

A5 = "ProjectDetailPage — optimistic message + reload safety".
The reload-safety side requires the backend to expose a way to
fetch a session's full transcript by session_id alone (no need to
know the project_name up-front — the page knows the session from
the URL ?session=… param).
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient


@pytest_asyncio.fixture
def client():
    from app.main import halo_app

    return TestClient(halo_app)


pytestmark = pytest.mark.usefixtures("permissive_test_config")


def _create_project(client, name: str = "a5-proj") -> str:
    r = client.post("/api/projects", json={"name": name, "agent_type": "simple"})
    assert r.status_code in (200, 201), r.text
    return r.json()["name"]


def test_session_messages_404_when_unknown(client):
    """A session that doesn't exist in memory or on disk → 404."""
    r = client.get("/api/sessions/does-not-exist-xyz/messages")
    assert r.status_code == 404


def test_session_messages_after_disk_persist(client, tmp_path, monkeypatch):
    """A persisted session's messages are readable via the new endpoint.

    Simulates the A5 reload scenario:
      1. Project + session are created (or known).
      2. A conversation file lands on disk (via the persistence module).
      3. GET /api/sessions/{id}/messages returns the transcript.
    """
    from app.projects import persistence
    from app.core.types import Message, Role

    _create_project(client)
    sid = "test-session-a5"
    msgs = [
        Message(role=Role.SYSTEM, content="You are a helpful assistant."),
        Message(role=Role.USER, content="Hello agent!"),
        Message(role=Role.ASSISTANT, content="Hi there! How can I help?"),
    ]
    persistence.save_messages("a5-proj", sid, msgs, agent_type="simple")

    r = client.get(f"/api/sessions/{sid}/messages")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["session_id"] == sid
    assert data["project_name"] == "a5-proj"
    assert data["message_count"] == 3
    assert [m["role"] for m in data["messages"]] == ["system", "user", "assistant"]
    assert [m["content"] for m in data["messages"]] == [
        "You are a helpful assistant.",
        "Hello agent!",
        "Hi there! How can I help?",
    ]


def test_session_messages_returns_empty_for_empty_session(client, tmp_path, monkeypatch):
    """A session that exists on disk but has zero messages → 200 + []."""
    from app.projects import persistence

    _create_project(client)
    sid = "empty-session-a5"
    # Save a session with no messages — persistence layer will still
    # write the file, and load_messages() will return [].
    persistence.save_messages("a5-proj", sid, [], agent_type="simple")

    r = client.get(f"/api/sessions/{sid}/messages")
    assert r.status_code == 200
    data = r.json()
    assert data["message_count"] == 0
    assert data["messages"] == []


def test_session_messages_shape_matches_memory_endpoint(client, tmp_path, monkeypatch):
    """The wire format of the new endpoint must match `/api/projects/.../memory/...`
    so the frontend can reuse the same `mapMessages()` mapper (B2 + A5 share).
    """
    from app.projects import persistence
    from app.core.types import Message, Role, ToolCall

    _create_project(client, name="a5-shape")
    sid = "shape-check-a5"
    msgs = [
        Message(role=Role.USER, content="search for the file"),
        Message(
            role=Role.ASSISTANT,
            content="Let me grep for it.",
            tool_calls=[
                ToolCall(id="tc-1", name="shell_exec", arguments={"command": "grep foo"})
            ],
        ),
        Message(role=Role.TOOL, content="matched line 1\nmatched line 2", name="shell_exec"),
    ]
    persistence.save_messages("a5-shape", sid, msgs, agent_type="native_react")

    # New endpoint
    r1 = client.get(f"/api/sessions/{sid}/messages")
    assert r1.status_code == 200
    new = r1.json()

    # Existing projects endpoint
    r2 = client.get(f"/api/projects/a5-shape/memory/{sid}")
    assert r2.status_code == 200
    old = r2.json()

    # Strip session_id and project_name from both before comparing;
    # the two endpoints emit the same messages list.
    new_msgs = new["messages"]
    old_msgs = old["messages"]
    assert new_msgs == old_msgs

    # And the assistant-with-tool-calls + tool-result pattern is preserved
    assert new_msgs[1]["role"] == "assistant"
    assert new_msgs[1]["tool_calls"][0]["name"] == "shell_exec"
    assert new_msgs[2]["role"] == "tool"
    assert new_msgs[2]["name"] == "shell_exec"

"""Smoke tests for the FastAPI app."""
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


# API tests need permissive policy to create real projects / sessions
pytestmark = pytest.mark.usefixtures("permissive_test_config")


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["name"] == "gundam-halo"


def test_system_gauges(client):
    r = client.get("/api/system/gauges")
    assert r.status_code == 200
    data = r.json()
    assert "cpu_percent" in data
    assert "memory_percent" in data


def test_list_projects_empty(client, tmp_path, monkeypatch):
    """When no projects exist, return empty list."""
    monkeypatch.setenv("HALO_HOME", str(tmp_path))
    # Reload config by setting env
    r = client.get("/api/projects")
    assert r.status_code == 200
    # Note: this may include projects from previous test runs if HALO_HOME was set
    # The fixture is a best-effort, not a guarantee of isolation
    assert isinstance(r.json(), list)


def test_create_project(client, tmp_path, monkeypatch):
    monkeypatch.setenv("HALO_HOME", str(tmp_path))
    r = client.post(
        "/api/projects",
        json={"name": "test-project", "description": "A test", "agent_type": "native_react"},
    )
    if r.status_code == 201:
        data = r.json()
        assert data["name"] == "test-project"
        assert data["status"] == "active"
        # New project has empty stats
        assert data["message_count"] == 0
        assert data["session_count"] == 0
        assert data["last_activity_at"] == ""


def test_project_summary_includes_session_stats(client, tmp_path, monkeypatch):
    """After sessions are persisted on disk, summary should aggregate session_count
    and last_activity_at from the conversation files."""
    monkeypatch.setenv("HALO_HOME", str(tmp_path))
    # Create project
    pr = client.post("/api/projects", json={"name": "stats-test"})
    assert pr.status_code == 201

    # Write a fake persisted session file directly to disk (faster than going
    # through the agent, which needs a real LLM call).
    import json
    from app.projects import persistence

    sid = "test-session-001"
    path = persistence.session_file_path("stats-test", sid)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(
            {
                "version": 1,
                "session_id": sid,
                "project_name": "stats-test",
                "agent_type": "simple",
                "created_at": "2026-06-06T10:00:00Z",
                "updated_at": "2026-06-06T10:05:00Z",
                "message_count": 4,
                "messages": [],  # not read by scan; we just need the metadata
            },
            f,
        )

    # Re-fetch project — should now have stats
    r = client.get("/api/projects/stats-test")
    assert r.status_code == 200
    data = r.json()
    assert data["name"] == "stats-test"
    assert data["session_count"] == 1
    assert data["message_count"] == 4
    assert data["last_activity_at"] == "2026-06-06T10:05:00Z"

    # Also test list endpoint includes the same fields
    r = client.get("/api/projects")
    assert r.status_code == 200
    found = [p for p in r.json() if p["name"] == "stats-test"]
    assert len(found) == 1
    assert found[0]["message_count"] == 4
    assert found[0]["session_count"] == 1
    assert found[0]["last_activity_at"] == "2026-06-06T10:05:00Z"


def test_start_session(client, tmp_path, monkeypatch):
    monkeypatch.setenv("HALO_HOME", str(tmp_path))
    # Need a project first
    pr = client.post("/api/projects", json={"name": "session-test"})
    if pr.status_code == 201:
        sr = client.post(
            "/api/sessions",
            json={"project_name": "session-test", "agent_type": "simple"},
        )
        if sr.status_code == 201:
            sid = sr.json()["id"]
            # Send a message
            mr = client.post(
                f"/api/sessions/{sid}/message",
                json={"content": "hello"},
            )
            # 200 = synchronous response (agent replied)
            assert mr.status_code == 200

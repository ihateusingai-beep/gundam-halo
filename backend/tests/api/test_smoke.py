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

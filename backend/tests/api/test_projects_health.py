"""API test: ``GET /api/projects/health`` — the M14-T1 health probe.

We boot a fresh ``TestClient`` per test (with the autouse
``default_test_config`` pointing ``HALO_HOME`` at ``tmp_path``)
and verify the probe reflects the live state of the on-disk
projects directory.

Note: this test does NOT inherit the api/conftest.py that
disables the FAISS vector index — it doesn't need to touch
memory and avoids the cross-module coupling.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from app.main import create_app
from fastapi.testclient import TestClient


@pytest.fixture
def client() -> TestClient:
    """Boot the real app. The autouse ``default_test_config``
    fixture points ``HALO_HOME`` at ``tmp_path`` so each test
    gets a fresh projects root."""
    app = create_app()
    with TestClient(app) as c:
        yield c


def test_health_probe_returns_zero_when_no_projects(client: TestClient):
    r = client.get("/api/projects/health")
    assert r.status_code == 200
    body = r.json()
    assert body == {"ok": True, "count": 0}


def test_health_probe_reflects_live_state(client: TestClient, tmp_path: Path):
    """Create a project directory + project.toml by hand, then the
    probe should see count == 1."""
    projects = tmp_path / "projects"
    projects.mkdir(exist_ok=True)
    (projects / "demo").mkdir()
    (projects / "demo" / "project.toml").write_text(
        '[project]\n'
        'name = "demo"\n'
        'created_at = "2026-06-13T10:00:00Z"\n'
        'status = "active"\n'
        'agent_type = "native_react"\n'
        'default_paths = []\n'
        'allowed_apps = []\n'
    )
    r = client.get("/api/projects/health")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "count": 1}


def test_health_probe_skips_corrupt_projects(client: TestClient, tmp_path: Path):
    """Corrupt project.toml must not break the probe — it counts
    only well-formed projects and skips the rest with a warning."""
    projects = tmp_path / "projects"
    projects.mkdir(exist_ok=True)
    (projects / "good").mkdir()
    (projects / "good" / "project.toml").write_text(
        '[project]\nname = "good"\n'
        'created_at = "2026-06-13T10:00:00Z"\n'
        'status = "active"\n'
        'agent_type = "native_react"\n'
        'default_paths = []\n'
        'allowed_apps = []\n'
    )
    (projects / "bad").mkdir()
    (projects / "bad" / "project.toml").write_text("this is not = = valid toml")
    r = client.get("/api/projects/health")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "count": 1}

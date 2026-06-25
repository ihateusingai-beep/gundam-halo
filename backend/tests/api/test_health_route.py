"""Sprint 42 — /api/health route tests.

Verifies the Bug 2 fix: `health.router` is mounted at
`/api/health` (Sprint 42 convention) with the legacy bare
`/health` mount preserved via `health.legacy_router`.
"""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch, tmp_path):
    """Fresh HALO_HOME → backend with health router at both prefixes."""
    monkeypatch.setenv("HALO_HOME", str(tmp_path))
    monkeypatch.setenv("MINIMAX_API_KEY", "test-fake")

    # Reset cached config so HALO_HOME change takes effect.
    from app.core import config as config_mod
    config_mod.reset_config()

    from app.main import create_app
    return TestClient(create_app())


def test_api_health_returns_200(client):
    """GET /api/health → 200 OK with status=ok."""
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["name"] == "gundam-halo"
    # Version is whatever's currently in app/__init__.py
    from app import __version__
    assert body["version"] == __version__


def test_health_legacy_alias_returns_200(client):
    """GET /health (legacy bare mount) returns the same payload."""
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"


def test_api_health_with_trailing_slash(client):
    """Trailing slash is tolerated (FastAPI default redirect behavior)."""
    r = client.get("/api/health/")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_api_health_not_exposed_in_openapi_legacy_route():
    """The legacy `/health` route is `include_in_schema=False`
    (kept off the canonical OpenAPI surface — only `/api/health`
    is documented for API consumers)."""
    from app.api import health as health_mod
    legacy_routes = [
        r for r in health_mod.legacy_router.routes
        if hasattr(r, "include_in_schema")
    ]
    assert legacy_routes, "legacy router should have routes"
    for r in legacy_routes:
        assert r.include_in_schema is False, (
            f"Legacy route {r.path} should be hidden from OpenAPI"
        )

    canonical_routes = [
        r for r in health_mod.router.routes
        if hasattr(r, "include_in_schema")
    ]
    for r in canonical_routes:
        # Default is True for FastAPI; we just check the legacy
        # router's flag is the explicit difference.
        assert r.include_in_schema is not False

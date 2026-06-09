"""Tests for /api/memory — the user memory viewer (M7-Phase-2.5)."""

from __future__ import annotations

import pytest


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from app.main import halo_app

    return TestClient(halo_app)


pytestmark = pytest.mark.usefixtures("permissive_test_config")


def test_list_users_empty(client, tmp_path, monkeypatch):
    monkeypatch.setenv("HALO_HOME", str(tmp_path))
    r = client.get("/api/memory")
    assert r.status_code == 200
    assert r.json() == {"users": []}


def test_list_users_with_data(client, tmp_path, monkeypatch):
    monkeypatch.setenv("HALO_HOME", str(tmp_path))
    from app.memory.user_memory import get_user_memory_store

    store = get_user_memory_store()
    store.set("ken", "preferred_name", "Ken")
    store.set("alice", "timezone", "UTC")

    r = client.get("/api/memory")
    assert r.status_code == 200
    assert sorted(r.json()["users"]) == ["alice", "ken"]


def test_list_user_entries(client, tmp_path, monkeypatch):
    monkeypatch.setenv("HALO_HOME", str(tmp_path))
    from app.memory.user_memory import get_user_memory_store

    store = get_user_memory_store()
    store.set("ken", "preferred_name", "Ken")
    store.set("ken", "timezone", "Asia/Hong_Kong")

    r = client.get("/api/memory/ken")
    assert r.status_code == 200
    data = r.json()
    assert data["user"] == "ken"
    keys = {e["key"] for e in data["entries"]}
    assert keys == {"preferred_name", "timezone"}
    # All entries have value
    for e in data["entries"]:
        assert "value" in e
        assert "updated_at" in e
        assert "created_at" in e


def test_list_user_entries_empty(client, tmp_path, monkeypatch):
    monkeypatch.setenv("HALO_HOME", str(tmp_path))
    r = client.get("/api/memory/nobody")
    assert r.status_code == 200
    assert r.json() == {"user": "nobody", "entries": []}


def test_read_entry_ok(client, tmp_path, monkeypatch):
    monkeypatch.setenv("HALO_HOME", str(tmp_path))
    from app.memory.user_memory import get_user_memory_store

    store = get_user_memory_store()
    store.set("ken", "preferred_name", "Ken")

    r = client.get("/api/memory/ken/preferred_name")
    assert r.status_code == 200
    data = r.json()
    assert data["key"] == "preferred_name"
    assert data["value"] == "Ken"


def test_read_entry_404(client, tmp_path, monkeypatch):
    monkeypatch.setenv("HALO_HOME", str(tmp_path))
    r = client.get("/api/memory/ken/nope")
    assert r.status_code == 404


def test_delete_entry(client, tmp_path, monkeypatch):
    monkeypatch.setenv("HALO_HOME", str(tmp_path))
    from app.memory.user_memory import get_user_memory_store

    store = get_user_memory_store()
    store.set("ken", "preferred_name", "Ken")

    r = client.delete("/api/memory/ken/preferred_name")
    assert r.status_code == 200
    assert r.json() == {"deleted": True, "user": "ken", "key": "preferred_name"}

    # Confirm gone
    assert store.get("ken", "preferred_name") is None


def test_delete_entry_404(client, tmp_path, monkeypatch):
    monkeypatch.setenv("HALO_HOME", str(tmp_path))
    r = client.delete("/api/memory/ken/nope")
    assert r.status_code == 404

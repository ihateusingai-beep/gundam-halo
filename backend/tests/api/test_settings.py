"""Tests for /api/settings endpoints (sanitized config + audit log)."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


# All tests in this module need permissive policy
pytestmark = pytest.mark.usefixtures("permissive_test_config")


def test_get_settings_sanitized(client):
    """GET /api/settings should return the full config with secrets masked."""
    r = client.get("/api/settings")
    assert r.status_code == 200
    data = r.json()

    # Top-level sections
    assert "app" in data
    assert "user" in data
    assert "llm" in data
    assert "server" in data
    assert "mac" in data
    assert "telegram" in data
    assert "security" in data

    # App section
    assert data["app"]["version"] == "0.1.0"
    assert "home" in data["app"]

    # LLM section — secret masked as boolean
    assert "api_key_configured" in data["llm"]
    assert "api_key" not in data["llm"]  # plaintext MUST NOT be present
    assert "base_url" in data["llm"]
    assert "default_model" in data["llm"]

    # Telegram section — secret masked as boolean
    assert "bot_token_configured" in data["telegram"]
    assert "bot_token" not in data["telegram"]  # plaintext MUST NOT be present
    assert "allowed_chat_ids" in data["telegram"]

    # Mac section — file paths and shell allowlist
    assert "file_read_paths" in data["mac"]
    assert "file_write_paths" in data["mac"]
    assert "shell_allowlist" in data["mac"]
    assert isinstance(data["mac"]["a11y_enabled"], bool)

    # Security section
    assert "audit_log" in data["security"]
    assert "injection_scan" in data["security"]


def test_settings_includes_default_mac_policy(client):
    """The default Mac policy (project_only, default allowlist) is exposed."""
    r = client.get("/api/settings")
    assert r.status_code == 200
    mac = r.json()["mac"]
    assert mac["default_path_policy"] in ("project_only", "user_home", "allowlist")
    # Default allowlist should have common commands
    assert "git" in mac["shell_allowlist"]
    assert "ls" in mac["shell_allowlist"]


def test_get_audit_returns_list(client):
    """/api/settings/audit should return a JSON list (most recent first)."""
    r = client.get("/api/settings/audit")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    # If there's any data, each entry should have id/ts/event_type/data
    for entry in data:
        assert "id" in entry
        assert "ts" in entry
        assert "event_type" in entry
        assert "data" in entry
    # Note: when many entries share the same timestamp (rapid test runs),
    # strict ordering isn't guaranteed — just verify it's a valid list.


def test_get_audit_returns_entries(client, tmp_path, monkeypatch):
    """When audit log has entries, they come back most-recent-first."""
    # Write a fake NDJSON audit log directly to where the config says it should be
    r0 = client.get("/api/settings")
    audit_path = Path(r0.json()["security"]["audit_log"]).expanduser()
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    import time

    with open(audit_path, "w") as f:
        f.write(json.dumps({
            "id": "a1",
            "ts": "2026-06-06T10:00:00+00:00",
            "event_type": "mac_op_audit",
            "data": {"action": "file_read", "target": "/tmp/x.txt"},
        }) + "\n")
        f.write(json.dumps({
            "id": "a2",
            "ts": "2026-06-06T10:01:00+00:00",
            "event_type": "mac_op_audit",
            "data": {"action": "shell_exec", "target": "ls"},
        }) + "\n")
        f.flush()

    r = client.get("/api/settings/audit?limit=10")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2
    # Most recent first
    assert data[0]["id"] == "a2"
    assert data[1]["id"] == "a1"
    assert data[0]["event_type"] == "mac_op_audit"


def test_get_audit_respects_limit(client, tmp_path, monkeypatch):
    """limit param caps the number of returned entries."""
    r0 = client.get("/api/settings")
    audit_path = Path(r0.json()["security"]["audit_log"]).expanduser()
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    with open(audit_path, "w") as f:
        for i in range(20):
            f.write(json.dumps({
                "id": f"a{i}",
                "ts": f"2026-06-06T10:00:{i:02d}+00:00",
                "event_type": "mac_op_audit",
                "data": {"i": i},
            }) + "\n")

    r = client.get("/api/settings/audit?limit=5")
    assert r.status_code == 200
    assert len(r.json()) == 5


def test_get_audit_limit_bounds(client):
    """limit param rejects out-of-range values."""
    r = client.get("/api/settings/audit?limit=0")
    assert r.status_code == 422
    r = client.get("/api/settings/audit?limit=99999")
    assert r.status_code == 422

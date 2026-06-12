"""Tests for the M11 mac-control endpoints in `app/api/mac.py`.

Covers:
- AppleScript endpoint
- Clipboard read/write
- Notifications
- Spotlight
- Accessibility API

These tests mock `subprocess.run` (and the underlying mac/* modules
in some cases) so they run on Linux/Windows CI without osascript /
pbcopy / pbpaste / mdfind / System Events being installed.
"""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest


def _mock_completed_process(returncode=0, stdout="", stderr=""):
    cp = MagicMock()
    cp.returncode = returncode
    cp.stdout = stdout
    cp.stderr = stderr
    return cp


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from app.main import halo_app
    return TestClient(halo_app)


pytestmark = pytest.mark.usefixtures("permissive_test_config")


# --- AppleScript ---


def test_apple_script_endpoint_ok(client):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = _mock_completed_process(
            returncode=0, stdout="ok", stderr=""
        )
        r = client.post(
            "/api/mac/apple-script",
            json={"script": 'tell application "Finder" to get name'},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["exit_code"] == 0
    assert body["stdout"] == "ok"


def test_apple_script_endpoint_empty_rejected(client):
    r = client.post("/api/mac/apple-script", json={"script": ""})
    assert r.status_code == 400


def test_apple_script_endpoint_disabled_403(client, monkeypatch):
    from app.core import config as _config_module
    cfg = _config_module.get_config()
    cfg.mac.apple_script_enabled = False
    try:
        r = client.post(
            "/api/mac/apple-script",
            json={"script": 'tell application "Finder" to get name'},
        )
    finally:
        cfg.mac.apple_script_enabled = True
    assert r.status_code == 403


# --- Clipboard ---


def test_clipboard_read_endpoint(client):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = _mock_completed_process(stdout="clip text")
        r = client.get("/api/mac/clipboard")
    assert r.status_code == 200
    body = r.json()
    assert body["text"] == "clip text"
    assert body["bytes"] == 9


def test_clipboard_write_endpoint(client):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = _mock_completed_process()
        r = client.post("/api/mac/clipboard", json={"text": "hello"})
    assert r.status_code == 200
    body = r.json()
    assert body["bytes"] == 5
    assert body["status"] == "written"


def test_clipboard_write_empty_rejected(client):
    # Pydantic validation rejects the wrong type (123) before the
    # endpoint runs — FastAPI returns 422.
    r = client.post("/api/mac/clipboard", json={"text": 123})
    assert r.status_code == 422


# --- Notifications ---


def test_notify_endpoint_ok(client):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = _mock_completed_process()
        r = client.post(
            "/api/mac/notify",
            json={"text": "Task done", "title": "Build", "subtitle": "3s"},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["exit_code"] == 0


def test_notify_endpoint_empty_rejected(client):
    r = client.post("/api/mac/notify", json={"text": ""})
    assert r.status_code == 400


def test_notify_endpoint_disabled_403(client, monkeypatch):
    from app.core import config as _config_module
    cfg = _config_module.get_config()
    cfg.mac.notifications_enabled = False
    try:
        r = client.post("/api/mac/notify", json={"text": "hi"})
    finally:
        cfg.mac.notifications_enabled = True
    assert r.status_code == 403


# --- Spotlight ---


def test_spotlight_endpoint_ok(client):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = _mock_completed_process(
            stdout="/a.md\n/b.md\n/c.md"
        )
        r = client.post(
            "/api/mac/spotlight", json={"query": "kind:pdf", "max_results": 10}
        )
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 3
    assert body["results"] == ["/a.md", "/b.md", "/c.md"]


def test_spotlight_endpoint_empty_rejected(client):
    r = client.post("/api/mac/spotlight", json={"query": ""})
    assert r.status_code == 400


def test_spotlight_endpoint_only_in(client):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = _mock_completed_process(stdout="")
        r = client.post(
            "/api/mac/spotlight",
            json={"query": "foo", "only_in": "/Users/ken/Documents"},
        )
    assert r.status_code == 200
    # Verify -onlyin was used
    args = mock_run.call_args[0][0]
    assert "-onlyin" in args
    assert "/Users/ken/Documents" in args


# --- Accessibility ---


@pytest.fixture(autouse=False)
def a11y_on():
    from app.core import config as _config_module
    cfg = _config_module.get_config()
    original = cfg.mac.a11y_enabled
    cfg.mac.a11y_enabled = True
    yield
    cfg.mac.a11y_enabled = original


def test_a11y_endpoint_windows(client, a11y_on):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = _mock_completed_process(stdout="Win A,Win B")
        r = client.post("/api/mac/a11y", json={"operation": "windows"})
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 2
    assert body["items"] == ["Win A", "Win B"]


def test_a11y_endpoint_focused(client, a11y_on):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = _mock_completed_process(stdout="Terminal")
        r = client.post("/api/mac/a11y", json={"operation": "focused"})
    assert r.status_code == 200
    assert r.json()["result"] == "Terminal"


def test_a11y_endpoint_query(client, a11y_on):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = _mock_completed_process(stdout="42")
        r = client.post(
            "/api/mac/a11y",
            json={
                "operation": "query",
                "script": 'tell application "System Events" to return 42',
            },
        )
    assert r.status_code == 200
    assert r.json()["result"] == "42"


def test_a11y_endpoint_query_rejects_non_system_events_script(client, a11y_on):
    r = client.post(
        "/api/mac/a11y",
        json={"operation": "query", "script": "return 42"},
    )
    assert r.status_code == 400


def test_a11y_endpoint_unknown_op(client, a11y_on):
    r = client.post("/api/mac/a11y", json={"operation": "frobnicate"})
    assert r.status_code == 400


def test_a11y_endpoint_disabled_403(client):
    """Without a11y_on fixture, a11y_enabled is False → 403."""
    from app.core import config as _config_module
    cfg = _config_module.get_config()
    cfg.mac.a11y_enabled = False
    try:
        r = client.post("/api/mac/a11y", json={"operation": "windows"})
    finally:
        cfg.mac.a11y_enabled = True
    assert r.status_code == 403

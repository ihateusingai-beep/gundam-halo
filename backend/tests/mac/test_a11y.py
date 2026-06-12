"""Tests for the Accessibility wrapper (`app.mac.a11y`).

Note: A11y is read-only by design (synthetic input is out of v0.1.x
scope). These tests verify the policy gate + that osascript is
invoked with the right System Events tell blocks.
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


pytestmark = pytest.mark.usefixtures("permissive_test_config")


# A11y is OFF by default — flip it on for these tests
@pytest.fixture(autouse=True)
def enable_a11y(monkeypatch):
    from app.core import config as _config_module
    cfg = _config_module.get_config()
    original = cfg.mac.a11y_enabled
    cfg.mac.a11y_enabled = True
    yield
    cfg.mac.a11y_enabled = original


def test_a11y_window_list_uses_system_events():
    from app.mac.a11y import a11y_window_list

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = _mock_completed_process(
            stdout="Window 1,Window 2,Window 3"
        )
        result = a11y_window_list()
    args = mock_run.call_args[0][0]
    assert args[0] == "osascript"
    assert "System Events" in args[2]
    assert "window" in args[2]
    assert result["count"] == 3
    assert "Window 1" in result["items"]
    assert "Window 2" in result["items"]


def test_a11y_app_processes():
    from app.mac.a11y import a11y_app_processes

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = _mock_completed_process(stdout="Safari,Finder,Terminal")
        result = a11y_app_processes()
    assert result["count"] == 3
    assert "Safari" in result["items"]


def test_a11y_focused_app():
    from app.mac.a11y import a11y_focused_app

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = _mock_completed_process(stdout="Visual Studio Code")
        result = a11y_focused_app()
    assert "Visual Studio Code" in result["result"]


def test_a11y_query_requires_system_events():
    from app.mac.a11y import a11y_query

    with pytest.raises(ValueError, match="System Events"):
        a11y_query("return 42")  # no System Events reference


def test_a11y_query_accepts_valid_script():
    from app.mac.a11y import a11y_query

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = _mock_completed_process(stdout="42")
        result = a11y_query('tell application "System Events" to return 42')
    assert result["result"] == "42"


def test_a11y_query_rejects_empty():
    from app.mac.a11y import a11y_query

    with pytest.raises(ValueError, match="empty"):
        a11y_query("")


def test_a11y_disabled_raises_for_all_operations():
    """All four A11y entry points must respect a11y_enabled = false."""
    from app.core import config as _config_module
    from app.mac.a11y import (
        a11y_app_processes,
        a11y_focused_app,
        a11y_query,
        a11y_window_list,
    )

    cfg = _config_module.get_config()
    cfg.mac.a11y_enabled = False
    try:
        for fn, args in [
            (a11y_window_list, ()),
            (a11y_app_processes, ()),
            (a11y_focused_app, ()),
            (a11y_query, ('tell application "System Events" to return 1',)),
        ]:
            with pytest.raises(PermissionError, match="disabled"):
                fn(*args)
    finally:
        cfg.mac.a11y_enabled = True


# --- Tool class tests ---


def test_a11y_tool_windows():
    import asyncio
    from app.tools.a11y import A11yTool

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = _mock_completed_process(stdout="Win A,Win B")
        result = asyncio.run(A11yTool().run(operation="windows"))
    assert "2 visible windows" in result or "Found 2" in result
    assert "Win A" in result


def test_a11y_tool_processes():
    import asyncio
    from app.tools.a11y import A11yTool

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = _mock_completed_process(stdout="Finder")
        result = asyncio.run(A11yTool().run(operation="processes"))
    assert "Finder" in result


def test_a11y_tool_focused():
    import asyncio
    from app.tools.a11y import A11yTool

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = _mock_completed_process(stdout="Terminal")
        result = asyncio.run(A11yTool().run(operation="focused"))
    assert "Terminal" in result


def test_a11y_tool_query():
    import asyncio
    from app.tools.a11y import A11yTool

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = _mock_completed_process(stdout="42")
        result = asyncio.run(
            A11yTool().run(
                operation="query",
                script='tell application "System Events" to return 42',
            )
        )
    assert "42" in result


def test_a11y_tool_query_missing_script():
    import asyncio
    from app.tools.a11y import A11yTool

    result = asyncio.run(A11yTool().run(operation="query"))
    assert "Error" in result


def test_a11y_tool_unknown_op():
    import asyncio
    from app.tools.a11y import A11yTool

    result = asyncio.run(A11yTool().run(operation="frobnicate"))
    assert "Error" in result


def test_a11y_tool_disabled():
    import asyncio
    from app.core import config as _config_module
    from app.tools.a11y import A11yTool

    cfg = _config_module.get_config()
    cfg.mac.a11y_enabled = False
    try:
        result = asyncio.run(A11yTool().run(operation="windows"))
    finally:
        cfg.mac.a11y_enabled = True
    assert "Error" in result
    assert "disabled" in result

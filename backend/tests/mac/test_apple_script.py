"""Tests for the AppleScript wrapper (`app.mac.apple_script`).

We mock `subprocess.run` so these tests run on Linux/Windows CI
without `osascript` being installed. The actual osascript behavior
is exercised on macOS dev only.
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


# All tests use permissive config to enable the apple_script flag
pytestmark = pytest.mark.usefixtures("permissive_test_config")


def test_apple_script_runs_ok():
    from app.mac.apple_script import run_applescript

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = _mock_completed_process(
            returncode=0, stdout="https://example.com", stderr=""
        )
        result = run_applescript('tell application "Safari" to get URL of front document')

    assert result["exit_code"] == 0
    assert result["stdout"] == "https://example.com"
    assert result["stderr"] == ""
    assert "duration_ms" in result
    # Subprocess should have been called with the right argv
    args = mock_run.call_args[0][0]
    assert args[0] == "osascript"
    assert args[1] == "-e"
    assert 'tell application "Safari"' in args[2]


def test_apple_script_handles_nonzero_exit():
    from app.mac.apple_script import run_applescript

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = _mock_completed_process(
            returncode=1, stdout="", stderr="execution error"
        )
        result = run_applescript('tell application "Nonexistent" to do thing')

    assert result["exit_code"] == 1
    assert result["stderr"] == "execution error"


def test_apple_script_timeout_returns_structured_error():
    import subprocess
    from app.mac.apple_script import run_applescript

    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["osascript"], timeout=5)
        result = run_applescript('do something', timeout=5)

    assert result["exit_code"] == -1
    assert "Timeout" in result["stderr"]


def test_apple_script_rejects_empty():
    from app.mac.apple_script import run_applescript

    with pytest.raises(ValueError, match="empty"):
        run_applescript("")


def test_apple_script_rejects_whitespace_only():
    from app.mac.apple_script import run_applescript

    with pytest.raises(ValueError, match="empty"):
        run_applescript("   \n\t  ")


def test_apple_script_disabled_by_config(monkeypatch, tmp_path):
    """If apple_script_enabled = False, raise PermissionError."""
    from app.core import config as _config_module
    cfg = _config_module.get_config()
    cfg.mac.apple_script_enabled = False
    try:
        from app.mac.apple_script import run_applescript
        with pytest.raises(PermissionError, match="disabled"):
            run_applescript('do thing')
    finally:
        cfg.mac.apple_script_enabled = True  # restore for next tests


def test_apple_script_missing_osascript_raises_runtime_error():
    from app.mac.apple_script import run_applescript

    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = FileNotFoundError("osascript not found")
        with pytest.raises(RuntimeError, match="osascript"):
            run_applescript('do thing')


# --- Tool class test ---


def test_apple_script_tool_spec():
    from app.tools.apple_script import AppleScriptTool

    spec = AppleScriptTool().to_spec()
    assert spec["function"]["name"] == "apple_script"
    assert "script" in spec["function"]["parameters"]["required"]


def test_apple_script_tool_runs_via_subprocess():
    """End-to-end of the tool class — it should call osascript under the hood."""
    import asyncio
    from app.tools.apple_script import AppleScriptTool

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = _mock_completed_process(
            returncode=0, stdout="42", stderr=""
        )
        result = asyncio.run(AppleScriptTool().run(script="return 42"))
    assert "42" in result


def test_apple_script_tool_surfaces_disabled():
    """If apple_script_enabled = False, the tool returns Error: ... instead of raising."""
    import asyncio
    from app.core import config as _config_module
    from app.tools.apple_script import AppleScriptTool

    cfg = _config_module.get_config()
    cfg.mac.apple_script_enabled = False
    try:
        result = asyncio.run(AppleScriptTool().run(script="do thing"))
    finally:
        cfg.mac.apple_script_enabled = True
    assert "Error" in result
    assert "disabled" in result

"""Tests for the brightness tool.

We mock the AppleScript bridge (`app.mac.apple_script.run_applescript`)
so the tests run on any platform without needing macOS / System
Events permission. The mock returns a canned exit code + stdout;
the tool's logic (parsing, error handling) is what's under test.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.tools.brightness import BrightnessTool


def _mock_apple_script(side_effect):
    """Patch `app.mac.apple_script.run_applescript`. The brightness
    tool does a lazy import inside `run`, so the attribute is
    resolved at call time, not module-load time."""
    return patch("app.mac.apple_script.run_applescript", side_effect=side_effect)


def _ok(stdout: str):
    return {
        "exit_code": 0,
        "stdout": stdout,
        "stderr": "",
        "duration_ms": 5,
    }


def _fail(exit_code: int, stderr: str = "osascript error"):
    return {
        "exit_code": exit_code,
        "stdout": "",
        "stderr": stderr,
        "duration_ms": 5,
    }


@pytest.mark.asyncio
async def test_get_returns_int_percent():
    with _mock_apple_script(lambda **_: _ok("75")):
        result = await BrightnessTool().run(operation="get")
    assert result == "Main display brightness: 75%"


@pytest.mark.asyncio
async def test_get_handles_float_output():
    """Some macOS versions return a float."""
    with _mock_apple_script(lambda **_: _ok("75.4")):
        result = await BrightnessTool().run(operation="get")
    assert "75" in result
    assert "%" in result


@pytest.mark.asyncio
async def test_get_handles_garbled_output():
    """If AppleScript returns a non-numeric string, surface the raw
    value rather than crash."""
    with _mock_apple_script(lambda **_: _ok("unknown")):
        result = await BrightnessTool().run(operation="get")
    assert "could not parse" in result
    assert "unknown" in result


@pytest.mark.asyncio
async def test_set_within_range():
    with _mock_apple_script(lambda **_: _ok("")):
        result = await BrightnessTool().run(operation="set", level=50)
    assert result == "OK: main display brightness set to 50%"


@pytest.mark.asyncio
async def test_set_rejects_out_of_range():
    # We never even call AppleScript for this case.
    result = await BrightnessTool().run(operation="set", level=150)
    assert "Error" in result
    assert "0 and 100" in result


@pytest.mark.asyncio
async def test_set_rejects_negative():
    result = await BrightnessTool().run(operation="set", level=-1)
    assert "Error" in result


@pytest.mark.asyncio
async def test_get_osascript_failure():
    with _mock_apple_script(lambda **_: _fail(1, "permission denied")):
        result = await BrightnessTool().run(operation="get")
    assert "Error" in result
    assert "permission denied" in result


@pytest.mark.asyncio
async def test_set_osascript_failure():
    with _mock_apple_script(lambda **_: _fail(1)):
        result = await BrightnessTool().run(operation="set", level=50)
    assert "Error" in result


@pytest.mark.asyncio
async def test_unknown_op():
    result = await BrightnessTool().run(operation="nope")
    assert "Error" in result
    assert "nope" in result

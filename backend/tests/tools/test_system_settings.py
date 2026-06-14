"""Tests for the system_settings tool.

We mock `defaults` via `subprocess.run` so the tests are platform-
independent. The tool's logic (DND round-trip, key validation,
status read fallback) is what's under test.
"""
from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest

from app.tools.system_settings import SystemSettingsTool


def _mock_defaults(stdout: str = "", stderr: str = "", returncode: int = 0):
    cp = subprocess.CompletedProcess(
        args=(), returncode=returncode, stdout=stdout, stderr=stderr
    )
    return patch("subprocess.run", return_value=cp)


@pytest.mark.asyncio
async def test_dnd_enable_calls_defaults_twice():
    """We write both the new (FocusModes) and old (doNotDisturb)
    keys for backward compatibility."""
    captured_args: list = []
    real_run = subprocess.run

    def fake_run(args, **kwargs):
        captured_args.append(args)
        return real_run(
            ["true"], capture_output=True, text=True, timeout=1, check=False
        )

    with patch("subprocess.run", side_effect=fake_run):
        result = await SystemSettingsTool().run(operation="dnd", enabled=True)
    assert "OK" in result
    assert "enabled" in result
    # We expect at least 2 writes (FocusModes + doNotDisturb) + a read
    assert any("NSStatusItem Visible FocusModes" in str(a) for a in captured_args)
    assert any("doNotDisturb" in str(a) for a in captured_args)


@pytest.mark.asyncio
async def test_dnd_disable():
    with _mock_defaults():
        result = await SystemSettingsTool().run(operation="dnd", enabled=False)
    assert "OK" in result
    assert "disabled" in result


@pytest.mark.asyncio
async def test_dnd_requires_enabled():
    result = await SystemSettingsTool().run(operation="dnd")
    assert "Error" in result
    assert "enabled" in result


@pytest.mark.asyncio
async def test_dnd_defaults_write_failure():
    cp = subprocess.CompletedProcess(
        args=(), returncode=1, stdout="", stderr="boom"
    )
    with patch("subprocess.run", return_value=cp):
        result = await SystemSettingsTool().run(operation="dnd", enabled=True)
    assert "Error" in result
    assert "boom" in result


@pytest.mark.asyncio
async def test_dnd_status_returns_enabled():
    cp = subprocess.CompletedProcess(
        args=(), returncode=0, stdout="1\n", stderr=""
    )
    with patch("subprocess.run", return_value=cp):
        result = await SystemSettingsTool().run(operation="dnd_status")
    assert "enabled" in result


@pytest.mark.asyncio
async def test_dnd_status_returns_disabled():
    cp = subprocess.CompletedProcess(
        args=(), returncode=0, stdout="0\n", stderr=""
    )
    with patch("subprocess.run", return_value=cp):
        result = await SystemSettingsTool().run(operation="dnd_status")
    assert "disabled" in result


@pytest.mark.asyncio
async def test_dnd_status_falls_back_to_legacy_key():
    """Older macOS doesn't have NSStatusItem Visible FocusModes;
    the tool should fall back to the doNotDisturb key."""
    call_count = {"n": 0}

    def fake_run(args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return subprocess.CompletedProcess(
                args=(), returncode=1, stdout="", stderr=""
            )
        return subprocess.CompletedProcess(
            args=(), returncode=0, stdout="0\n", stderr=""
        )

    with patch("subprocess.run", side_effect=fake_run):
        result = await SystemSettingsTool().run(operation="dnd_status")
    assert "disabled" in result


@pytest.mark.asyncio
async def test_get_requires_both_args():
    result = await SystemSettingsTool().run(operation="get")
    assert "Error" in result


@pytest.mark.asyncio
async def test_get_reads_value():
    cp = subprocess.CompletedProcess(
        args=(), returncode=0, stdout="Dark\n", stderr=""
    )
    with patch("subprocess.run", return_value=cp):
        result = await SystemSettingsTool().run(
            operation="get", domain="NSGlobalDomain", key="AppleInterfaceStyle"
        )
    assert "NSGlobalDomain" in result
    assert "AppleInterfaceStyle" in result
    assert "Dark" in result


@pytest.mark.asyncio
async def test_get_reads_failure():
    cp = subprocess.CompletedProcess(
        args=(), returncode=1, stdout="", stderr="key not found"
    )
    with patch("subprocess.run", return_value=cp):
        result = await SystemSettingsTool().run(
            operation="get", domain="NSGlobalDomain", key="Bogus"
        )
    assert "Error" in result
    assert "key not found" in result


@pytest.mark.asyncio
async def test_unknown_op():
    result = await SystemSettingsTool().run(operation="nope")
    assert "Error" in result
    assert "nope" in result

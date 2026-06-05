"""Tests for the shell_exec tool."""
import os
import pytest

from app.tools.shell_exec import ShellExecTool


@pytest.fixture
def tool():
    return ShellExecTool()


# All tests in this module need permissive policy
pytestmark = pytest.mark.usefixtures("permissive_test_config")


def test_spec_format(tool):
    spec = tool.to_spec()
    assert spec["function"]["name"] == "shell_exec"
    assert "command" in spec["function"]["parameters"]["required"]


def test_allowed_command(tool):
    """git --version should work (git is in default allowlist)."""
    import asyncio
    result = asyncio.run(tool.run(command="git --version"))
    assert "Exit code" in result
    assert "0" in result  # git --version exits 0


def test_blocked_command(tool):
    """rm is NOT in default allowlist."""
    import asyncio
    result = asyncio.run(tool.run(command="rm -rf /tmp/test"))
    assert "Error" in result


def test_timeout_clamp(tool):
    """timeout_sec should be clamped to [1, 300]."""
    import asyncio
    result = asyncio.run(tool.run(command="ls /tmp", timeout_sec=99999))
    assert "Exit code" in result  # ran successfully, just timeout was clamped

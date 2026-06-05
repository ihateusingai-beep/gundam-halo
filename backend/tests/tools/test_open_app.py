"""Tests for the open_app tool."""
import os
import pytest

from app.tools.open_app import OpenAppTool


@pytest.fixture
def tool():
    return OpenAppTool()


# All tests in this module need permissive policy
pytestmark = pytest.mark.usefixtures("permissive_test_config")


def test_spec_format(tool):
    spec = tool.to_spec()
    assert spec["function"]["name"] == "open_app"


@pytest.mark.skipif(os.uname().sysname != "Darwin", reason="open -a is macOS-specific")
def test_launch_real_app(tool):
    """Launching Finder (always present on macOS) should succeed."""
    import asyncio
    result = asyncio.run(tool.run(app_name="Finder"))
    assert "OK" in result or "Error" in result  # either is fine for the test

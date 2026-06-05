"""Tests for the file_read tool."""
import os
import pytest

from app.tools.file_read import FileReadTool


@pytest.fixture
def tool():
    return FileReadTool()


# All tests in this module need permissive policy
pytestmark = pytest.mark.usefixtures("permissive_test_config")


def test_spec_format(tool):
    spec = tool.to_spec()
    assert spec["type"] == "function"
    assert spec["function"]["name"] == "file_read"
    assert "path" in spec["function"]["parameters"]["properties"]
    assert spec["function"]["parameters"]["required"] == ["path"]


def test_read_existing_file(tool, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    p = tmp_path / "test.txt"
    p.write_text("hello world")
    import asyncio
    result = asyncio.run(tool.run(path=str(p)))
    assert result == "hello world"


def test_read_nonexistent_file(tool):
    import asyncio
    result = asyncio.run(tool.run(path="/nonexistent/file.txt"))
    assert "Error" in result


def test_read_blocked_path(tool):
    """~/.ssh is NEVER readable."""
    import asyncio
    result = asyncio.run(tool.run(path="~/.ssh/id_rsa"))
    assert "Error" in result
    assert "policy" in result


def test_read_truncates_long_content(tool, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    p = tmp_path / "big.txt"
    p.write_text("x" * 60_000)
    import asyncio
    result = asyncio.run(tool.run(path=str(p)))
    assert "truncated" in result

"""Tests for the file_write tool."""
import pytest

from app.tools.file_write import FileWriteTool


@pytest.fixture
def tool():
    return FileWriteTool()


def test_spec_format(tool):
    spec = tool.to_spec()
    assert spec["function"]["name"] == "file_write"
    assert set(spec["function"]["parameters"]["required"]) == {"path", "content"}


def test_write_creates_file(tool, tmp_path, monkeypatch, permissive_test_config):
    monkeypatch.setenv("HOME", str(tmp_path))
    p = tmp_path / "out.txt"
    import asyncio
    result = asyncio.run(tool.run(path=str(p), content="hi"))
    assert "OK" in result
    assert p.read_text() == "hi"


def test_write_blocked_path(tool, tmp_path, monkeypatch, permissive_test_config):
    """~/.ssh is NEVER writable, even when tmp_path is allowed."""
    monkeypatch.setenv("HOME", str(tmp_path))
    import asyncio
    result = asyncio.run(tool.run(path="~/.ssh/authorized_keys", content="evil"))
    assert "Error" in result
    assert "policy" in result


def test_write_blocked_documents(tool, tmp_path, monkeypatch):
    """~/Documents is NOT in default file_write_paths.

    No `permissive_test_config` — uses default policy. tmp_path is not
    in the default allowlist, so the write should be blocked.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    import asyncio
    # tmp_path is NOT in default file_write_paths → should be blocked.
    # We use a path inside tmp_path (e.g. a "Documents" subdir).
    p = tmp_path / "Documents" / "notes.txt"
    p.parent.mkdir(parents=True, exist_ok=True)
    result = asyncio.run(tool.run(path=str(p), content="x"))
    assert "Error" in result
    assert "policy" in result

"""Tests for the clipboard wrapper (`app.mac.clipboard`)."""

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


def test_read_clipboard_returns_text():
    from app.mac.clipboard import read_clipboard

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = _mock_completed_process(stdout="hello world")
        result = read_clipboard()
    assert result == "hello world"


def test_read_clipboard_returns_empty_on_nonzero():
    """pbpaste exits 1 when clipboard doesn't hold plain text — return "". """
    from app.mac.clipboard import read_clipboard

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = _mock_completed_process(returncode=1)
        result = read_clipboard()
    assert result == ""


def test_read_clipboard_handles_timeout():
    import subprocess
    from app.mac.clipboard import read_clipboard

    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["pbpaste"], timeout=2)
        assert read_clipboard() == ""


def test_write_clipboard_pipes_text_to_stdin():
    from app.mac.clipboard import write_clipboard

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = _mock_completed_process()
        written = write_clipboard("test value")
    assert written == 10  # len("test value".encode("utf-8"))
    # Verify the call passed the bytes via stdin
    kwargs = mock_run.call_args.kwargs
    assert kwargs["input"] == b"test value"


def test_write_clipboard_rejects_non_string():
    from app.mac.clipboard import write_clipboard

    with pytest.raises(ValueError, match="must be a string"):
        write_clipboard(12345)  # type: ignore[arg-type]


def test_write_clipboard_surfaces_failure():
    from app.mac.clipboard import write_clipboard

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = _mock_completed_process(returncode=1, stderr="err")
        with pytest.raises(RuntimeError, match="pbcopy failed"):
            write_clipboard("text")


def test_write_clipboard_missing_tool_raises():
    from app.mac.clipboard import write_clipboard

    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = FileNotFoundError("pbcopy not found")
        with pytest.raises(RuntimeError, match="pbcopy"):
            write_clipboard("text")


# --- Tool class test ---


def test_clipboard_tool_read():
    import asyncio
    from app.tools.clipboard import ClipboardTool

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = _mock_completed_process(stdout="data")
        result = asyncio.run(ClipboardTool().run(operation="read"))
    assert result == "data"


def test_clipboard_tool_write():
    import asyncio
    from app.tools.clipboard import ClipboardTool

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = _mock_completed_process()
        result = asyncio.run(ClipboardTool().run(operation="write", text="data"))
    assert "OK" in result
    assert "4 bytes" in result


def test_clipboard_tool_write_missing_text():
    import asyncio
    from app.tools.clipboard import ClipboardTool

    result = asyncio.run(ClipboardTool().run(operation="write"))
    assert "Error" in result


def test_clipboard_tool_unknown_op():
    import asyncio
    from app.tools.clipboard import ClipboardTool

    result = asyncio.run(ClipboardTool().run(operation="frobnicate"))
    assert "Error" in result
    assert "unknown operation" in result

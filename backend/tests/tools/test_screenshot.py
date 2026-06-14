"""Tests for the screenshot tool.

We mock `subprocess.run` (the screen capture is OS-level) so the
tests run on any platform. The mock returns a canned CompletedProcess
and the tool's logic (path validation, args building, error
handling) is what's under test.
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from app.tools.screenshot import ScreenshotTool, _default_path


def _mock_run(stdout: str = "", stderr: str = "", returncode: int = 0):
    """Patch subprocess.run inside the screenshot tool."""
    return patch(
        "subprocess.run",
        return_value=__import__("subprocess").CompletedProcess(
            args=(), returncode=returncode, stdout=stdout, stderr=stderr
        ),
    )


@pytest.mark.asyncio
async def test_full_uses_default_path():
    """The default path ends in .png and lives under ~/Desktop."""
    p = _default_path()
    assert p.suffix == ".png"
    assert "Desktop" in str(p)


@pytest.mark.asyncio
async def test_full_capture_writes_file(tmp_path: Path):
    out = tmp_path / "shot.png"
    out.write_bytes(b"\x89PNG\r\n\x1a\n")  # valid PNG magic
    with _mock_run():
        result = await ScreenshotTool().run(
            operation="full", output_path=str(out)
        )
    assert result.startswith("OK:")
    assert "bytes" in result
    assert str(out) in result


@pytest.mark.asyncio
async def test_full_creates_parent_dir(tmp_path: Path):
    out = tmp_path / "nested" / "deeper" / "shot.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(b"\x89PNG\r\n\x1a\n")
    with _mock_run():
        result = await ScreenshotTool().run(
            operation="full", output_path=str(out)
        )
    assert result.startswith("OK:")


@pytest.mark.asyncio
async def test_full_rejects_non_png_extension(tmp_path: Path):
    out = tmp_path / "shot.jpg"
    result = await ScreenshotTool().run(
        operation="full", output_path=str(out)
    )
    assert "Error" in result
    assert ".png" in result


@pytest.mark.asyncio
async def test_full_subprocess_failure(tmp_path: Path):
    out = tmp_path / "shot.png"
    with _mock_run(stderr="screencapture: display not found", returncode=1):
        result = await ScreenshotTool().run(
            operation="full", output_path=str(out)
        )
    assert "Error" in result
    assert "display not found" in result


@pytest.mark.asyncio
async def test_full_zero_byte_output(tmp_path: Path):
    """screencapture returned 0 but produced no file. Common when
    the user denied Screen Recording permission. Should fail with
    a clear message."""
    out = tmp_path / "shot.png"  # file does not exist
    with _mock_run():
        result = await ScreenshotTool().run(
            operation="full", output_path=str(out)
        )
    assert "Error" in result
    assert "no file" in result


@pytest.mark.asyncio
async def test_window_requires_window_name(tmp_path: Path):
    out = tmp_path / "shot.png"
    result = await ScreenshotTool().run(
        operation="window", output_path=str(out)
    )
    assert "Error" in result
    assert "window_name" in result


@pytest.mark.asyncio
async def test_window_passes_window_name(tmp_path: Path):
    out = tmp_path / "shot.png"
    out.write_bytes(b"\x89PNG\r\n\x1a\n")
    # The actual arg list is what we want to verify, not the result.
    captured = {}
    real_run = __import__("subprocess").run

    def fake_run(args, **kwargs):
        captured["args"] = args
        return real_run(
            ["true"], capture_output=True, text=True, timeout=1, check=False
        )

    with patch("subprocess.run", side_effect=fake_run):
        # `true` exits 0 immediately. The tool checks exit code and
        # also the file existence. Provide a file to make it pass.
        result = await ScreenshotTool().run(
            operation="window",
            output_path=str(out),
            window_name="Safari",
        )
    # The command must include `-l Safari` (window selection by name).
    flat = " ".join(str(a) for a in captured["args"])
    assert "-l" in flat and "Safari" in flat, (
        f"expected '-l Safari' in args, got {captured['args']}"
    )


@pytest.mark.asyncio
async def test_region_requires_all_coords(tmp_path: Path):
    out = tmp_path / "shot.png"
    # Missing height
    result = await ScreenshotTool().run(
        operation="region",
        output_path=str(out),
        x=0,
        y=0,
        width=200,
        height=-1,
    )
    assert "Error" in result
    assert "height" in result


@pytest.mark.asyncio
async def test_region_passes_rect(tmp_path: Path):
    out = tmp_path / "shot.png"
    out.write_bytes(b"\x89PNG\r\n\x1a\n")
    captured = {}
    real_run = __import__("subprocess").run

    def fake_run(args, **kwargs):
        captured["args"] = args
        return real_run(
            ["true"], capture_output=True, text=True, timeout=1, check=False
        )

    with patch("subprocess.run", side_effect=fake_run):
        result = await ScreenshotTool().run(
            operation="region",
            output_path=str(out),
            x=100,
            y=200,
            width=300,
            height=400,
        )
    flat = " ".join(str(a) for a in captured["args"])
    assert "-R" in flat and "100,200,300,400" in flat, (
        f"expected '-R 100,200,300,400' in args, got {captured['args']}"
    )


@pytest.mark.asyncio
async def test_unknown_op():
    result = await ScreenshotTool().run(operation="nope")
    assert "Error" in result
    assert "nope" in result

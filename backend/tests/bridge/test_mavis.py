"""Tests for the Mavis bridge."""

import pytest

from app.bridge.mavis import MavisBridge, MavisResult


def test_bridge_dry_run_default():
    b = MavisBridge()
    assert b.mode == "dry_run"


def test_bridge_real_mode_valid():
    b = MavisBridge(mode="real")
    assert b.mode == "real"


def test_bridge_invalid_mode_raises():
    with pytest.raises(ValueError, match="Invalid mode"):
        MavisBridge(mode="invalid")


@pytest.mark.asyncio
async def test_bridge_dry_run_returns_fake_result(tmp_path):
    b = MavisBridge(mode="dry_run")
    project = tmp_path / "myproject"
    project.mkdir()

    result = await b.delegate(
        task="fix the auth bug",
        project_dir=project,
        context={"files": ["src/auth.py"]},
    )

    assert result.success is True
    assert "[DRY-RUN]" in result.summary
    assert result.commit_sha == "[DRY-RUN-no-commit]"
    assert result.pushed is False
    assert "DRY-RUN" in result.raw_output


@pytest.mark.asyncio
async def test_bridge_dry_run_with_nonexistent_dir():
    b = MavisBridge(mode="dry_run")
    result = await b.delegate(
        task="do something",
        project_dir="/nonexistent/path",
    )
    # Project dir validation happens before mode check
    assert result.success is False
    assert "does not exist" in (result.error or "")


@pytest.mark.asyncio
async def test_bridge_real_mode_missing_cli(tmp_path):
    """In real mode, if the Mavis CLI is not installed, return error."""
    b = MavisBridge(mode="real", mavis_cli="definitely-not-a-real-cli-12345")
    project = tmp_path / "myproject"
    project.mkdir()

    result = await b.delegate(
        task="test task",
        project_dir=project,
    )

    assert result.success is False
    assert "Could not find" in (result.error or "")

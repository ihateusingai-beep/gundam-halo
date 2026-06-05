"""Tests for the Mavis bridge (real-mode spawn protocol)."""

import subprocess
from pathlib import Path
from unittest import mock

import pytest

from app.bridge import mavis as mavis_mod
from app.bridge.mavis import MavisBridge, MavisResult, find_mavis_binary


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
async def test_bridge_dry_run_returns_fake_result(tmp_path, permissive_test_config):
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
    assert result.mode == "dry_run"
    assert "DRY-RUN" in result.raw_output


@pytest.mark.asyncio
async def test_bridge_dry_run_with_nonexistent_dir():
    b = MavisBridge(mode="dry_run")
    result = await b.delegate(
        task="do something",
        project_dir="/nonexistent/path",
    )
    assert result.success is False
    assert "does not exist" in (result.error or "")


# ---------------------------------------------------------------------------
# Real mode: auto-detect + fallback
# ---------------------------------------------------------------------------


def test_find_mavis_binary_returns_string_when_present():
    """If hermes or mavis is on PATH, find it."""
    with mock.patch("app.bridge.mavis.shutil.which") as mock_which:
        mock_which.side_effect = lambda name: "/usr/local/bin/hermes" if name == "hermes" else None
        result = find_mavis_binary()
        assert result == "/usr/local/bin/hermes"
        # Should try mavis first
        assert mock_which.call_args_list[0].args[0] == "mavis"
        assert mock_which.call_args_list[1].args[0] == "hermes"


def test_find_mavis_binary_returns_none_when_missing():
    """If neither binary is on PATH, return None."""
    with mock.patch("app.bridge.mavis.shutil.which", return_value=None):
        result = find_mavis_binary()
        assert result is None


@pytest.mark.asyncio
async def test_real_mode_falls_back_to_dry_run_when_binary_missing(tmp_path):
    """If real mode but no binary, fall back to dry_run with a warning."""
    b = MavisBridge(mode="real", mavis_cli=None)  # auto-detect

    with mock.patch("app.bridge.mavis.find_mavis_binary", return_value=None):
        project = tmp_path / "proj"
        project.mkdir()
        result = await b.delegate(
            task="do work",
            project_dir=project,
        )

    # Should have fallen back to dry-run
    assert result.mode == "dry_run"
    assert "[DRY-RUN]" in result.summary


# ---------------------------------------------------------------------------
# Real mode: subprocess invocation (mocked)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_real_mode_invokes_hermes_chat_with_correct_flags(tmp_path):
    """Verify the subprocess command is built correctly."""
    b = MavisBridge(
        mode="real",
        mavis_cli="/fake/hermes",
        use_worktree=True,
        use_checkpoints=True,
        mavis_model="anthropic/claude-sonnet-4",
    )
    project = tmp_path / "proj"
    project.mkdir()

    # Mock the subprocess.run for hermes
    mock_result = mock.Mock()
    mock_result.returncode = 0
    mock_result.stdout = "Done fixing the auth bug."
    mock_result.stderr = ""

    with mock.patch("subprocess.run", return_value=mock_result) as mock_run:
        with mock.patch("app.bridge.mavis.MavisBridge._inspect_git_state", return_value={
            "commit_sha": "abc123", "branch": "main", "files_changed": ["src/auth.py"], "pushed": False,
        }):
            result = await b.delegate(
                task="fix the auth bug",
                project_dir=project,
            )

    # Verify the command
    call_args = mock_run.call_args
    cmd = call_args.args[0]
    cwd = call_args.kwargs.get("cwd")
    assert cmd[0] == "/fake/hermes"
    assert cmd[1] == "chat"
    assert cmd[2] == "-q"
    assert cmd[3] == "fix the auth bug"
    assert "--worktree" in cmd
    assert "--checkpoints" in cmd
    assert "-m" in cmd
    assert "anthropic/claude-sonnet-4" in cmd
    assert cwd == str(project)

    # Verify the result
    assert result.success is True
    assert "Done fixing the auth bug" in result.summary
    assert result.commit_sha == "abc123"
    assert result.files_changed == ["src/auth.py"]
    assert result.mode == "real"


@pytest.mark.asyncio
async def test_real_mode_with_resume_flag(tmp_path):
    """Verify --resume flag is passed when session_id is given."""
    b = MavisBridge(mode="real", mavis_cli="/fake/hermes")
    project = tmp_path / "proj"
    project.mkdir()

    mock_result = mock.Mock()
    mock_result.returncode = 0
    mock_result.stdout = "continued work"
    mock_result.stderr = ""

    with mock.patch("subprocess.run", return_value=mock_result) as mock_run:
        with mock.patch("app.bridge.mavis.MavisBridge._inspect_git_state", return_value={
            "commit_sha": "", "branch": "", "files_changed": [], "pushed": False,
        }):
            await b.delegate(
                task="continue from where you left off",
                project_dir=project,
                session_id="prev-session-123",
            )

    cmd = mock_run.call_args.args[0]
    assert "--resume" in cmd
    assert "prev-session-123" in cmd


@pytest.mark.asyncio
async def test_real_mode_handles_timeout(tmp_path):
    """Subprocess timeout returns a clear error result."""
    b = MavisBridge(mode="real", mavis_cli="/fake/hermes", timeout_sec=10)
    project = tmp_path / "proj"
    project.mkdir()

    with mock.patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=["x"], timeout=10)):
        result = await b.delegate(task="slow task", project_dir=project)

    assert result.success is False
    assert "timed out" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_real_mode_handles_nonzero_exit(tmp_path):
    """Non-zero exit with no stdout is an error."""
    b = MavisBridge(mode="real", mavis_cli="/fake/hermes")
    project = tmp_path / "proj"
    project.mkdir()

    mock_result = mock.Mock()
    mock_result.returncode = 1
    mock_result.stdout = ""
    mock_result.stderr = "fatal: not a git repo"

    with mock.patch("subprocess.run", return_value=mock_result):
        result = await b.delegate(task="task", project_dir=project)

    assert result.success is False
    assert "not a git repo" in (result.error or "")


# ---------------------------------------------------------------------------
# _inspect_git_state — real git inspection
# ---------------------------------------------------------------------------


def test_inspect_git_state_real_repo(tmp_path):
    """In a real git repo with multiple commits, _inspect_git_state should read correctly."""
    import subprocess
    project = tmp_path / "realrepo"
    project.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=str(project), check=True)
    subprocess.run(["git", "config", "user.email", "test@test"], cwd=str(project), check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(project), check=True)

    # Initial commit
    (project / "README.md").write_text("# Test\n")
    subprocess.run(["git", "add", "README.md"], cwd=str(project), check=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=str(project), check=True)

    # Second commit — modify a file (this gives us a diff against main)
    (project / "src.py").write_text("print('hello')\n")
    subprocess.run(["git", "add", "src.py"], cwd=str(project), check=True)
    subprocess.run(["git", "commit", "-q", "-m", "add src.py"], cwd=str(project), check=True)

    b = MavisBridge(mode="real")
    state = b._inspect_git_state(project)

    assert state["branch"] in ("main", "master")  # depends on git config
    assert len(state["commit_sha"]) == 40  # full SHA
    assert "src.py" in state["files_changed"]


def test_inspect_git_state_non_git_dir(tmp_path):
    """Non-git directory should not crash — return empty state."""
    project = tmp_path / "notgit"
    project.mkdir()

    b = MavisBridge(mode="real")
    state = b._inspect_git_state(project)

    # All fields empty/default
    assert state["commit_sha"] == ""
    assert state["branch"] == ""
    assert state["files_changed"] == []
    assert state["pushed"] is False

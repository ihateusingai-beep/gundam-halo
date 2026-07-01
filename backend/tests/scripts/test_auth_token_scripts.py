"""Sprint 48 — generate-auth-token.sh + rotate-auth-token.sh tests.

Coverage (4 tests):
1. generate-auth-token.sh creates .env with token when missing.
2. generate-auth-token.sh rotates existing token.
3. rotate-auth-token.sh requires .env to exist.
4. rotate-auth-token.sh replaces token in place.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"


def _run_script(name: str, env: dict, cwd: Path) -> subprocess.CompletedProcess:
    """Run a shell script with the given env + cwd."""
    return subprocess.run(
        ["/bin/bash", str(SCRIPTS_DIR / name)],
        env={**os.environ, **env},
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_generate_creates_env_when_missing(tmp_path: Path):
    """No .env → script creates one with HALO_API_TOKEN + chmod 600."""
    env_file = tmp_path / ".env"
    assert not env_file.exists()
    result = _run_script(
        "generate-auth-token.sh",
        {"HALO_HOME": str(tmp_path)},
        cwd=tmp_path,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert env_file.is_file()
    # chmod 600 check.
    mode = env_file.stat().st_mode & 0o777
    assert mode == 0o600, f"expected mode 600, got {oct(mode)}"
    # Has HALO_API_TOKEN line.
    content = env_file.read_text()
    assert "HALO_API_TOKEN=" in content
    # Token looks base64-ish (alphanumeric, ~43 chars).
    token_line = [l for l in content.splitlines() if l.startswith("HALO_API_TOKEN=")][0]
    token = token_line.split("=", 1)[1]
    assert len(token) >= 32


def test_generate_rotates_existing_token(tmp_path: Path):
    """Existing token → replaced with new one."""
    env_file = tmp_path / ".env"
    env_file.write_text("HALO_API_TOKEN=old-token-abc123\n", encoding="utf-8")
    result = _run_script(
        "generate-auth-token.sh",
        {"HALO_HOME": str(tmp_path)},
        cwd=tmp_path,
    )
    assert result.returncode == 0
    content = env_file.read_text()
    token_line = [l for l in content.splitlines() if l.startswith("HALO_API_TOKEN=")][0]
    new_token = token_line.split("=", 1)[1]
    assert new_token != "old-token-abc123"
    assert len(new_token) >= 32


def test_rotate_requires_env_file(tmp_path: Path):
    """No .env → rotate script exits with non-zero + clear error."""
    result = _run_script(
        "rotate-auth-token.sh",
        {"HALO_HOME": str(tmp_path)},
        cwd=tmp_path,
    )
    assert result.returncode != 0
    assert "not found" in result.stderr.lower()


def test_rotate_replaces_in_place(tmp_path: Path):
    """rotate-auth-token.sh replaces existing token + chmod 600."""
    env_file = tmp_path / ".env"
    env_file.write_text("HALO_API_TOKEN=initial-token\n", encoding="utf-8")
    result = _run_script(
        "rotate-auth-token.sh",
        {"HALO_HOME": str(tmp_path)},
        cwd=tmp_path,
    )
    assert result.returncode == 0
    content = env_file.read_text()
    token_line = [l for l in content.splitlines() if l.startswith("HALO_API_TOKEN=")][0]
    new_token = token_line.split("=", 1)[1]
    assert new_token != "initial-token"
    assert len(new_token) >= 32
    # chmod 600.
    mode = env_file.stat().st_mode & 0o777
    assert mode == 0o600
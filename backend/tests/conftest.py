"""Shared test fixtures.

Two fixtures:
- `default_test_config` (autouse) — sets HALO_HOME + dummy MiniMax key.
  Uses DEFAULT policy — these are the same defaults the policy tests
  verify, so this doesn't interfere with them.
- `permissive_test_config` (opt-in) — additionally allows all file ops
  and shell commands for tests that need to actually do work in tmp_path.
"""

import os
import pytest

from app.core import config as _config_module


@pytest.fixture(autouse=True)
def default_test_config(monkeypatch, tmp_path):
    """Autouse: redirect HALO_HOME to tmp_path + set dummy MiniMax key.

    Uses default policy (no override). Tests that need permissive policy
    request `permissive_test_config` explicitly.
    """
    monkeypatch.setenv("HALO_HOME", str(tmp_path))
    monkeypatch.setenv("MINIMAX_API_KEY", "test-fake-key-not-real")
    _config_module.reset_config()
    # Load via get_config() so the singleton is updated
    _config_module.get_config(home=tmp_path)
    yield
    _config_module.reset_config()


@pytest.fixture
def permissive_test_config(monkeypatch, tmp_path):
    """Opt-in: for tests that need to actually do file ops or run shell.

    Adds tmp_path to file_read_paths / file_write_paths, sets shell
    allowlist to wildcard. Used by tool tests and API tests.
    """
    cfg = _config_module.get_config()
    # Combine: add tmp_path to existing allowlists
    cfg.mac.file_read_paths = list(cfg.mac.file_read_paths) + [
        str(tmp_path), "/tmp", "/private/tmp", "/var/folders",
    ]
    cfg.mac.file_write_paths = list(cfg.mac.file_write_paths) + [
        str(tmp_path), "/tmp", "/private/tmp", "/var/folders",
    ]
    # Add common test commands to the allowlist (don't use "*" — that
    # would also override policy tests in the same session)
    extra_shell = ["ls", "cat", "echo", "true", "false", "test", "git"]
    cfg.mac.shell_allowlist = list(set(cfg.mac.shell_allowlist) | set(extra_shell))
    yield

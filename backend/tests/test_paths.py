"""Tests for `app.paths` — single-source-of-truth halo_home resolver.

Sprint 56: validates the R1 refactor (consolidate `.gundam-halo` path
computation). Tests cover:
  - DEFAULT_HALO_HOME matches the pre-Sprint-56 literal
  - halo_home() returns ~/.gundam-halo by default
  - halo_home() honours $HALO_HOME override
  - Each sub-dir helper routes through halo_home()
  - Backwards-compat: DEFAULT_HOME in app.core.config still works
"""
from __future__ import annotations

from pathlib import Path

import pytest


class TestHaloHome:
    """Tests for `halo_home()` — the env-var-aware canonical resolver."""

    def test_default_home_is_dot_gundam_halo(self, monkeypatch):
        """DEFAULT_HALO_HOME must equal ~/.gundam-halo so existing
        behaviour is preserved (R1 audit caught 28 sites that did this
        exactly; pre-refactor behaviour must match exactly).
        """
        from app.paths import DEFAULT_HALO_HOME
        monkeypatch.delenv("HALO_HOME", raising=False)
        assert DEFAULT_HALO_HOME == Path.home() / ".gundam-halo"

    def test_halo_home_default_when_env_unset(self, monkeypatch):
        """No HALO_HOME → ~/.gundam-halo."""
        from app.paths import halo_home
        monkeypatch.delenv("HALO_HOME", raising=False)
        assert halo_home() == Path.home() / ".gundam-halo"

    def test_halo_home_resolves_to_absolute(self, monkeypatch):
        """halo_home() always returns a `.resolve()`-d absolute Path
        so callers can compare / cache safely.
        """
        from app.paths import halo_home
        monkeypatch.delenv("HALO_HOME", raising=False)
        assert halo_home().is_absolute()

    def test_halo_home_honours_env_override(self, monkeypatch, tmp_path):
        """HALO_HOME=/tmp/foo → halo_home() returns /tmp/foo.
        This is the headline benefit of R1: tests + production can
        point the whole tree at a sandbox without monkeypatching
        28 separate constants.
        """
        monkeypatch.setenv("HALO_HOME", str(tmp_path))
        from app.paths import halo_home
        assert halo_home() == tmp_path.resolve()

    def test_halo_home_expands_user_in_env_override(self, monkeypatch):
        """HALO_HOME=~/sandbox → resolved against $HOME.
        Many launchd plists + shell configs use ~-prefixed paths.
        """
        monkeypatch.setenv("HALO_HOME", "~/halo-sandbox")
        from app.paths import halo_home
        assert halo_home() == (Path.home() / "halo-sandbox").resolve()


class TestSubDirHelpers:
    """Each helper routes through halo_home() — so HALO_HOME
    override cascades once and applies to all sub-dirs.
    """

    def test_models_dir_under_default(self, monkeypatch):
        from app.paths import models_dir
        monkeypatch.delenv("HALO_HOME", raising=False)
        assert models_dir() == Path.home() / ".gundam-halo" / "models"

    def test_cache_dir_under_default(self, monkeypatch):
        from app.paths import cache_dir
        monkeypatch.delenv("HALO_HOME", raising=False)
        assert cache_dir() == Path.home() / ".gundam-halo" / "cache"

    def test_recordings_dir_under_default(self, monkeypatch):
        from app.paths import recordings_dir
        monkeypatch.delenv("HALO_HOME", raising=False)
        assert recordings_dir() == Path.home() / ".gundam-halo" / "recordings"

    def test_logs_dir_under_default(self, monkeypatch):
        from app.paths import logs_dir
        monkeypatch.delenv("HALO_HOME", raising=False)
        assert logs_dir() == Path.home() / ".gundam-halo" / "logs"

    def test_config_path_under_default(self, monkeypatch):
        from app.paths import config_path
        monkeypatch.delenv("HALO_HOME", raising=False)
        assert config_path() == Path.home() / ".gundam-halo" / "config.toml"

    def test_subdirs_follow_halo_home_override(self, monkeypatch, tmp_path):
        """Single env-var override cascades to every sub-dir helper.
        This is the key win: previously each script + API module + core
        module each had its own `DEFAULT_HALO_HOME = Path.home() / ".gundam-halo"`
        literal that wouldn't follow HALO_HOME.
        """
        monkeypatch.setenv("HALO_HOME", str(tmp_path))
        from app.paths import (
            cache_dir,
            config_path,
            logs_dir,
            models_dir,
            recordings_dir,
        )
        resolved = tmp_path.resolve()
        assert models_dir() == resolved / "models"
        assert cache_dir() == resolved / "cache"
        assert recordings_dir() == resolved / "recordings"
        assert logs_dir() == resolved / "logs"
        assert config_path() == resolved / "config.toml"


class TestExpandHome:
    """`expand_home(path)` is the cross-platform thin wrapper around
    `os.path.expanduser` that also `.resolve()`-es. Used by the
    legacy `app.core.config.expand_home` (kept for back-compat).
    """

    def test_expand_tilde(self):
        from app.paths import expand_home
        assert expand_home("~/foo") == (Path.home() / "foo").resolve()

    def test_passes_through_absolute(self):
        """Already-absolute paths are .resolve()-d.
        (macOS resolves /tmp → /private/tmp because /tmp is a symlink;
        we use Path("/tmp/foo").resolve() for the assertion so the
        test passes on both Linux + macOS.)
        """
        from app.paths import expand_home
        assert expand_home("/tmp/foo") == Path("/tmp/foo").resolve()

    def test_accepts_path_object(self):
        """`expand_home(Path("~/x"))` must work — callers pass Path."""
        from app.paths import expand_home
        result = expand_home(Path("~/x"))
        assert result == (Path.home() / "x").resolve()


class TestWhisperCacheDir:
    """whisper_cache_dir() is NOT under halo_home because it's the
    openai-whisper library convention. Pin it to ~/.cache/whisper so
    the fine-tune scripts that download openai-whisper-base land at
    a known location.
    """

    def test_whisper_cache_dir_default(self):
        from app.paths import whisper_cache_dir
        assert whisper_cache_dir() == Path.home() / ".cache" / "whisper"


class TestBackCompat:
    """Sprint 56: legacy `app.core.config.DEFAULT_HOME` + `expand_home`
    must remain importable so the 28+ call sites that already import
    them don't break.
    """

    def test_config_default_home_compat(self):
        from app.core.config import DEFAULT_HOME
        from app.paths import DEFAULT_HALO_HOME
        assert DEFAULT_HOME == DEFAULT_HALO_HOME

    def test_config_expand_home_compat(self):
        from app.core.config import expand_home
        from app.paths import expand_home as new_expand_home
        # Same behaviour: both wrap os.path.expanduser + .resolve()
        assert expand_home("~/x") == new_expand_home("~/x")


@pytest.fixture(autouse=True)
def clean_halo_home_env(monkeypatch):
    """Strip HALO_HOME at test start so tests that don't explicitly
    set it see the same behaviour as production-default (which is
    `monkeypatch.delenv` not strict absence — pytest cleans up
    env between tests anyway, but be explicit).
    """
    monkeypatch.delenv("HALO_HOME", raising=False)

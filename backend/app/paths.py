"""Single source of truth for ~/.gundam-halo paths.

Before this module existed, the expression `Path.home() / '.gundam-halo'`
appeared in 28 different files (11 source files, 15 test files, 2 core
modules — see Sprint 56 audit). Each was a possible silent drift point:
change one, the others keep using the default, and a future test or
production environment that sets HALO_HOME only gets partial effect.

After this module, there is ONE place that knows how to find the home
directory. Subdirectory helpers (`models_dir()`, `cache_dir()`, …)
centralise the layout too, so future renames (e.g. moving `cache/` to
`var/cache/`) require editing one module instead of chasing 28.

`HALO_HOME` env var override works for every helper because they all
funnel through `halo_home()`. The single-user launchd plist sets it for
production; tests can `monkeypatch.setenv("HALO_HOME", str(tmp_path))`
once and have the whole tree follow.

The default `DEFAULT_HALO_HOME` is also re-exported as
`app.core.config.DEFAULT_HOME` via `__all__` so existing imports keep
working unchanged.
"""
from __future__ import annotations

import os
from pathlib import Path

# Default home directory — `~/.gundam-halo`. Lives here (not in
# `app.core.config`) because:
#   1. `app.paths` is the canonical owner post-Sprint 56.
#   2. `app.core.config.DEFAULT_HOME` re-exports this same Path so
#      legacy imports `from app.core.config import DEFAULT_HOME`
#      continue to work without cycle risk — we just `from
#      app.paths import DEFAULT_HALO_HOME as DEFAULT_HOME` in
#      `app.core.config.__init__` (or use a lazy import inside
#      `expand_home`).
DEFAULT_HALO_HOME: Path = Path.home() / ".gundam-halo"


def halo_home() -> Path:
    """Return the Halo home directory.

    Honours the `$HALO_HOME` env var (used by the bundled launchd
    plist + tests). Falls back to `~/.gundam-halo`. Always returns
    a `.resolve()`-d absolute path so callers can compare / cache
    safely without worrying about CWD changes.
    """
    raw = os.environ.get("HALO_HOME")
    if raw:
        return Path(os.path.expanduser(raw)).resolve()
    return DEFAULT_HALO_HOME.resolve()


def expand_home(path: str | Path) -> Path:
    """Expand ~ and resolve to absolute Path.

    Kept here (instead of only in `app.core.config`) because R1 audit
    found `scripts/` doing `os.path.expanduser("~/.gundam-halo/...")`
    inline. Migrating those callers to use the helpers below makes
    the canonical-home logic live in one place.
    """
    return Path(os.path.expanduser(str(path))).resolve()


# ---------------------------------------------------------------------------
# Sub-directories under halo_home()
# ---------------------------------------------------------------------------
# Each helper is a thin wrapper so a future rename (cache/ → var/cache/)
# requires only updating this file. Tests can monkeypatch halo_home()
# once and the whole tree follows.


def models_dir() -> Path:
    """`~/.gundam-halo/models/` — Whisper / Silero / yolov8 / funasr
    checkpoints + the fine-tune output (Sprint 55: `whisper-yue-base/`).
    """
    return halo_home() / "models"


def cache_dir() -> Path:
    """`~/.gundam-halo/cache/` — Common Voice yue shards (Sprint 55)
    + other large transient artifacts that shouldn't live under `models/`.
    """
    return halo_home() / "cache"


def recordings_dir() -> Path:
    """`~/.gundam-halo/recordings/` — `yue-self-<date>/` corpora
    (Sprint 33b self-record) + `held-out-<date>.{wav,txt}` pairs.
    """
    return halo_home() / "recordings"


def logs_dir() -> Path:
    """`~/.gundam-halo/logs/` — held-out eval / finetune / cron monitor
    output files.
    """
    return halo_home() / "logs"


def projects_dir() -> Path:
    """`~/.gundam-halo/projects/` — per-user project workspaces."""
    return halo_home() / "projects"


def config_path() -> Path:
    """`~/.gundam-halo/config.toml` — single source of truth for the
    app's runtime config (Sprint 32 P0-2: round-tripped via
    `app.core.toml_doc`, not parsed via regex).
    """
    return halo_home() / "config.toml"


# Legacy / utility helpers (Sprint 56) --------------------------------------

def whisper_cache_dir() -> Path:
    """`~/.cache/whisper/` — openai-whisper library convention.
    NOT under halo_home because it's HF/whisper-cpp's default cache
    layout that older scripts (m9c_voice_tools.py) hard-code.
    """
    return Path.home() / ".cache" / "whisper"


# Public surface -------------------------------------------------------------

__all__ = [
    "DEFAULT_HALO_HOME",
    "halo_home",
    "expand_home",
    "models_dir",
    "cache_dir",
    "recordings_dir",
    "logs_dir",
    "projects_dir",
    "config_path",
    "whisper_cache_dir",
]

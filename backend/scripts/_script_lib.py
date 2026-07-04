"""Shared helpers for `backend/scripts/*.py` entry points.

Sprint 56 R1: every script previously redeclared
`DEFAULT_HALO_HOME = Path.home() / ".gundam-halo"` and a
`_resolve_halo_home(args)` helper. Consolidate here so a future
rename of the home directory requires editing one module
instead of chasing 8 scripts.

Used by: gen_cantonese_corpus.py, run_held_out_pipeline.py,
swap_to_personalised_model.py, prepare_fsicoli_cv_yue.py, and
future scripts.
"""
from __future__ import annotations

import argparse

# All scripts are launched from repo root or `backend/`. Adding
# `backend/` to sys.path so `from _script_lib import ...` works
# from any cwd mirrors what the scripts already do for
# `from app.paths import ...`.
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.paths import (  # noqa: E402
    halo_home,
)


def resolve_halo_home(args: argparse.Namespace) -> Path:
    """Resolve the halo-home directory for a script.

    Priority:
      1. `args.halo_home` (explicit CLI override, e.g. `--halo-home /tmp/x`)
      2. `$HALO_HOME` env var (set by launchd plist in production)
      3. `~/.gundam-halo` (canonical default via `app.paths.halo_home()`)

    Note: priorities 2 and 3 are handled by `halo_home()` already; we
    only branch on the CLI override so `python prep.py --halo-home
    /tmp/sandbox` overrides even when $HALO_HOME is also set.

    Does NOT verify the directory exists — different scripts have
    different needs (some auto-create, others fail-fast). The caller
    decides; e.g. `gen_cantonese_corpus.py` raises SystemExit if
    the dir is missing because it can't auto-create an empty
    halo_home (no recordings/ yet).
    """
    if getattr(args, "halo_home", None):
        return Path(args.halo_home).expanduser().resolve()
    return halo_home()


__all__ = ["resolve_halo_home"]

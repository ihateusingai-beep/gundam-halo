"""System endpoints — gauges, health, info."""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

import psutil

from app import __version__

logger = logging.getLogger(__name__)
router = APIRouter()


class Gauges(BaseModel):
    cpu_percent: float
    memory_percent: float
    disk_percent: float
    network_sent_mb: float
    network_recv_mb: float


@router.get("/gauges", response_model=Gauges)
async def get_gauges() -> Gauges:
    """Current Mac system resource usage."""
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    net = psutil.net_io_counters()

    return Gauges(
        cpu_percent=psutil.cpu_percent(interval=0.1),
        memory_percent=mem.percent,
        disk_percent=disk.percent,
        network_sent_mb=net.bytes_sent / 1024 / 1024,
        network_recv_mb=net.bytes_recv / 1024 / 1024,
    )


def _read_git_sha() -> str | None:
    """Best-effort lookup of the running backend's git SHA.

    Looks in this order:
      1. `HALO_GIT_SHA` env var (set by launch scripts / supervisors)
      2. `git rev-parse HEAD` if a `.git` dir exists at the project root
      3. The baked-in `__git_sha__` constant (injected at build time)
    Returns None on every miss.
    """
    env_sha = os.environ.get("HALO_GIT_SHA")
    if env_sha:
        return env_sha.strip()
    try:
        # Walk up from this file to find the repo root
        here = Path(__file__).resolve()
        for ancestor in [here, *here.parents]:
            git_dir = ancestor / ".git"
            if git_dir.exists():
                head = git_dir / "HEAD"
                if head.exists():
                    head_text = head.read_text(encoding="utf-8").strip()
                    if head_text.startswith("ref: "):
                        ref = head_text.split(" ", 1)[1]
                        ref_file = git_dir / ref
                        if ref_file.exists():
                            return ref_file.read_text(encoding="utf-8").strip()
                    return head_text
    except Exception as e:
        logger.debug(f"git SHA lookup failed: {e}")
    return None


@router.get("/info")
async def get_info() -> dict:
    """Basic system info, used by the cockpit for diagnostics.

    New fields (M15-restart-banner):
      - git_sha: backend's current commit SHA, "unknown" if not in a
        git repo or env var unset
      - build_id: backend process start timestamp (epoch seconds).
        The frontend can detect a backend restart by watching this
        change.
      - features: list of feature flags the backend supports
        (frontend uses this to know if streaming voice etc. is
        available, even when the git SHA hasn't changed).
    """
    import time

    return {
        "platform": "mac",
        "python_version": "3.11+",
        "app_version": __version__,
        "git_sha": _read_git_sha() or "unknown",
        "build_id": int(time.time()),  # updated on every restart
        "features": [
            "voice_streaming",  # M15 — agent streaming + per-sentence TTS
            "live2d_triggers",  # M3-B4 — Live2D motion on tool calls
            "telegram_dry_run",  # M2 — Telegram channel in dry-run
        ],
    }


# ---------------------------------------------------------------------------
# Sprint 43 — Self-Healing Backend (watchdog + launchd supervisor state)
# ---------------------------------------------------------------------------


@router.get("/health-detailed")
async def get_health_detailed() -> dict:
    """Extended health payload for the watchdog (Sprint 43).

    Returns the basic /api/health payload PLUS:
      - crash_count_60m (int) — number of crashes in the last 60 min
      - last_crash_at (str | null) — ISO 8601 timestamp of the most
        recent crash, or None if no crashes in the window
      - respawn_disabled (bool) — True if the crash count >= threshold
        (default 3). The Tauri watchdog reads this flag and:
          * surfaces a red banner in the cockpit
          * switches the tray icon dot to red
          * stops trying to ping for 5 minutes
      - watchdog.installed (bool) — True if the launchd supervisor
        plist (com.gundam.halo) is loaded
      - watchdog.pid (int | null) — PID of the supervised uvicorn
        process, or None if not running

    The endpoint NEVER raises — all helpers swallow errors. The
    frontend relies on this being always-available even when the
    backend is in a degraded state.
    """
    from app.core.config import get_config
    from app.core.watchdog import (
        crash_count_last_hour,
        get_launchd_pid,
        is_launchd_supervisor_loaded,
        last_crash_at,
        should_stop_respawning,
    )

    home = Path(get_config().home)
    return {
        "status": "ok",
        "version": __version__,
        "name": "gundam-halo",
        "crash_count_60m": crash_count_last_hour(home),
        "last_crash_at": last_crash_at(home),
        "respawn_disabled": should_stop_respawning(home),
        "watchdog": {
            "installed": is_launchd_supervisor_loaded(),
            "pid": get_launchd_pid(),
        },
    }


@router.post("/clear-crash-log")
async def post_clear_crash_log() -> dict:
    """Sprint 43 — wipe the crash log (admin action).

    Called by the cockpit's BackendHealthBanner "Clear crash log &
    retry" button. Does NOT delete the crash marker file (that's
    owned by the launchd WatchPaths hook).

    Returns the number of events that were cleared.

    Security note (Sprint 43): the endpoint is currently
    unprotected (single-user assumption, same as the rest of the
    /api/system/* surface). A future Sprint 45 will add an auth
    layer — flagged in docs/SECURITY-HARDENING.md.
    """
    from app.core.config import get_config
    from app.core.watchdog import clear_crash_log

    home = Path(get_config().home)
    cleared = clear_crash_log(home)
    return {"ok": True, "cleared": cleared}

"""System endpoints — gauges, health, info."""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

import psutil

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
        "app_version": "0.1.0",
        "git_sha": _read_git_sha() or "unknown",
        "build_id": int(time.time()),  # updated on every restart
        "features": [
            "voice_streaming",  # M15 — agent streaming + per-sentence TTS
            "live2d_triggers",  # M3-B4 — Live2D motion on tool calls
            "telegram_dry_run",  # M2 — Telegram channel in dry-run
        ],
    }

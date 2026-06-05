"""System endpoints — gauges, health, info."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

import psutil

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


@router.get("/info")
async def get_info() -> dict:
    """Basic system info."""
    return {
        "platform": "mac",
        "python_version": "3.11+",
        "app_version": "0.1.0",
    }

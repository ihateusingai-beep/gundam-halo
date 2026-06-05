"""Mac control endpoints — file read/write, shell, apple_script, etc.

ALL endpoints are policy-gated. See `app/mac/policy.py`.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.events import EventType, get_event_bus
from app.mac.file_ops import read_file, write_file
from app.mac.policy import check_path_read, check_path_write
from app.mac.shell import run_shell

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------


class FileReadRequest(BaseModel):
    path: str


class FileReadResponse(BaseModel):
    path: str
    content: str
    bytes: int


@router.post("/file/read", response_model=FileReadResponse)
async def api_file_read(req: FileReadRequest) -> FileReadResponse:
    if not check_path_read(req.path):
        get_event_bus().publish(
            EventType.MAC_OP_BLOCKED,
            {"action": "mac.file.read", "target": req.path, "reason": "policy"},
        )
        raise HTTPException(status_code=403, detail=f"Path not allowed by policy: {req.path}")

    try:
        content = read_file(req.path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"File not found: {req.path}")
    except Exception as e:
        logger.error(f"file read error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    get_event_bus().publish(
        EventType.MAC_OP_AUDIT,
        {"action": "mac.file.read", "target": req.path, "bytes": len(content)},
    )

    return FileReadResponse(path=req.path, content=content, bytes=len(content))


class FileWriteRequest(BaseModel):
    path: str
    content: str


class FileWriteResponse(BaseModel):
    path: str
    bytes: int
    status: str = "written"


@router.post("/file/write", response_model=FileWriteResponse)
async def api_file_write(req: FileWriteRequest) -> FileWriteResponse:
    """Write a file. PATH MUST be in write policy. Requires confirmation in real use."""
    if not check_path_write(req.path):
        get_event_bus().publish(
            EventType.MAC_OP_BLOCKED,
            {"action": "mac.file.write", "target": req.path, "reason": "policy"},
        )
        raise HTTPException(status_code=403, detail=f"Path not allowed by policy: {req.path}")

    try:
        write_file(req.path, req.content)
    except Exception as e:
        logger.error(f"file write error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    get_event_bus().publish(
        EventType.MAC_OP_AUDIT,
        {"action": "mac.file.write", "target": req.path, "bytes": len(req.content)},
    )

    return FileWriteResponse(path=req.path, bytes=len(req.content))


# ---------------------------------------------------------------------------
# Shell
# ---------------------------------------------------------------------------


class ShellRequest(BaseModel):
    command: str = Field(..., description="Command and arguments, space-separated")
    timeout_sec: int = 30


class ShellResponse(BaseModel):
    command: str
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int


@router.post("/shell", response_model=ShellResponse)
async def api_shell(req: ShellRequest) -> ShellResponse:
    """Execute a shell command. COMMAND must be in allowlist."""
    try:
        result = run_shell(req.command, timeout=req.timeout_sec)
    except PermissionError as e:
        get_event_bus().publish(
            EventType.MAC_OP_BLOCKED,
            {"action": "mac.shell", "target": req.command, "reason": "not_in_allowlist"},
        )
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"shell error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    get_event_bus().publish(
        EventType.MAC_OP_AUDIT,
        {
            "action": "mac.shell",
            "target": req.command,
            "exit_code": result["exit_code"],
            "duration_ms": result["duration_ms"],
        },
    )

    return ShellResponse(**result)

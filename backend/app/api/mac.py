"""Mac control endpoints — file read/write, shell, AppleScript,
clipboard, notifications, Spotlight, Accessibility API.

ALL endpoints are policy-gated. See `app/mac/policy.py` for
path / command allowlists. The M11 surface (AppleScript,
clipboard, notifications, Spotlight, A11y) is gated by per-feature
config flags in `cfg.mac.*` and always audit-logged.
"""
from __future__ import annotations

import logging
from typing import Any, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.events import EventType, get_event_bus
from app.mac.a11y import (
    a11y_app_processes,
    a11y_focused_app,
    a11y_query,
    a11y_window_list,
)
from app.mac.apple_script import run_applescript
from app.mac.clipboard import read_clipboard, write_clipboard
from app.mac.file_ops import read_file, write_file
from app.mac.notifications import send_notification
from app.mac.policy import check_path_read, check_path_write
from app.mac.shell import run_shell
from app.mac.spotlight import spotlight_search

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

    return FileWriteResponse(path=req.path, bytes=len(req.content), status="written")


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


# ---------------------------------------------------------------------------
# AppleScript (M11)
# ---------------------------------------------------------------------------


class AppleScriptRequest(BaseModel):
    script: str = Field(..., description="AppleScript source to run via `osascript -e`.")
    timeout_sec: int = 30


class AppleScriptResponse(BaseModel):
    script: str
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int


@router.post("/apple-script", response_model=AppleScriptResponse)
async def api_apple_script(req: AppleScriptRequest) -> AppleScriptResponse:
    """Run an AppleScript snippet. Gated by `cfg.mac.apple_script_enabled`."""
    try:
        result = run_applescript(req.script, timeout=req.timeout_sec)
    except PermissionError as e:
        get_event_bus().publish(
            EventType.MAC_OP_BLOCKED,
            {
                "action": "mac.apple_script",
                "target": req.script[:120],
                "reason": "disabled_in_config",
            },
        )
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    get_event_bus().publish(
        EventType.MAC_OP_AUDIT,
        {
            "action": "mac.apple_script",
            "target": req.script[:120],
            "exit_code": result["exit_code"],
            "duration_ms": result["duration_ms"],
        },
    )
    return AppleScriptResponse(**result)


# ---------------------------------------------------------------------------
# Clipboard (M11)
# ---------------------------------------------------------------------------


class ClipboardReadResponse(BaseModel):
    text: str
    bytes: int


class ClipboardWriteRequest(BaseModel):
    text: str


class ClipboardWriteResponse(BaseModel):
    bytes: int
    status: str = "written"


@router.get("/clipboard", response_model=ClipboardReadResponse)
async def api_clipboard_read() -> ClipboardReadResponse:
    """Read the system clipboard. Returns empty text if the clipboard
    doesn't hold a plain-text type (image, file ref, etc.)."""
    try:
        text = read_clipboard()
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    get_event_bus().publish(
        EventType.MAC_OP_AUDIT,
        {
            "action": "mac.clipboard.read",
            "target": "",
            "bytes": len(text.encode("utf-8")),
        },
    )
    return ClipboardReadResponse(text=text, bytes=len(text.encode("utf-8")))


@router.post("/clipboard", response_model=ClipboardWriteResponse)
async def api_clipboard_write(req: ClipboardWriteRequest) -> ClipboardWriteResponse:
    """Write text to the system clipboard."""
    try:
        written = write_clipboard(req.text)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    get_event_bus().publish(
        EventType.MAC_OP_AUDIT,
        {
            "action": "mac.clipboard.write",
            "target": "",
            "bytes": written,
        },
    )
    return ClipboardWriteResponse(bytes=written)


# ---------------------------------------------------------------------------
# Notifications (M11)
# ---------------------------------------------------------------------------


class NotificationRequest(BaseModel):
    text: str = Field(..., description="Notification body — the main message.")
    title: Optional[str] = None
    subtitle: Optional[str] = None


class NotificationResponse(BaseModel):
    exit_code: int
    stderr: str
    duration_ms: int


@router.post("/notify", response_model=NotificationResponse)
async def api_notify(req: NotificationRequest) -> NotificationResponse:
    """Show a macOS system notification. Gated by `cfg.mac.notifications_enabled`."""
    try:
        result = send_notification(
            text=req.text,
            title=req.title,
            subtitle=req.subtitle,
        )
    except PermissionError as e:
        get_event_bus().publish(
            EventType.MAC_OP_BLOCKED,
            {
                "action": "mac.notify",
                "target": req.text[:120],
                "reason": "disabled_in_config",
            },
        )
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    get_event_bus().publish(
        EventType.MAC_OP_AUDIT,
        {
            "action": "mac.notify",
            "target": req.text[:120],
            "exit_code": result["exit_code"],
            "duration_ms": result["duration_ms"],
        },
    )
    return NotificationResponse(
        exit_code=result["exit_code"],
        stderr=result["stderr"],
        duration_ms=result["duration_ms"],
    )


# ---------------------------------------------------------------------------
# Spotlight (M11)
# ---------------------------------------------------------------------------


class SpotlightRequest(BaseModel):
    query: str = Field(..., description="Spotlight query string (same DSL as Finder).")
    only_in: Optional[str] = Field(
        None, description="Optional directory to limit the search to."
    )
    max_results: int = Field(
        50, ge=1, le=500, description="Max results (capped at 500)."
    )


class SpotlightResponse(BaseModel):
    query: str
    count: int
    results: List[str]
    exit_code: int
    stderr: str


@router.post("/spotlight", response_model=SpotlightResponse)
async def api_spotlight(req: SpotlightRequest) -> SpotlightResponse:
    """Search the macOS Spotlight index. Read-only."""
    try:
        result = spotlight_search(
            query=req.query,
            max_results=req.max_results,
            only_in=req.only_in,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    get_event_bus().publish(
        EventType.MAC_OP_AUDIT,
        {
            "action": "mac.spotlight",
            "target": req.query[:120],
            "count": result["count"],
        },
    )
    return SpotlightResponse(
        query=result["query"],
        count=result["count"],
        results=result["results"],
        exit_code=result["exit_code"],
        stderr=result["stderr"],
    )


# ---------------------------------------------------------------------------
# Accessibility (M11)
# ---------------------------------------------------------------------------


class A11yRequest(BaseModel):
    operation: str = Field(
        ...,
        description=(
            "One of: 'windows' (list visible window names), 'processes' "
            "(list visible app names), 'focused' (return the frontmost app), "
            "'query' (run a custom System Events snippet; must reference "
            "'System Events')."
        ),
    )
    script: Optional[str] = None
    timeout_sec: int = 30


class A11yResponse(BaseModel):
    operation: str
    result: str
    items: List[str]
    count: int
    exit_code: int
    stderr: str
    duration_ms: int


@router.post("/a11y", response_model=A11yResponse)
async def api_a11y(req: A11yRequest) -> A11yResponse:
    """Read-only Accessibility API query via System Events.

    Gated by `cfg.mac.a11y_enabled`. We deliberately do NOT
    expose a way to send synthetic input here — that lives in
    a higher-trust tool out of v0.1.x scope.
    """
    op = req.operation
    if op not in ("windows", "processes", "focused", "query"):
        raise HTTPException(
            status_code=400,
            detail=f"Unknown operation {op!r}; expected one of windows/processes/focused/query",
        )

    def _run() -> dict:
        if op == "windows":
            return a11y_window_list(timeout=req.timeout_sec)
        if op == "processes":
            return a11y_app_processes(timeout=req.timeout_sec)
        if op == "focused":
            return a11y_focused_app(timeout=req.timeout_sec)
        # op == "query"
        if not req.script:
            raise ValueError("'script' is required for operation='query'")
        return a11y_query(script=req.script, timeout=req.timeout_sec)

    try:
        result = _run()
    except PermissionError as e:
        get_event_bus().publish(
            EventType.MAC_OP_BLOCKED,
            {
                "action": "mac.a11y",
                "target": op,
                "reason": "disabled_in_config",
            },
        )
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    get_event_bus().publish(
        EventType.MAC_OP_AUDIT,
        {
            "action": "mac.a11y",
            "target": f"{op}:{(req.script or '')[:80]}",
            "exit_code": result["exit_code"],
            "duration_ms": result["duration_ms"],
        },
    )
    return A11yResponse(
        operation=op,
        result=result["result"],
        items=result.get("items", []),
        count=result["count"],
        exit_code=result["exit_code"],
        stderr=result["stderr"],
        duration_ms=result["duration_ms"],
    )

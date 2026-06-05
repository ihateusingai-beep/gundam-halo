"""Session endpoints — start, send message, stop, get state."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.config import get_config
from app.core.events import EventType, get_event_bus

logger = logging.getLogger(__name__)
router = APIRouter()


class SessionStart(BaseModel):
    project_name: str
    agent_type: str = "native_react"


class SessionInfo(BaseModel):
    id: str
    project_name: str
    agent_type: str
    started_at: str
    message_count: int = 0


class MessageSend(BaseModel):
    content: str


# In-memory session tracking. Real impl would persist to disk + use LLM.
_sessions: dict[str, SessionInfo] = {}


def _session_id() -> str:
    import uuid
    return uuid.uuid4().hex[:12]


@router.post("", response_model=SessionInfo, status_code=201)
async def start_session(payload: SessionStart) -> SessionInfo:
    cfg = get_config()
    pdir = cfg.home / "projects" / payload.project_name
    if not pdir.exists():
        raise HTTPException(status_code=404, detail=f"Project '{payload.project_name}' not found")

    sid = _session_id()
    now = datetime.utcnow().isoformat() + "Z"
    info = SessionInfo(
        id=sid,
        project_name=payload.project_name,
        agent_type=payload.agent_type,
        started_at=now,
    )
    _sessions[sid] = info

    get_event_bus().publish(
        EventType.SESSION_START,
        {"session_id": sid, "project": payload.project_name, "agent": payload.agent_type},
    )

    return info


@router.get("/{session_id}", response_model=SessionInfo)
async def get_session(session_id: str) -> SessionInfo:
    info = _sessions.get(session_id)
    if not info:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return info


@router.get("", response_model=List[SessionInfo])
async def list_sessions() -> List[SessionInfo]:
    return list(_sessions.values())


@router.post("/{session_id}/message", status_code=202)
async def send_message(session_id: str, payload: MessageSend) -> dict:
    info = _sessions.get(session_id)
    if not info:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")

    # Increment message count
    info.message_count += 1

    get_event_bus().publish(
        EventType.SESSION_MESSAGE_RECEIVED,
        {
            "session_id": session_id,
            "project": info.project_name,
            "content_length": len(payload.content),
        },
    )

    # TODO: actually invoke the agent (engine + tool loop) and stream the response
    # For now, return a stub.
    return {
        "session_id": session_id,
        "status": "accepted",
        "message_count": info.message_count,
        "agent_response": "[stub: agent not yet implemented in scaffold]",
    }


@router.post("/{session_id}/stop", status_code=200)
async def stop_session(session_id: str) -> dict:
    info = _sessions.get(session_id)
    if not info:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")

    get_event_bus().publish(
        EventType.SESSION_END,
        {"session_id": session_id, "project": info.project_name},
    )

    del _sessions[session_id]
    return {"session_id": session_id, "status": "stopped"}

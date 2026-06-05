"""Session endpoints — start, send message, stop, get state.

Sessions are real (not stubs) in this version: they instantiate an agent
from the registry, pass it the engine + default tools, and route user
messages through it.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.agents._stubs import BaseAgent
from app.core.config import get_config
from app.core.events import EventType, get_event_bus
from app.core.registry import AgentRegistry
from app.engines.minimax import MiniMaxEngine
from app.tools.builder import default_tools

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


class MessageResponse(BaseModel):
    session_id: str
    user_message: str
    agent_response: str
    tool_calls_made: int
    success: bool
    error: Optional[str] = None


# In-memory session tracking.
# TODO (v2): persist to disk for resume across restarts.
_sessions: dict[str, SessionInfo] = {}
_agents: dict[str, BaseAgent] = {}


def _session_id() -> str:
    return uuid.uuid4().hex[:12]


def _get_or_create_engine():
    """Return a MiniMax engine, initialized from config."""
    cfg = get_config()
    if not cfg.llm.api_key:
        raise RuntimeError(
            "MINIMAX_API_KEY not set. Set it in .env or env vars."
        )
    return MiniMaxEngine(
        api_key=cfg.llm.api_key,
        base_url=cfg.llm.base_url,
        model=cfg.llm.default_model,
    )


def _get_or_create_agent(session_id: str, agent_type: str) -> BaseAgent:
    """Return a cached agent for the session, or create one."""
    if session_id in _agents:
        return _agents[session_id]

    if not AgentRegistry.contains(agent_type):
        raise ValueError(f"Unknown agent type: {agent_type}")

    engine = _get_or_create_engine()
    tools = default_tools()
    agent_cls = AgentRegistry.get(agent_type)
    agent = agent_cls(engine, get_config().llm.default_model, tools=tools)
    _agents[session_id] = agent
    return agent


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


@router.post("/{session_id}/message", response_model=MessageResponse)
async def send_message(session_id: str, payload: MessageSend) -> MessageResponse:
    info = _sessions.get(session_id)
    if not info:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")

    info.message_count += 1
    get_event_bus().publish(
        EventType.SESSION_MESSAGE_RECEIVED,
        {
            "session_id": session_id,
            "project": info.project_name,
            "content_length": len(payload.content),
        },
    )

    try:
        agent = _get_or_create_agent(session_id, info.agent_type)
    except Exception as e:
        logger.error(f"Failed to create agent for session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Agent init failed: {e}")

    try:
        result = await agent.run(payload.content)
    except Exception as e:
        logger.error(f"Agent run error in session {session_id}: {e}")
        return MessageResponse(
            session_id=session_id,
            user_message=payload.content,
            agent_response="",
            tool_calls_made=0,
            success=False,
            error=str(e),
        )

    return MessageResponse(
        session_id=session_id,
        user_message=payload.content,
        agent_response=result.output,
        tool_calls_made=result.tool_calls_made,
        success=result.success,
        error=result.error,
    )


@router.post("/{session_id}/stop", status_code=200)
async def stop_session(session_id: str) -> dict:
    info = _sessions.get(session_id)
    if not info:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")

    get_event_bus().publish(
        EventType.SESSION_END,
        {"session_id": session_id, "project": info.project_name},
    )

    _sessions.pop(session_id, None)
    _agents.pop(session_id, None)
    return {"session_id": session_id, "status": "stopped"}

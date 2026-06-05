"""Session endpoints — start, send message, stop, get state.

Sessions are persisted to disk: each turn's full message history is
saved to `~/.gundam-halo/projects/<name>/conversations/<session_id>.json`
(atomic write). On restart, sessions in memory are gone, but files
remain — a new send_message call with a known session_id will
lazily load + resume.
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
from app.core.types import Message
from app.engines.minimax import MiniMaxEngine
from app.projects import persistence
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
    resumed_from_disk: bool = False  # True if this session was loaded from disk on first send


class MessageSend(BaseModel):
    content: str


class MessageResponse(BaseModel):
    session_id: str
    user_message: str
    agent_response: str
    tool_calls_made: int
    success: bool
    error: Optional[str] = None


# In-memory caches. These can be lost on restart — disk has the truth.
_sessions: dict[str, SessionInfo] = {}
_agents: dict[str, BaseAgent] = {}
_session_files_known: set[str] = set()  # session_ids that have files on disk


def _session_id() -> str:
    return uuid.uuid4().hex[:12]


def _get_or_create_engine() -> MiniMaxEngine:
    cfg = get_config()
    if not cfg.llm.api_key:
        raise RuntimeError("MINIMAX_API_KEY not set. Set it in .env or env vars.")
    return MiniMaxEngine(
        api_key=cfg.llm.api_key,
        base_url=cfg.llm.base_url,
        model=cfg.llm.default_model,
    )


def _get_or_create_agent(
    session_id: str, project_name: str, agent_type: str
) -> BaseAgent:
    """Return a cached agent, or create one (with disk-loaded history if available)."""
    if session_id in _agents:
        return _agents[session_id]

    if not AgentRegistry.contains(agent_type):
        raise ValueError(f"Unknown agent type: {agent_type}")

    # Try to load message history from disk
    initial_messages: Optional[List[Message]] = None
    if persistence.session_exists(project_name, session_id):
        initial_messages = persistence.load_messages(project_name, session_id)
        logger.debug(
            f"Resuming session {session_id} from disk "
            f"({len(initial_messages or [])} messages)"
        )

    engine = _get_or_create_engine()
    tools = default_tools()
    agent_cls = AgentRegistry.get(agent_type)
    agent = agent_cls(
        engine,
        get_config().llm.default_model,
        tools=tools,
        initial_messages=initial_messages,
    )
    _agents[session_id] = agent
    return agent


def _index_disk_sessions() -> None:
    """On startup, scan all projects and index their session files in memory."""
    cfg = get_config()
    projects_dir = cfg.home / "projects"
    if not projects_dir.exists():
        return

    for project_dir in projects_dir.iterdir():
        if not project_dir.is_dir():
            continue
        project_name = project_dir.name
        for summary in persistence.scan_project_sessions(project_name):
            _session_files_known.add(summary.session_id)
    logger.debug(f"Indexed {len(_session_files_known)} session files on disk")


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
    # Check in-memory first
    info = _sessions.get(session_id)
    if info:
        return info

    # Check disk — if there's a saved session, we can hydrate a minimal SessionInfo
    # (project_name and agent_type are stored in the file)
    if session_id in _session_files_known:
        for project_dir in (get_config().home / "projects").iterdir():
            if not project_dir.is_dir():
                continue
            summary = next(
                (s for s in persistence.scan_project_sessions(project_dir.name) if s.session_id == session_id),
                None,
            )
            if summary:
                return SessionInfo(
                    id=summary.session_id,
                    project_name=summary.project_name,
                    agent_type=summary.agent_type,
                    started_at=summary.created_at,
                    message_count=summary.message_count,
                    resumed_from_disk=True,
                )

    raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")


@router.get("", response_model=List[SessionInfo])
async def list_sessions() -> List[SessionInfo]:
    return list(_sessions.values())


@router.post("/{session_id}/message", response_model=MessageResponse)
async def send_message(session_id: str, payload: MessageSend) -> MessageResponse:
    info = _sessions.get(session_id)
    if info is None:
        # If session exists on disk, we can still send — agent will lazy-load
        if session_id not in _session_files_known:
            raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
        # Try to find the project for this session
        project_name = None
        agent_type = "native_react"
        for pdir in (get_config().home / "projects").iterdir():
            if not pdir.is_dir():
                continue
            for s in persistence.scan_project_sessions(pdir.name):
                if s.session_id == session_id:
                    project_name = s.project_name
                    agent_type = s.agent_type
                    break
            if project_name:
                break
        if not project_name:
            raise HTTPException(status_code=500, detail="Could not find project for session")

        info = SessionInfo(
            id=session_id,
            project_name=project_name,
            agent_type=agent_type,
            started_at="",
            message_count=0,
            resumed_from_disk=True,
        )
        _sessions[session_id] = info
        info.message_count = len(persistence.load_messages(project_name, session_id) or [])

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
        agent = _get_or_create_agent(session_id, info.project_name, info.agent_type)
    except Exception as e:
        logger.error(f"Failed to create agent for session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Agent init failed: {e}")

    # Publish "agent thinking" so WebSocket subscribers see activity immediately
    get_event_bus().publish(
        EventType.AGENT_TURN_START,
        {
            "session_id": session_id,
            "project": info.project_name,
            "user_message": payload.content,
        },
    )

    try:
        result = await agent.run(payload.content)
    except Exception as e:
        logger.error(f"Agent run error in session {session_id}: {e}")
        get_event_bus().publish(
            EventType.AGENT_TURN_END,
            {"session_id": session_id, "success": False, "error": str(e)},
        )
        return MessageResponse(
            session_id=session_id,
            user_message=payload.content,
            agent_response="",
            tool_calls_made=0,
            success=False,
            error=str(e),
        )

    # Publish "agent message" with the result
    get_event_bus().publish(
        EventType.AGENT_TURN_END,
        {
            "session_id": session_id,
            "project": info.project_name,
            "tool_calls_made": result.tool_calls_made,
            "output_length": len(result.output),
            "success": result.success,
        },
    )

    # Persist the full message history to disk (atomic write)
    try:
        persistence.save_messages(
            info.project_name,
            session_id,
            result.messages,
            agent_type=info.agent_type,
        )
        _session_files_known.add(session_id)
    except Exception as e:
        logger.error(f"Failed to persist session {session_id}: {e}")
        # Continue — in-memory result is still returned, but warn

    # Update in-memory count
    info.message_count = len(result.messages)

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
    if info is None and session_id not in _session_files_known:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")

    if info is not None:
        get_event_bus().publish(
            EventType.SESSION_END,
            {"session_id": session_id, "project": info.project_name},
        )

    _sessions.pop(session_id, None)
    _agents.pop(session_id, None)
    return {"session_id": session_id, "status": "stopped"}


# Public helper for app startup
def init_persistence_on_startup() -> None:
    """Called from main.py's lifespan. Indexes on-disk sessions."""
    _index_disk_sessions()

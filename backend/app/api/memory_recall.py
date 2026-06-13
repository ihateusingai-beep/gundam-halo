"""M12 — Structured memory recall API.

Endpoints (all under ``/api/memory``):

  GET  /api/memory/sessions                — list all sessions (paginated)
  GET  /api/memory/sessions/{sid}          — single session metadata
  GET  /api/memory/sessions/{sid}/messages — full message history (SQLite)
  GET  /api/memory/search?q=...&project=   — LIKE search across messages
  GET  /api/memory/recall?q=...&k=5&user=  — semantic recall
  POST /api/memory/rebuild                 — admin: rebuild SQLite + FAISS

The existing ``/api/memory/{user}/{key}`` family stays unchanged —
that one reads from the file-based UserMemoryStore. We add new
sub-routes here for the structured layer.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.memory.lifecycle import rebuild_index, recall
from app.memory.sqlite_index import get_sqlite_index

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class SessionSummary(BaseModel):
    session_id: str
    project_name: str
    agent_type: str
    channel: str | None = None
    created_at: float
    updated_at: float
    message_count: int


class SessionsResponse(BaseModel):
    sessions: list[SessionSummary]
    total: int
    limit: int
    offset: int


class SearchHit(BaseModel):
    message_id: int
    session_id: str
    project_name: str | None = None
    seq: int
    role: str
    snippet: str
    score: float | None = None  # present for recall, None for LIKE


class RecallResponse(BaseModel):
    query: str
    k: int
    results: list[dict[str, Any]]


class RebuildResponse(BaseModel):
    sessions: int
    messages: int
    memory_entries: int
    vector_ntotal: int


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/sessions", response_model=SessionsResponse)
async def list_sessions(
    project: str | None = Query(None, description="Filter by project name"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> SessionsResponse:
    """List all sessions indexed in SQLite, newest first."""
    idx = get_sqlite_index()
    rows = idx.list_sessions(project=project, limit=limit, offset=offset)
    total = idx.count_sessions(project=project)
    return SessionsResponse(
        sessions=[
            SessionSummary(**r.to_dict()) for r in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/sessions/{session_id}", response_model=SessionSummary)
async def get_session(session_id: str) -> SessionSummary:
    idx = get_sqlite_index()
    row = idx.get_session(session_id)
    if row is None:
        raise HTTPException(
            status_code=404, detail=f"Session '{session_id}' not indexed"
        )
    return SessionSummary(**row.to_dict())


@router.get("/sessions/{session_id}/messages")
async def get_session_messages(session_id: str) -> dict[str, Any]:
    """Read a session's full message list from SQLite.

    The shape matches ``/api/sessions/{sid}/messages`` so the
    frontend can reuse the same mapper.
    """
    idx = get_sqlite_index()
    session = idx.get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=404, detail=f"Session '{session_id}' not indexed"
        )
    rows = idx.get_messages(session_id)
    return {
        "session_id": session_id,
        "project_name": session.project_name,
        "message_count": len(rows),
        "messages": [
            {
                "role": r.role,
                "content": r.content,
                "tool_calls": (
                    __import__("json").loads(r.tool_calls)
                    if r.tool_calls
                    else []
                ),
                "tool_call_id": r.tool_call_id,
                "name": r.name,
            }
            for r in rows
        ],
    }


@router.get("/search", response_model=dict[str, Any])
async def search_messages(
    q: str = Query(..., min_length=1, description="Search query"),
    project: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    """Lexical search across message content (LIKE %q%)."""
    idx = get_sqlite_index()
    rows = idx.search_messages(q, project=project, limit=limit)
    # Hydrate project name from session
    hits = []
    for r in rows:
        s = idx.get_session(r.session_id)
        hits.append(
            SearchHit(
                message_id=r.message_id,
                session_id=r.session_id,
                project_name=s.project_name if s else None,
                seq=r.seq,
                role=r.role,
                snippet=r.snippet(),
            )
        )
    return {
        "query": q,
        "count": len(hits),
        "results": [h.model_dump() for h in hits],
    }


@router.get("/recall", response_model=RecallResponse)
async def recall_endpoint(
    q: str = Query(..., min_length=1, description="Recall query"),
    k: int = Query(5, ge=1, le=50),
    user: str | None = Query(None, description="Filter memory_entry by user"),
) -> RecallResponse:
    """Semantic recall across all indexed chunks."""
    hits = recall(q, k=k, user=user)
    return RecallResponse(
        query=q,
        k=k,
        results=[h.to_dict() for h in hits],
    )


@router.post("/rebuild", response_model=RebuildResponse)
async def rebuild_endpoint() -> RebuildResponse:
    """Admin: rebuild SQLite + FAISS from disk. Idempotent."""
    stats = rebuild_index()
    return RebuildResponse(**stats)


__all__ = ["router"]

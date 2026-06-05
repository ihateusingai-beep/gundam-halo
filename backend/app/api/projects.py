"""Project endpoints — list, create, get, archive, delete."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.config import get_config
from app.core.events import EventType, get_event_bus

logger = logging.getLogger(__name__)
router = APIRouter()


class ProjectSummary(BaseModel):
    name: str
    status: str  # active | paused | archived
    created_at: str
    agent_type: str = "native_react"


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-z0-9-]+$")
    description: str = ""
    agent_type: str = "native_react"


def _project_dir(name: str) -> Path:
    cfg = get_config()
    return cfg.home / "projects" / name


def _list_projects() -> List[ProjectSummary]:
    cfg = get_config()
    projects_dir = cfg.home / "projects"
    if not projects_dir.exists():
        return []

    out: List[ProjectSummary] = []
    for entry in sorted(projects_dir.iterdir()):
        if not entry.is_dir():
            continue
        project_toml = entry / "project.toml"
        if not project_toml.exists():
            continue
        # Minimal: read name + status from project.toml
        try:
            import tomllib
            with open(project_toml, "rb") as f:
                data = tomllib.load(f)
            proj = data.get("project", {})
            out.append(
                ProjectSummary(
                    name=proj.get("name", entry.name),
                    status=proj.get("status", "active"),
                    created_at=proj.get("created_at", ""),
                    agent_type=proj.get("agent_type", "native_react"),
                )
            )
        except Exception as e:
            logger.warning(f"Failed to read {project_toml}: {e}")
    return out


@router.get("", response_model=List[ProjectSummary])
async def list_projects() -> List[ProjectSummary]:
    return _list_projects()


@router.post("", response_model=ProjectSummary, status_code=201)
async def create_project(payload: ProjectCreate) -> ProjectSummary:
    pdir = _project_dir(payload.name)
    if pdir.exists():
        raise HTTPException(status_code=409, detail=f"Project '{payload.name}' already exists")

    # Create project directory layout
    (pdir / "memory").mkdir(parents=True)
    (pdir / "conversations").mkdir(parents=True)
    (pdir / "files").mkdir(parents=True)
    (pdir / "tools").mkdir(parents=True)
    (pdir / "checkpoints").mkdir(parents=True)

    # Write project.toml
    now = datetime.utcnow().isoformat() + "Z"
    project_toml = pdir / "project.toml"
    project_toml.write_text(
        f"""[project]
name = "{payload.name}"
created_at = "{now}"
status = "active"
agent_type = "{payload.agent_type}"
description = "{payload.description}"
"""
    )

    get_event_bus().publish(
        EventType.PROJECT_CREATED,
        {"name": payload.name, "agent_type": payload.agent_type},
    )

    return ProjectSummary(
        name=payload.name,
        status="active",
        created_at=now,
        agent_type=payload.agent_type,
    )


@router.get("/{name}", response_model=ProjectSummary)
async def get_project(name: str) -> ProjectSummary:
    pdir = _project_dir(name)
    if not pdir.exists():
        raise HTTPException(status_code=404, detail=f"Project '{name}' not found")
    project_toml = pdir / "project.toml"
    if not project_toml.exists():
        raise HTTPException(status_code=500, detail="Project metadata missing")

    import tomllib
    with open(project_toml, "rb") as f:
        data = tomllib.load(f)
    proj = data.get("project", {})

    return ProjectSummary(
        name=proj.get("name", name),
        status=proj.get("status", "active"),
        created_at=proj.get("created_at", ""),
        agent_type=proj.get("agent_type", "native_react"),
    )


@router.delete("/{name}", status_code=204)
async def delete_project(name: str) -> None:
    """Delete a project. Does NOT archive — use /archive for that."""
    import shutil

    pdir = _project_dir(name)
    if not pdir.exists():
        raise HTTPException(status_code=404, detail=f"Project '{name}' not found")
    shutil.rmtree(pdir)
    logger.info(f"Deleted project: {name}")


@router.post("/{name}/archive", status_code=200)
async def archive_project(name: str) -> ProjectSummary:
    """Archive a project (moves to archive/ subdir)."""
    import shutil
    from datetime import datetime

    cfg = get_config()
    pdir = _project_dir(name)
    if not pdir.exists():
        raise HTTPException(status_code=404, detail=f"Project '{name}' not found")

    archive_root = cfg.home / "archive"
    archive_root.mkdir(exist_ok=True)
    snapshot_name = f"{name}-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"
    dest = archive_root / snapshot_name
    shutil.move(str(pdir), str(dest))

    get_event_bus().publish(
        EventType.PROJECT_ARCHIVED,
        {"name": name, "snapshot": str(dest)},
    )

    return ProjectSummary(
        name=name,
        status="archived",
        created_at="",
        agent_type="native_react",
    )


# ---------------------------------------------------------------------------
# Memory: list sessions for a project
# ---------------------------------------------------------------------------


class SessionListItem(BaseModel):
    id: str
    agent_type: str
    created_at: str
    updated_at: str
    message_count: int


@router.get("/{name}/memory", response_model=List[SessionListItem])
async def list_project_memory(name: str) -> List[SessionListItem]:
    """List all persisted sessions (conversations) for a project.

    Reads from `~/.gundam-halo/projects/<name>/conversations/*.json`.
    Useful for the Memory page in the UI to show past conversations.
    """
    from app.projects import persistence

    summaries = persistence.scan_project_sessions(name)
    return [
        SessionListItem(
            id=s.session_id,
            agent_type=s.agent_type,
            created_at=s.created_at,
            updated_at=s.updated_at,
            message_count=s.message_count,
        )
        for s in summaries
    ]


@router.get("/{name}/memory/{session_id}")
async def get_session_messages(name: str, session_id: str) -> dict:
    """Return the full message history of a persisted session."""
    from app.projects import persistence
    from app.projects.persistence import _dict_to_message

    messages = persistence.load_messages(name, session_id)
    if messages is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found in project '{name}'")

    return {
        "session_id": session_id,
        "project_name": name,
        "message_count": len(messages),
        "messages": [
            {
                "role": m.role.value,
                "content": m.content,
                "tool_calls": [
                    {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                    for tc in m.tool_calls
                ],
                "tool_call_id": m.tool_call_id,
                "name": m.name,
            }
            for m in messages
        ],
    }

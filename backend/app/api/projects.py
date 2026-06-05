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

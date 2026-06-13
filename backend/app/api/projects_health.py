"""Health probe for the per-project filesystem layer.

Returns ``{ok: true, count: N}`` where ``N`` is the number of
project directories currently on disk under
``$HALO_HOME/projects/``.

The probe is intentionally minimal — T1's scope is to wire the
``ProjectManager`` singleton into the FastAPI lifespan and prove
that the per-project FS layer is reachable. Full CRUD endpoints
are T2's job (see `app/api/projects.py` for the existing M4-era
scaffolding that T2 will refactor on top of ``ProjectManager``).

Mounted at ``/api/projects/health`` so it doesn't clash with the
existing ``GET /api/projects`` list endpoint from M4. T2 can
decide whether to keep this path, fold it into a single
``/api/projects`` plus a ``/api/projects/count`` shape, or
replace it with a more detailed readiness payload.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, FastAPI, Request

from app.projects.manager import get_project_manager

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/health")
async def projects_health(request: Request) -> dict[str, Any]:
    """Return ``{ok: true, count: N}`` for the projects feature.

    The probe is *cheap*: it calls ``ProjectManager.list()`` which
    iterates ``$HALO_HOME/projects/`` and loads each ``project.toml``
    via the Pydantic ``Project`` model. We rely on the manager to
    handle missing / corrupt project directories gracefully
    (logged warnings, skipped silently).
    """
    app: FastAPI = request.app
    pm = get_project_manager(app)
    count = pm.count()
    return {"ok": True, "count": count}

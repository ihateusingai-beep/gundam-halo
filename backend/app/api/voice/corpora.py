"""Voice self-record corpora endpoint — GET /voice/self-record-corpora.

Sprint 45: dashboard affordance — scans `$HALO_HOME/recordings/yue-self-*`
and summarises each corpus for the HeldOutEvalCard's "Will fine-tune
on: <path> (N chunks · Ms)" hint.

Sprint 56 R4: extracted from `app/api/voice_config_api.py`
(990 LoC monolith). This module owns 1 endpoint + the
`_resolve_halo_home` + `_latest_self_record_corpus` helpers
(now in `voice/_shared.py` — re-imported here for the
endpoint's use).
"""
from __future__ import annotations

import logging
from typing import Any

from app.api.ws_protocol import router
from app.api.voice._shared import (
    CORPUS_DIR_PREFIX,
    _resolve_halo_home,
)

logger = logging.getLogger(__name__)


@router.get("/voice/self-record-corpora")
async def list_self_record_corpora() -> dict[str, Any]:
    """Scan `$HALO_HOME/recordings/yue-self-*` and summarise each.

    Returns `{corpora: list, latest_path: str | null}`. Each corpus
    carries enough metadata for `HeldOutEvalCard` to render a
    "Will fine-tune on: <path> (N chunks · Ms)" hint above the
    fine-tune button without a second round-trip.

    Order: newest-first by directory mtime. The first entry is
    flagged `is_latest: true`; the rest are `is_latest: false`.

    Empty result if no corpus dirs exist yet (the user hasn't
    recorded anything). Graceful: missing `recordings/` dir →
    empty list (no 404).
    """
    from app.voice.self_record_manifest import summarise as manifest_summarise

    halo_home = _resolve_halo_home()
    recordings = halo_home / "recordings"
    if not recordings.is_dir():
        return {"corpora": [], "latest_path": None}

    dated = sorted(
        (d for d in recordings.glob(f"{CORPUS_DIR_PREFIX}*") if d.is_dir()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    corpora = []
    for i, d in enumerate(dated):
        chunk_files = list(d.glob("chunk-*.wav"))
        manifest = d / "manifest.jsonl"
        if manifest.is_file():
            ms = manifest_summarise(manifest)
            manifest_chunks = ms.total_chunks
            total_duration = ms.total_duration_s
            rejected = ms.rejected_lines
        else:
            manifest_chunks = 0
            total_duration = 0.0
            rejected = 0
        date_part = d.name[len(CORPUS_DIR_PREFIX):] if d.name.startswith(CORPUS_DIR_PREFIX) else d.name
        corpora.append({
            "path": str(d),
            "date": date_part,
            "chunk_count": len(chunk_files),
            "manifest_chunks": manifest_chunks,
            "total_duration_s": round(total_duration, 2),
            "rejected_lines": rejected,
            "is_latest": i == 0,
        })
    return {
        "corpora": corpora,
        "latest_path": corpora[0]["path"] if corpora else None,
    }


__all__ = ["list_self_record_corpora"]

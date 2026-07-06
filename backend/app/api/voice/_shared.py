"""Shared types + helpers for the voice REST API submodules.

Sprint 56 R4: extracted from `app/api/voice_config_api.py` (990
LoC monolith). This module owns the things that all 3 voice
submodules (`rest.py`, `corpora.py`, `eval_jobs.py`) need:

  - Pydantic request models (RunEvalRequest, RunFinetuneRequest)
  - Halo-home resolver + path helpers (_resolve_halo_home,
    _resolve_train_corpus_dir, _resolve_base_model_path)
  - Manifest preflight (_preflight_validate_manifest)
  - Background-thread target (_run_orchestrator_thread) — runs
    the orchestrator subprocess, marks the job's terminal
    state when done
  - UNATTRIBUTED_KEY constant (Sprint 46)

These are import-cycles-clean: `_shared` only imports from
`app.core.*` and `app.voice.*` (no app.api or app.main deps).
The 3 sibling submodules import the Pydantic models + helpers
from here.

Kept as `app/api/voice/_shared.py` (underscore prefix = "not
a FastAPI router module" — only the 3 sibling files in this
dir use it).
"""
from __future__ import annotations

import logging
import subprocess
import sys
import threading
from pathlib import Path

from fastapi import HTTPException
from pydantic import BaseModel, Field

from app.core.config import get_config
from app.core.eval_jobs import get_store
# Sprint 56 R1: app.paths is the canonical halo_home resolver.
from app.paths import halo_home, models_dir

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Common Voice yue baseline + Sprint 45 default for run-finetune.
DEFAULT_HALO_HOME = halo_home()
DEFAULT_BASE_MODEL_PATH = models_dir() / "whisper-yue-base"
CORPUS_DIR_PREFIX = "yue-self-"
# Sprint 46 — synthetic bucket for runs with empty corpus_id
# (legacy runs before the corpus_id field was added).
UNATTRIBUTED_KEY = "unattributed"


# ---------------------------------------------------------------------------
# Pydantic request models
# ---------------------------------------------------------------------------


class RunEvalRequest(BaseModel):
    """Body for POST /voice/run-held-out-eval (Sprint 40)."""

    threshold: float = Field(0.15, ge=0.0, le=1.0)
    model_size: str = Field("base", pattern="^(tiny|base|small|medium)$")
    halo_home: str | None = Field(None, max_length=512)


class RunFinetuneRequest(BaseModel):
    """Body for POST /voice/run-finetune (Sprint 40 + 45).

    All path fields are optional. When omitted, the backend
    auto-detects the most recent `yue-self-<date>/` dir under
    `$HALO_HOME/recordings/` for the corpus, and uses the Common
    Voice yue baseline checkpoint at `$HALO_HOME/models/whisper-yue-base/`
    as the fine-tune starting point.

    Sprint 45 additions:
      - `base_model_path` — explicit override of the starting
        checkpoint (pass empty string `""` to fall through to the
        HF Hub `openai/whisper-base` English-only weights).
    """

    train_corpus_dir: str | None = Field(None, max_length=512)
    base_model_path: str | None = Field(None, max_length=512)
    output_model_dir: str | None = Field(None, max_length=512)
    halo_home: str | None = Field(None, max_length=512)


# ---------------------------------------------------------------------------
# Path resolvers (Sprint 45)
# ---------------------------------------------------------------------------


def _resolve_halo_home() -> Path:
    """Resolve $HALO_HOME (env var overrides the default)."""
    return halo_home()


def _latest_self_record_corpus(halo_home: Path) -> Path | None:
    """Return the newest `yue-self-*` dir under `recordings/`.

    Sorts by mtime (newest first). Returns None if `recordings/`
    doesn't exist or has no dated subdirs.
    """
    recordings = halo_home / "recordings"
    if not recordings.is_dir():
        return None
    dated = sorted(
        (d for d in recordings.glob(f"{CORPUS_DIR_PREFIX}*") if d.is_dir()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return dated[0] if dated else None


def _resolve_train_corpus_dir(
    payload: RunFinetuneRequest, halo_home: Path
) -> Path:
    """Resolve the training corpus directory.

    Priority:
      1. `payload.train_corpus_dir` (explicit override).
      2. Latest `yue-self-*/` dir under `recordings/`.
      3. `recordings/` itself (parent fallback — only if it has a
         flat `manifest.jsonl`).
      4. HTTP 400 with a hint pointing at the Record card.
    """
    if payload.train_corpus_dir:
        return Path(payload.train_corpus_dir).expanduser().resolve()

    latest = _latest_self_record_corpus(halo_home)
    if latest is not None:
        return latest

    parent_fallback = halo_home / "recordings"
    if (parent_fallback / "manifest.jsonl").is_file():
        return parent_fallback

    raise HTTPException(
        status_code=400,
        detail=(
            "No self-record corpus found. Record at least one chunk via "
            "the Tauri Record card, or pass `train_corpus_dir` explicitly."
        ),
    )


def _resolve_base_model_path(
    payload: RunFinetuneRequest, halo_home: Path
) -> Path | None:
    """Resolve the base HF-format Whisper checkpoint.

    Priority:
      1. `payload.base_model_path` (explicit override).
      2. `$HALO_HOME/models/whisper-yue-base/` if it exists.
      3. None (let `finetune_whisper_yue.py` fall back to HF Hub
         `openai/whisper-base`).

    Returns None when no local base is found and no override was
    supplied — the orchestrator treats None as "skip the flag".
    """
    if payload.base_model_path is not None:
        stripped = payload.base_model_path.strip()
        if not stripped:
            return None  # explicit "skip"
        return Path(stripped).expanduser().resolve()
    candidate = (halo_home / "models" / "whisper-yue-base").resolve()
    return candidate if candidate.is_dir() else None


def _preflight_validate_manifest(train_dir: Path) -> str | None:
    """Validate the corpus's `manifest.jsonl`. Returns None if OK,
    else an error message suitable for surfacing to the UI.

    The check is fast (just reads the JSONL) and rejects:
      - Missing `manifest.jsonl`.
      - Empty manifest.
      - Schema-violating rows (all rows rejected).
    """
    manifest = train_dir / "manifest.jsonl"
    if not manifest.is_file():
        return (
            f"manifest.jsonl not found in {train_dir}. "
            "Did the Record card finish flushing?"
        )
    from app.voice.self_record_manifest import iter_manifest

    rows = 0
    try:
        for _sample in iter_manifest(manifest):
            rows += 1
    except FileNotFoundError as e:
        return str(e)
    if rows == 0:
        return f"manifest is empty: {manifest}"
    return None


# ---------------------------------------------------------------------------
# Background thread target
# ---------------------------------------------------------------------------


def _run_orchestrator_thread(
    job_id: str,
    args: list[str],
    halo_home: Path,
) -> None:
    """Background-thread target: run the orchestrator subprocess,
    mark the job's terminal state when done.

    Lives in `_shared` so the wiring is close to the endpoints
    that fire it (eval_jobs.py POST endpoints). Mirrors the
    watchdog's std::thread pattern from Sprint 43 (no tokio, no
    async — pure sync).
    """
    store = get_store(halo_home)
    try:
        store.mark_running(job_id)
    except Exception as e:
        logger.error(f"could not mark job {job_id} as running: {e}")
        return

    scripts_dir = Path(__file__).resolve().parent.parent.parent.parent / "scripts"
    orchestrator = scripts_dir / "run_held_out_pipeline.py"

    log_dir = halo_home / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{job_id}.log"

    cmd = [sys.executable, str(orchestrator)] + args
    try:
        with log_path.open("w", encoding="utf-8") as logf:
            proc = subprocess.run(
                cmd,
                cwd=str(scripts_dir.parent),  # backend root
                stdout=logf,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
            )
        exit_code = proc.returncode
    except Exception as e:
        logger.error(f"orchestrator for job {job_id} crashed: {e}")
        try:
            store.complete_job(
                job_id,
                exit_code=3,
                error=f"orchestrator_crash: {type(e).__name__}: {e}",
            )
        except Exception:
            pass
        return

    # Pick the most recent trend JSON (written by run_held_out_eval.py).
    trend_path: str | None = None
    try:
        results_dir = halo_home / "tests" / "voice" / "held_out_results"
        if results_dir.is_dir():
            newest = max(
                results_dir.glob("*.json"),
                key=lambda p: p.stat().st_mtime,
                default=None,
            )
            if newest is not None:
                trend_path = str(newest)
    except Exception as e:
        logger.warning(f"could not locate trend JSON for {job_id}: {e}")

    try:
        store.complete_job(
            job_id,
            exit_code=exit_code,
            trend_json_path=trend_path,
            error=None if exit_code == 0 else f"orchestrator_exit_{exit_code}",
        )
    except Exception as e:
        logger.error(f"could not mark job {job_id} complete: {e}")


__all__ = [
    # Pydantic models
    "RunEvalRequest",
    "RunFinetuneRequest",
    # Constants
    "DEFAULT_HALO_HOME",
    "DEFAULT_BASE_MODEL_PATH",
    "CORPUS_DIR_PREFIX",
    "UNATTRIBUTED_KEY",
    # Path resolvers
    "_resolve_halo_home",
    "_latest_self_record_corpus",
    "_resolve_train_corpus_dir",
    "_resolve_base_model_path",
    # Manifest preflight
    "_preflight_validate_manifest",
    # Background thread
    "_run_orchestrator_thread",
    # Re-exported for legacy imports
    "get_config",
]

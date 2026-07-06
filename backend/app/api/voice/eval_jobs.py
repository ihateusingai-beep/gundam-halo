"""Voice eval-job endpoints — held-out eval, fine-tune, list jobs, corpus breakdown.

Sprint 40: held-out eval + fine-tune background runners. The
endpoints kick off the orchestrator subprocess in a thread
(Sprint 43 watchdog pattern) so the FastAPI event loop stays
responsive while the eval / fine-tune runs for 30s-60min.

Sprint 45: server-side auto-detect for `train_corpus_dir` +
`base_model_path` + manifest preflight.

Sprint 46: GET /voice/eval-corpus-breakdown — per-corpus WER
breakdown for the dashboard's stacked bar chart.

Sprint 56 R4: extracted from `app/api/voice_config_api.py`
(990 LoC monolith). This module owns 4 endpoints + the
shared helpers (`_resolve_*`, `_preflight_*`,
`_run_orchestrator_thread`) that live in `voice/_shared.py`.
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

from fastapi import Depends, HTTPException

from app.api.ws_protocol import router
from app.api.voice._shared import (
    RunEvalRequest,
    RunFinetuneRequest,
    UNATTRIBUTED_KEY,
    _preflight_validate_manifest,
    _resolve_base_model_path,
    _resolve_halo_home,
    _resolve_train_corpus_dir,
    _run_orchestrator_thread,
)
from app.core.auth import require_auth
from app.core.config import get_config
from app.core.eval_jobs import (
    JOB_KIND_FINETUNE,
    JOB_KIND_HELD_OUT_EVAL,
    get_store,
)
# Sprint 46: module-level import so tests can monkeypatch the
# results-dir resolver (`held_out_results_dir` returns a
# hardcoded path under the repo; tests redirect to tmp_path).
from app.voice.held_out_eval import held_out_results_dir

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# POST /voice/run-held-out-eval (Sprint 40)
# ---------------------------------------------------------------------------


@router.post("/voice/run-held-out-eval", dependencies=[Depends(require_auth)])
async def post_run_held_out_eval(payload: RunEvalRequest) -> dict[str, Any]:
    """Sprint 40 — kick off a held-out eval in a background thread.

    Returns 202-style `{job_id}` immediately. The client polls
    GET /voice/run-held-out-eval/{job_id} for status.

    The eval can take 30s-2min depending on Whisper model size +
    recording length. Running it inline would block the FastAPI
    event loop; the thread keeps the UI responsive.
    """
    halo_home = Path(payload.halo_home).expanduser().resolve() if payload.halo_home else Path(get_config().home).resolve()

    store = get_store(halo_home)
    job = store.create_job(JOB_KIND_HELD_OUT_EVAL)

    args = [
        "--mode",
        "eval",
        "--threshold",
        str(payload.threshold),
        "--model-size",
        payload.model_size,
    ]
    if payload.halo_home:
        args += ["--halo-home", payload.halo_home]
    thread = threading.Thread(
        target=_run_orchestrator_thread,
        args=(job.job_id, args, halo_home),
        name=f"eval-{job.job_id}",
        daemon=True,
    )
    thread.start()
    return {"job_id": job.job_id, "status": "pending"}


# ---------------------------------------------------------------------------
# GET /voice/run-held-out-eval/{job_id} (Sprint 40)
# ---------------------------------------------------------------------------


@router.get("/voice/run-held-out-eval/{job_id}")
async def get_run_held_out_eval(job_id: str) -> dict[str, Any]:
    """Sprint 40 — poll an eval job's state.

    Returns 404 if `job_id` is unknown. Otherwise the full job state.
    """
    halo_home = Path(get_config().home).resolve()
    store = get_store(halo_home)
    job = store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"job {job_id!r} not found")
    return job.to_dict()


# ---------------------------------------------------------------------------
# POST /voice/run-finetune (Sprint 40 + 45)
# ---------------------------------------------------------------------------


@router.post("/voice/run-finetune", dependencies=[Depends(require_auth)])
async def post_run_finetune(payload: RunFinetuneRequest) -> dict[str, Any]:
    """Sprint 40 + 45 — kick off a LoRA fine-tune in a background thread.

    Fine-tune + after-eval can take 30-60 minutes (Common Voice
    yue is ~50h; LoRA on a single user's 30-min corpus is much
    faster). The thread keeps the FastAPI event loop responsive.

    Sprint 45 wiring:
      - `train_corpus_dir` auto-detected (latest `yue-self-*/`)
        when not explicitly passed.
      - `base_model_path` auto-resolved (CV-yue baseline) when
        not explicitly passed.
      - Manifest pre-flight rejects broken corpora immediately
        (returns 400 + error string), saving the user a 30-60s
        wait for the orchestrator to spawn.

    After the job completes, the user clicks "Activate
    personalised model" on the Sprint 39 ModelSwapDialog to swap
    `voice.asr.backend` + `model_path` in config.toml.
    """
    halo_home = Path(payload.halo_home).expanduser().resolve() if payload.halo_home else Path(get_config().home).resolve()

    # Sprint 45: resolve + preflight BEFORE spawning the thread.
    # Bad path / broken manifest → 400 immediately, no background
    # job created, no log file written.
    train_dir = _resolve_train_corpus_dir(payload, halo_home)
    base_model = _resolve_base_model_path(payload, halo_home)
    preflight_error = _preflight_validate_manifest(train_dir)
    if preflight_error is not None:
        raise HTTPException(status_code=400, detail=preflight_error)

    store = get_store(halo_home)
    job = store.create_job(JOB_KIND_FINETUNE)

    args = [
        "--mode",
        "finetune",
        "--halo-home",
        str(halo_home),
        "--train-corpus-dir",
        str(train_dir),
    ]
    if base_model is not None:
        args += ["--base-model-path", str(base_model)]
    if payload.output_model_dir:
        args += ["--output-model-dir", payload.output_model_dir]
    thread = threading.Thread(
        target=_run_orchestrator_thread,
        args=(job.job_id, args, halo_home),
        name=f"finetune-{job.job_id}",
        daemon=True,
    )
    thread.start()
    return {
        "job_id": job.job_id,
        "status": "pending",
        "train_corpus_dir": str(train_dir),
        "base_model_path": str(base_model) if base_model else None,
    }


# ---------------------------------------------------------------------------
# GET /voice/list-jobs (Sprint 40)
# ---------------------------------------------------------------------------


@router.get("/voice/list-jobs")
async def list_eval_jobs(limit: int = 10) -> dict[str, Any]:
    """Sprint 40 — list recent eval/finetune jobs (newest first).

    Used by the HeldOutEvalCard to show "Last eval: 2 hours ago
    (PASS)" without polling the active job.
    """
    halo_home = Path(get_config().home).resolve()
    store = get_store(halo_home)
    jobs = store.list_jobs(limit=limit)
    return {"jobs": [j.to_dict() for j in jobs]}


# ---------------------------------------------------------------------------
# GET /voice/eval-corpus-breakdown (Sprint 46)
# ---------------------------------------------------------------------------


@router.get("/voice/eval-corpus-breakdown")
async def get_eval_corpus_breakdown(limit: int = 20) -> dict[str, Any]:
    """Per-corpus WER breakdown for the HeldOutEvalCard stacked chart.

    Returns:
        {
          "by_corpus": {
            "<corpus_id>": {
              "run_count": int,
              "latest_wer_pct": float,
              "best_wer_pct": float,
              "avg_wer_pct": float,
              "first_seen_ms": int,
              "latest_seen_ms": int,
              "passed": bool   # all runs in this corpus passed?
            }
          },
          "timeline": [
            {
              "timestamp": str,
              "timestamp_ms": int,
              "wer_pct": float,
              "corpus_id": str,  # bucketed as "unattributed" if empty
              "asr_backend": str
            }
          ],
          "total_runs": int
        }

    - `by_corpus`: one entry per unique corpus_id seen in the last
      `limit` runs. Stats computed across only THAT corpus's runs.
      Sorted by `latest_seen_ms` descending (most recently active
      corpus first).
    - `timeline`: every run in chronological order (oldest first)
      with its corpus_id. Drives the stacked bar chart.
    - Empty strings (legacy unattributed runs) are bucketed under
      the synthetic key `"unattributed"` so they don't disappear.

    Graceful: missing results dir → `{by_corpus: {}, timeline: [],
    total_runs: 0}`. Malformed JSONs skipped (counted only by
    `load_eval_history` itself, which already handles that).
    """
    # held_out_results_dir is imported at module level so tests
    # can monkeypatch it (Sprint 46).
    from app.voice.held_out_eval import load_eval_history

    # load_eval_history returns newest-first; we want both:
    # - by_corpus sorted by latest_seen_ms desc (newest activity wins)
    # - timeline sorted by timestamp_ms asc (left-to-right chart)
    rows_newest_first = load_eval_history(held_out_results_dir(), limit=limit)

    by_corpus: dict[str, dict[str, Any]] = {}
    timeline: list[dict[str, Any]] = []

    # `rows_newest_first` is what load_eval_history returns — newest
    # first by timestamp_ms. We track the latest WER per corpus at
    # insertion time (the FIRST hit for a corpus IS the latest
    # because we iterate newest-first). Earlier in the loop = newer.
    for row in rows_newest_first:
        raw_corpus = str(row.get("corpus_id") or "")
        # Sprint 46: empty string → "unattributed" bucket.
        corpus_key = raw_corpus if raw_corpus else UNATTRIBUTED_KEY

        ts_ms = int(row.get("timestamp_ms", 0))
        wer_pct = float(row.get("wer_pct", 0.0))

        # Timeline (one entry per run).
        timeline.append({
            "timestamp": str(row.get("timestamp", "")),
            "timestamp_ms": ts_ms,
            "wer_pct": wer_pct,
            "corpus_id": corpus_key,
            "asr_backend": str(row.get("asr_backend", "")),
        })

        # Per-corpus accumulator.
        entry = by_corpus.get(corpus_key)
        if entry is None:
            # First time seeing this corpus in this loop iteration =
            # the latest entry (since rows are newest-first).
            entry = {
                "run_count": 0,
                "_wer_sum": 0.0,
                "_wer_min": float("inf"),
                "_latest_wer_pct": wer_pct,
                "first_seen_ms": ts_ms,
                "latest_seen_ms": ts_ms,
                "_all_passed": True,
            }
            by_corpus[corpus_key] = entry
        entry["run_count"] += 1
        entry["_wer_sum"] += wer_pct
        if wer_pct < entry["_wer_min"]:
            entry["_wer_min"] = wer_pct
        if ts_ms < entry["first_seen_ms"]:
            entry["first_seen_ms"] = ts_ms
        if ts_ms > entry["latest_seen_ms"]:
            entry["latest_seen_ms"] = ts_ms
        if not row.get("passed", False):
            entry["_all_passed"] = False

    # Project internal accumulators → public shape.
    by_corpus_public: dict[str, dict[str, Any]] = {}
    for corpus_key, entry in by_corpus.items():
        n = entry["run_count"]
        by_corpus_public[corpus_key] = {
            "run_count": n,
            "latest_wer_pct": round(entry["_latest_wer_pct"], 2),
            "best_wer_pct": round(entry["_wer_min"], 2),
            "avg_wer_pct": round(entry["_wer_sum"] / n, 2) if n else 0.0,
            "first_seen_ms": entry["first_seen_ms"],
            "latest_seen_ms": entry["latest_seen_ms"],
            "passed": entry["_all_passed"],
        }

    # Sort by_corpus by latest_seen_ms desc (most recently active first).
    by_corpus_sorted = dict(
        sorted(
            by_corpus_public.items(),
            key=lambda kv: kv[1]["latest_seen_ms"],
            reverse=True,
        )
    )

    # Sort timeline by timestamp_ms asc (oldest first → left-to-right).
    timeline.sort(key=lambda r: r["timestamp_ms"])

    return {
        "by_corpus": by_corpus_sorted,
        "timeline": timeline,
        "total_runs": len(timeline),
    }


__all__ = [
    "post_run_held_out_eval",
    "get_run_held_out_eval",
    "post_run_finetune",
    "list_eval_jobs",
    "get_eval_corpus_breakdown",
]

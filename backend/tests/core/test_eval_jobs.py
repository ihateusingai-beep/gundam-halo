"""Sprint 40 — eval_jobs unit tests.

Coverage (4 tests):
1. Pending → running → succeeded lifecycle.
2. Concurrent jobs get unique IDs (no race on the dict).
3. State persists across restart (new EvalJobStore reads JSON).
4. Orphaned running jobs (from a previous process) flip to failed
   on next startup via mark_orphaned_running_jobs_as_failed().
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.core.eval_jobs import (
    EvalJob,
    EvalJobStore,
    JOB_KIND_FINETUNE,
    JOB_KIND_HELD_OUT_EVAL,
)


def test_create_then_run_then_succeed(tmp_path: Path):
    """Happy path: create → mark running → complete with exit 0."""
    store = EvalJobStore(tmp_path)

    # Create
    job = store.create_job(JOB_KIND_HELD_OUT_EVAL)
    assert job.status == "pending"
    assert job.kind == "held-out-eval"
    assert job.job_id.startswith("held-out-eval-")

    # Mark running
    store.mark_running(job.job_id, log_path="/tmp/eval.log")
    fetched = store.get_job(job.job_id)
    assert fetched is not None
    assert fetched.status == "running"
    assert fetched.log_path == "/tmp/eval.log"
    assert fetched.finished_at is None

    # Complete (success)
    store.complete_job(
        job.job_id,
        exit_code=0,
        trend_json_path="/tmp/trend.json",
    )
    fetched = store.get_job(job.job_id)
    assert fetched.status == "succeeded"
    assert fetched.exit_code == 0
    assert fetched.trend_json_path == "/tmp/trend.json"
    assert fetched.finished_at is not None


def test_concurrent_jobs_unique_ids(tmp_path: Path):
    """Two simultaneous job creations → unique IDs, no dict race."""
    store = EvalJobStore(tmp_path)

    j1 = store.create_job(JOB_KIND_HELD_OUT_EVAL)
    j2 = store.create_job(JOB_KIND_HELD_OUT_EVAL)
    j3 = store.create_job(JOB_KIND_FINETUNE)

    assert j1.job_id != j2.job_id != j3.job_id
    # All 3 visible in list.
    jobs = store.list_jobs(limit=10)
    assert len(jobs) == 3
    assert {j.kind for j in jobs} == {"held-out-eval", "finetune"}


def test_state_persists_across_restart(tmp_path: Path):
    """A new EvalJobStore instance picks up the persisted state."""
    s1 = EvalJobStore(tmp_path)
    job = s1.create_job(JOB_KIND_HELD_OUT_EVAL)
    s1.mark_running(job.job_id)
    s1.complete_job(job.job_id, exit_code=0, trend_json_path="/tmp/x.json")

    # Simulate restart.
    s2 = EvalJobStore(tmp_path)
    fetched = s2.get_job(job.job_id)
    assert fetched is not None
    assert fetched.status == "succeeded"
    assert fetched.exit_code == 0
    assert fetched.trend_json_path == "/tmp/x.json"


def test_orphaned_running_jobs_marked_failed_on_restart(tmp_path: Path):
    """A 'running' job from a previous process is dead (its subprocess
    was reaped). The next process must mark it failed + assign
    reason='backend_restart'."""
    s1 = EvalJobStore(tmp_path)
    job = s1.create_job(JOB_KIND_FINETUNE)
    s1.mark_running(job.job_id)

    # New process loads state, then runs cleanup.
    s2 = EvalJobStore(tmp_path)
    flipped = s2.mark_orphaned_running_jobs_as_failed()
    assert flipped == 1

    fetched = s2.get_job(job.job_id)
    assert fetched.status == "failed"
    assert fetched.error == "backend_restart"
    assert fetched.exit_code == -1
    assert fetched.finished_at is not None


def test_complete_job_with_nonzero_exit_marks_failed(tmp_path: Path):
    """Failure path: complete_job with exit_code=1 → status=failed."""
    store = EvalJobStore(tmp_path)
    job = store.create_job(JOB_KIND_HELD_OUT_EVAL)
    store.mark_running(job.job_id)
    store.complete_job(
        job.job_id,
        exit_code=1,
        error="held-out WAV not found",
    )
    fetched = store.get_job(job.job_id)
    assert fetched.status == "failed"
    assert fetched.exit_code == 1
    assert fetched.error == "held-out WAV not found"


def test_unknown_kind_raises_value_error(tmp_path: Path):
    """Defensive: typo'd kind names raise instead of silently creating."""
    store = EvalJobStore(tmp_path)
    with pytest.raises(ValueError, match="unknown job kind"):
        store.create_job("totally-not-a-real-kind")


def test_state_file_is_json_parseable(tmp_path: Path):
    """Defensive: the persisted file is valid JSON (for ops/debug)."""
    import json as json_mod

    store = EvalJobStore(tmp_path)
    store.create_job(JOB_KIND_HELD_OUT_EVAL)
    state_path = tmp_path / "state" / "eval_jobs.json"
    assert state_path.is_file()
    data = json_mod.loads(state_path.read_text(encoding="utf-8"))
    assert "jobs" in data
    assert isinstance(data["jobs"], list)
    assert len(data["jobs"]) == 1
    assert data["jobs"][0]["kind"] == "held-out-eval"
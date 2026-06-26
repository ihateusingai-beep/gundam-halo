"""Eval jobs — Sprint 40 background job store for held-out eval.

This module owns the in-memory + JSON-persisted job state for
`POST /voice/run-held-out-eval` and `POST /voice/run-finetune`.
The eval can take 2 minutes (baseline) to 60 minutes (fine-tune
+ after-eval), so we MUST run it in a background thread and
return a job_id the frontend can poll.

Design notes
------------
- The job store is **process-local**: when the backend restarts,
  jobs that were "running" lose their subprocess (the OS
  reaps it). On restart we mark every previously-running job
  as "failed" with `reason: "backend_restart"` so the user
  isn't left wondering why their eval looks stuck.
- Jobs are persisted to `~/.gundam-halo/state/eval_jobs.json`
  every state transition (not every poll) — the file is small
  (< 1 KB per job) and the write is atomic via tempfile +
  os.replace.
- Thread-safe mutations via `threading.Lock`. The watchdog
  thread (Sprint 43) shares the same pattern.
- Job IDs are `<kind>-<UTC-timestamp>-<random6>` so multiple
  concurrent jobs are distinguishable in logs.
- We use a module-level singleton (mirrors `WatchdogStop` in
  Sprint 43 + `_crash_log_lock` in Sprint 43's watchdog).
  Tests get a fresh instance via `reset_for_tests()`.

The function NEVER raises on the read path. Write paths
(`start_job`, `update_job`, `complete_job`) propagate
exceptions so the caller can surface the error in their
endpoint response.
"""
from __future__ import annotations

import json
import logging
import os
import random
import tempfile
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Filename of the eval-jobs JSON state file (under HALO_HOME/state/).
STATE_FILENAME = "state/eval_jobs.json"

#: How often to flush in-memory state to disk on a running
#: job (so a backend crash doesn't lose the "running" state).
PERSIST_INTERVAL_SEC = 5

#: Job kinds supported by the orchestrator (Sprint 40).
JOB_KIND_HELD_OUT_EVAL = "held-out-eval"
JOB_KIND_FINETUNE = "finetune"
ALLOWED_JOB_KINDS = frozenset({JOB_KIND_HELD_OUT_EVAL, JOB_KIND_FINETUNE})


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------


@dataclass
class EvalJob:
    """One background eval job (held-out-eval or finetune)."""

    job_id: str
    kind: str  # "held-out-eval" | "finetune"
    status: str  # "pending" | "running" | "succeeded" | "failed"
    started_at: str  # ISO 8601 UTC
    finished_at: str | None = None
    exit_code: int | None = None
    log_path: str | None = None
    trend_json_path: str | None = None
    report_path: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialise for the API response + JSON state file."""
        return asdict(self)


# ---------------------------------------------------------------------------
# State store
# ---------------------------------------------------------------------------


class EvalJobStore:
    """Thread-safe in-memory + JSON-persisted eval job store.

    One instance per process. The module-level `get_store()`
    returns the singleton (created on first use); tests call
    `reset_for_tests()` to start fresh.
    """

    def __init__(self, home: Path) -> None:
        self._home = home
        self._lock = threading.Lock()
        self._jobs: dict[str, EvalJob] = {}
        self._load()

    # -- public API ----------------------------------------------------

    def create_job(self, kind: str) -> EvalJob:
        """Allocate a new pending job + persist.

        Raises ValueError if `kind` is not in ALLOWED_JOB_KINDS.
        """
        if kind not in ALLOWED_JOB_KINDS:
            raise ValueError(f"unknown job kind: {kind!r}")
        job_id = self._make_job_id(kind)
        job = EvalJob(
            job_id=job_id,
            kind=kind,
            status="pending",
            started_at=datetime.now(UTC).isoformat(),
        )
        with self._lock:
            self._jobs[job_id] = job
            self._persist_unlocked()
        logger.info(f"eval_jobs: created {kind} job {job_id}")
        return job

    def mark_running(self, job_id: str, log_path: str | None = None) -> None:
        """Flip pending → running."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise KeyError(f"unknown job_id: {job_id}")
            job.status = "running"
            if log_path is not None:
                job.log_path = log_path
            self._persist_unlocked()

    def complete_job(
        self,
        job_id: str,
        exit_code: int,
        trend_json_path: str | None = None,
        report_path: str | None = None,
        error: str | None = None,
    ) -> None:
        """Flip running → succeeded (exit 0) or failed (non-zero)."""
        status = "succeeded" if exit_code == 0 else "failed"
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise KeyError(f"unknown job_id: {job_id}")
            job.status = status
            job.finished_at = datetime.now(UTC).isoformat()
            job.exit_code = exit_code
            if trend_json_path is not None:
                job.trend_json_path = trend_json_path
            if report_path is not None:
                job.report_path = report_path
            if error is not None:
                job.error = error
            self._persist_unlocked()
        logger.info(
            f"eval_jobs: job {job_id} {status} (exit {exit_code})"
        )

    def get_job(self, job_id: str) -> EvalJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list_jobs(self, limit: int = 10) -> list[EvalJob]:
        """Newest-first list of jobs."""
        with self._lock:
            jobs = sorted(
                self._jobs.values(),
                key=lambda j: j.started_at,
                reverse=True,
            )
        return jobs[:limit]

    def mark_orphaned_running_jobs_as_failed(self) -> int:
        """Called at backend startup to clean up after a restart.

        Any job in "pending" or "running" status when the process
        restarted had its subprocess reaped by the OS. Mark them
        as failed so the user isn't confused.
        """
        count = 0
        with self._lock:
            for job in self._jobs.values():
                if job.status in ("pending", "running"):
                    job.status = "failed"
                    job.finished_at = datetime.now(UTC).isoformat()
                    job.exit_code = -1
                    job.error = "backend_restart"
                    count += 1
            if count:
                self._persist_unlocked()
        if count:
            logger.warning(
                f"eval_jobs: marked {count} orphaned running job(s) as failed"
            )
        return count

    # -- internals -----------------------------------------------------

    def _make_job_id(self, kind: str) -> str:
        ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        rand = "".join(random.choices("0123456789abcdef", k=6))
        return f"{kind}-{ts}-{rand}"

    def _state_path(self) -> Path:
        return self._home / STATE_FILENAME

    def _persist_unlocked(self) -> None:
        """Write the in-memory state to disk atomically.

        Caller MUST hold self._lock.
        """
        path = self._state_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "version": 1,
                "jobs": [j.to_dict() for j in self._jobs.values()],
            }
            fd, tmp = tempfile.mkstemp(
                dir=path.parent, prefix=".eval_jobs.", suffix=".tmp"
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(payload, f, ensure_ascii=False, indent=2)
                os.replace(tmp, path)
            except Exception:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise
        except Exception as e:
            logger.error(f"eval_jobs: failed to persist state: {e}")
            # NEVER raise — persistence is best-effort.

    def _load(self) -> None:
        """Read the state file on startup (idempotent)."""
        path = self._state_path()
        if not path.is_file():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            for j in data.get("jobs", []):
                job = EvalJob(
                    job_id=str(j["job_id"]),
                    kind=str(j["kind"]),
                    status=str(j["status"]),
                    started_at=str(j["started_at"]),
                    finished_at=j.get("finished_at"),
                    exit_code=j.get("exit_code"),
                    log_path=j.get("log_path"),
                    trend_json_path=j.get("trend_json_path"),
                    report_path=j.get("report_path"),
                    error=j.get("error"),
                )
                self._jobs[job.job_id] = job
            logger.info(
                f"eval_jobs: loaded {len(self._jobs)} job(s) from {path}"
            )
        except (json.JSONDecodeError, KeyError, OSError) as e:
            logger.warning(f"eval_jobs: failed to load state: {e}")


# ---------------------------------------------------------------------------
# Module singleton (mirrors watchdog._crash_log_lock pattern)
# ---------------------------------------------------------------------------

_singleton: EvalJobStore | None = None
_singleton_lock = threading.Lock()


def get_store(home: Path) -> EvalJobStore:
    """Return the process-singleton store. Constructed on first use."""
    global _singleton
    with _singleton_lock:
        if _singleton is None:
            _singleton = EvalJobStore(home)
        return _singleton


def reset_for_tests(home: Path | None = None) -> EvalJobStore:
    """Test-only — drop the singleton so the next get_store() is fresh."""
    global _singleton
    with _singleton_lock:
        _singleton = EvalJobStore(home) if home is not None else None
        return _singleton if _singleton is not None else get_store(home)


# ---------------------------------------------------------------------------
# Module exports
# ---------------------------------------------------------------------------


__all__ = [
    "ALLOWED_JOB_KINDS",
    "EvalJob",
    "EvalJobStore",
    "JOB_KIND_FINETUNE",
    "JOB_KIND_HELD_OUT_EVAL",
    "get_store",
    "reset_for_tests",
]
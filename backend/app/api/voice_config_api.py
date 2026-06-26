"""Voice REST endpoints — `/voice/status`, `/voice/config`.

Sprint 32 P1.1: extracted from `api/voice_ws.py`. The REST
endpoints (`voice_status`, `get_voice_config`, `put_voice_config`)
live here so the WS route file (`ws_protocol.py`) stays focused
on the WebSocket control loop.

The endpoints all register against the shared `router` object
imported from `ws_protocol.py`. FastAPI allows multiple modules
to add routes to the same `APIRouter` instance — FastAPI's
`include_router` walks the route table at app startup, so the
order of registration doesn't matter.

The PUT handler (`put_voice_config`) also persists changes to
`~/.gundam-halo/config.toml` via `app.core.toml_doc` (the
Sprint 32 P0-2 single-source-of-truth helper). The previous
inline regex path was fragile (multiline values, escaped
strings); `toml_doc` round-trips the document while preserving
comments and structure.
"""
from __future__ import annotations

import logging
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel, Field

from app.api.restart_handler import (
    get_restart_required,
    schedule_restart_if_needed,
    set_restart_required,
)
from app.api.ws_protocol import router
from app.core.config import get_config
from app.core.eval_jobs import (
    JOB_KIND_FINETUNE,
    JOB_KIND_HELD_OUT_EVAL,
    get_store,
)
from app.core.toml_doc import read_doc, update_section_key, write_doc

logger = logging.getLogger(__name__)


@router.get("/voice/status")
async def voice_status() -> dict[str, Any]:
    """Voice layer status — useful for the cockpit dashboard."""
    cfg = get_config().voice
    return {
        "enabled": cfg.enabled,
        "vad": {"backend": cfg.vad.backend, "model_path": cfg.vad.model_path},
        "asr": {
            "backend": cfg.asr.backend,
            "model_size": cfg.asr.model_size,
            "device": cfg.asr.device,
        },
        "tts": {"backend": cfg.tts.backend, "voice": cfg.tts.voice},
        "live2d": {"enabled": cfg.live2d.enabled, "theme": cfg.live2d.theme},
        "sample_rate": cfg.sample_rate,
        "frame_duration_ms": cfg.frame_duration_ms,
        # Sprint 16: wake phrases shipped to the dashboard so the
        # Settings → Voice tab can display + edit them.
        "wake_phrases": cfg.wake_phrases,
    }


@router.get("/voice/config")
async def get_voice_config() -> dict[str, Any]:
    """Sprint 16 + 17a + 17b: get the voice config.

    Fields:
      - wake_phrases        (Sprint 16, string[])
      - strict_wake_phrase  (Sprint 17a, bool)
      - asr_backend         (Sprint 17b, str) — current ASR
                            engine name. Read-only; changing it
                            requires a backend restart.
      - asr_corrector       (Sprint 17b, str) — current corrector.
      - restart_required    (Sprint 17b, bool) — true if a
                            recent PUT required a backend
                            restart to take effect (e.g. the
                            ASR backend changed). The
                            dashboard shows a "restart
                            required" banner when this is set.

    Kept separate from `/voice/status` so the dashboard can fetch
    the full config in one round-trip without paying for the VAD /
    ASR / TTS / Live2D fields it doesn't need to edit.
    """
    cfg = get_config().voice
    return {
        "wake_phrases": list(cfg.wake_phrases),
        "strict_wake_phrase": cfg.strict_wake_phrase,
        "asr_backend": cfg.asr.backend,
        "asr_corrector": cfg.asr.corrector,
        # Sprint 19c: always-on mic toggle. Runtime-tunable;
        # the dashboard reads it to decide which UI to show
        # (push-to-talk button vs ⏸ / ▶ toggle).
        "always_on_mic": cfg.always_on_mic,
        # Sprint 18: read the in-process flag set by
        # `put_voice_config` when the user just changed the
        # asr_backend or asr_corrector. The flag is cleared
        # by any subsequent PUT that doesn't change either
        # field (see put_voice_config).
        "restart_required": get_restart_required(),
    }


@router.get("/voice/eval-results")
async def get_voice_eval_results() -> dict[str, Any]:
    """Sprint 39 — held-out eval trend for the dashboard.

    Reads the Sprint 38 trend JSONs from
    `backend/tests/voice/held_out_results/*.json` and
    returns the most recent 7 runs (newest first) for the
    HeldOutEvalCard sparkline + the current WER threshold
    so the card can colour-code pass/fail without a second
    round-trip.

    Returns:
        {
          "latest": dict | null,   # newest run, or null if no runs
          "history": list[dict],   # most recent first, max 7
          "threshold_pct": float,  # e.g. 15.0
        }

    Each entry in `latest` / `history[*]` is the shape
    produced by `app.voice.held_out_eval.load_eval_history`:
      `{timestamp, timestamp_ms, wer_pct, passed, wav_path,
        asr_backend, duration_sec, source_path}`

    Graceful: if the results dir is missing or empty,
    returns `{"latest": null, "history": [],
    "threshold_pct": 15.0}`. If individual JSONs are
    malformed, they're skipped (warning logged) — the
    rest of the trend still loads.
    """
    from app.voice.held_out_eval import (
        DEFAULT_WER_THRESHOLD,
        held_out_results_dir,
        load_eval_history,
    )

    history = load_eval_history(held_out_results_dir(), limit=7)
    latest = history[0] if history else None

    # `load_wer_threshold()` reads from `~/.gundam-halo/test-config.toml`
    # via `halo_home()`; the API layer doesn't need to inject
    # HALO_HOME — the helper honours it for test redirection.
    from app.voice.held_out_eval import load_wer_threshold

    threshold = load_wer_threshold()

    return {
        "latest": latest,
        "history": history,
        "threshold_pct": round(threshold * 100, 2)
        if threshold != DEFAULT_WER_THRESHOLD
        else DEFAULT_WER_THRESHOLD * 100,
    }


@router.put("/voice/config")
async def put_voice_config(payload: dict[str, Any]) -> dict[str, Any]:
    """Sprint 16 + 17a + 18: update the voice config in-memory + persist
    to config.toml.

    Required payload fields (the dashboard always sends the current
    form state, so we don't accept implicit "use the current value"):
      - `wake_phrases: list[str]` — non-empty list of non-empty strings.
      - `strict_wake_phrase: bool` — if true, voice turns are
        discarded unless the ASR transcript starts with a
        configured wake phrase.

    Optional payload fields (Sprint 18):
      - `asr_backend: "whisper_local" | "yuesub"` — the ASR engine
        to load on the next voice WS connect. Omit to leave the
        current value untouched. Changing this sets
        `restart_required: true` in the response.
      - `asr_corrector: "bert" | "opencc" | "none"` — which text
        corrector to apply (yuesub backend only). Omit to leave
        the current value untouched. Changing this sets
        `restart_required: true` in the response.

    Persistence:
      - Edit `~/.gundam-halo/config.toml` [voice] section to add
        the new keys (we don't blow away the user's other [voice]
        settings — we only touch the keys we own).
      - The in-process config is updated immediately so the next
        voice turn picks up the change without a server restart.
      - For asr_backend / asr_corrector the in-process change does
        NOT affect the already-built pipeline (the voice pipeline
        is constructed at WS connect time; the new value will be
        picked up the next time the user reconnects, but we
        surface `restart_required: true` so the dashboard can
        prompt the user explicitly).
    """
    # ---- wake_phrases validation (unchanged from Sprint 16) ----
    new_phrases = payload.get("wake_phrases")
    if not isinstance(new_phrases, list) or not all(
        isinstance(p, str) and p.strip() for p in new_phrases
    ):
        raise HTTPException(
            status_code=400,
            detail="`wake_phrases` must be a non-empty list of non-empty strings",
        )
    # Normalize: strip whitespace, drop empties, dedupe (preserving order)
    seen: set[str] = set()
    normalized: list[str] = []
    for p in new_phrases:
        s = p.strip()
        if s and s not in seen:
            seen.add(s)
            normalized.append(s)
    if not normalized:
        raise HTTPException(
            status_code=400,
            detail="`wake_phrases` must contain at least one non-empty string",
        )

    # ---- Sprint 17a: strict_wake_phrase validation ----
    # The field is required in the payload. We don't accept
    # implicit "use the current value" — the dashboard is the
    # source of truth for the user's intent and should always
    # send the form's current state.
    if "strict_wake_phrase" not in payload:
        raise HTTPException(
            status_code=400,
            detail="`strict_wake_phrase` is required (send the current toggle state)",
        )
    new_strict = payload["strict_wake_phrase"]
    if not isinstance(new_strict, bool):
        raise HTTPException(
            status_code=400,
            detail="`strict_wake_phrase` must be a boolean",
        )

    # ---- Sprint 19c: optional always_on_mic ----
    # Runtime-tunable (no restart). If absent, the current
    # value is left untouched. If present, must be a bool.
    new_always_on_mic: bool | None = None
    if "always_on_mic" in payload:
        raw = payload["always_on_mic"]
        if not isinstance(raw, bool):
            raise HTTPException(
                status_code=400,
                detail="`always_on_mic` must be a boolean",
            )
        new_always_on_mic = raw

    # ---- Sprint 18: optional asr_backend / asr_corrector validation ----
    # Both are optional. If absent, the current value is left
    # untouched and `restart_required` is not flipped for that
    # field. If present, the value must be one of the known
    # engines / correctors; otherwise we return 400.
    new_asr_backend: str | None = None
    if "asr_backend" in payload:
        raw = payload["asr_backend"]
        if not isinstance(raw, str):
            raise HTTPException(
                status_code=400,
                detail="`asr_backend` must be a string",
            )
        if raw not in ("whisper_local", "yuesub", "whisper_hf"):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"`asr_backend` must be one of: whisper_local, yuesub, "
                    f"whisper_hf (got {raw!r})"
                ),
            )
        new_asr_backend = raw

    new_asr_corrector: str | None = None
    if "asr_corrector" in payload:
        raw = payload["asr_corrector"]
        if not isinstance(raw, str):
            raise HTTPException(
                status_code=400,
                detail="`asr_corrector` must be a string",
            )
        if raw not in ("bert", "opencc", "none"):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"`asr_corrector` must be one of: bert, opencc, none "
                    f"(got {raw!r})"
                ),
            )
        new_asr_corrector = raw

    # Update in-memory config (so the next turn picks it up).
    cfg = get_config()
    cfg.voice.wake_phrases = normalized
    cfg.voice.strict_wake_phrase = new_strict
    # Sprint 19c: always_on_mic is runtime-tunable; apply
    # in-memory immediately so the next /voice/config GET
    # reflects the new value.
    if new_always_on_mic is not None:
        cfg.voice.always_on_mic = new_always_on_mic

    # Sprint 18: diff vs current for restart_required. If the
    # user actually changed asr_backend or asr_corrector (i.e.
    # sent a value AND that value differs from the in-memory
    # value), the dashboard should prompt the user to restart
    # the backend. wake_phrases and strict_wake_phrase are
    # runtime-tunable and don't require a restart.
    prev_asr_backend = cfg.voice.asr.backend
    prev_asr_corrector = cfg.voice.asr.corrector

    if new_asr_backend is not None:
        cfg.voice.asr.backend = new_asr_backend
    if new_asr_corrector is not None:
        cfg.voice.asr.corrector = new_asr_corrector

    restart_required = (
        (new_asr_backend is not None and new_asr_backend != prev_asr_backend)
        or (new_asr_corrector is not None and new_asr_corrector != prev_asr_corrector)
    )

    # Sprint 19b: auto-restart on ASR / corrector change. We
    # schedule a self-restart in 5 seconds so the new pipeline
    # (FsmnVAD + YuesubASR + corrector) loads on the new
    # process. The PUT response returns immediately; the
    # 5s grace gives in-flight voice turns time to finish.
    # Persist the in-process flag for the GET endpoint. If
    # the user just changed either asr field, set the flag.
    # If they sent a PUT that *didn't* touch either asr field,
    # clear it (the previous banner is now stale — they
    # already restarted or decided to keep the old value).
    # Note: this is process-local; the flag clears on backend
    # restart, which is the right semantic (the restart picks
    # up the new value).
    set_restart_required(restart_required)

    restart_scheduled = schedule_restart_if_needed(
        restart_required=restart_required,
        reason="asr_config_change",
    )

    # Invalidate the cache so future get_config() reloads from disk.
    from app.core import config as config_mod

    config_mod._config = None

    # Persist to config.toml. We use `tomlkit` via `app.core.toml_doc`
    # to read + mutate the doc in-place, then atomically write it
    # back. The previous regex path was fragile (didn't handle
    # multiline values or escaped strings); tomlkit round-trips
    # the document while preserving comments and structure.
    #
    # Each `update_section_key` call auto-creates the target
    # section + any intermediate dotted-path tables (e.g. writing
    # to "voice.asr" auto-creates `[voice]` if missing). This
    # replaces the old regex + "append at end of file" fallback.
    config_path = Path(cfg.home) / "config.toml"
    try:
        doc = read_doc(config_path)
        update_section_key(doc, "voice", "wake_phrases", normalized)
        update_section_key(doc, "voice", "strict_wake_phrase", new_strict)
        if new_always_on_mic is not None:
            update_section_key(
                doc, "voice", "always_on_mic", new_always_on_mic
            )
        if new_asr_backend is not None:
            update_section_key(
                doc, "voice.asr", "backend", new_asr_backend
            )
        if new_asr_corrector is not None:
            update_section_key(
                doc, "voice.asr", "corrector", new_asr_corrector
            )
        write_doc(config_path, doc)
    except Exception as e:
        logger.error(f"failed to persist voice config: {e}")
        # We've already updated the in-memory config; surface the
        # write error so the dashboard can show a warning.
        return {
            "wake_phrases": normalized,
            "strict_wake_phrase": new_strict,
            "asr_backend": cfg.voice.asr.backend,
            "asr_corrector": cfg.voice.asr.corrector,
            "always_on_mic": cfg.voice.always_on_mic,
            "restart_required": restart_required,
            "restart_scheduled": restart_scheduled,
            "persisted": False,
            "error": str(e),
        }

    return {
        "wake_phrases": normalized,
        "strict_wake_phrase": new_strict,
        "asr_backend": cfg.voice.asr.backend,
        "asr_corrector": cfg.voice.asr.corrector,
        "always_on_mic": cfg.voice.always_on_mic,
        "restart_required": restart_required,
        "restart_scheduled": restart_scheduled,
        "persisted": True,
    }


# ---------------------------------------------------------------------------
# Sprint 40 — held-out eval + fine-tune background runners
# ---------------------------------------------------------------------------


class RunEvalRequest(BaseModel):
    """Body for POST /voice/run-held-out-eval (Sprint 40)."""

    threshold: float = Field(0.15, ge=0.0, le=1.0)
    model_size: str = Field("base", pattern="^(tiny|base|small|medium)$")
    halo_home: str | None = Field(None, max_length=512)


class RunFinetuneRequest(BaseModel):
    """Body for POST /voice/run-finetune (Sprint 40)."""

    train_corpus_dir: str | None = Field(None, max_length=512)
    output_model_dir: str | None = Field(None, max_length=512)
    halo_home: str | None = Field(None, max_length=512)


def _run_orchestrator_thread(
    job_id: str,
    args: list[str],
    halo_home: Path,
) -> None:
    """Background-thread target: run the orchestrator subprocess,
    mark the job's terminal state when done.

    Lives in voice_config_api.py to keep the wiring close to the
    endpoints that fire it. Mirrors the watchdog's std::thread
    pattern from Sprint 43 (no tokio, no async — pure sync).
    """
    store = get_store(halo_home)
    try:
        store.mark_running(job_id)
    except Exception as e:
        logger.error(f"could not mark job {job_id} as running: {e}")
        return

    scripts_dir = Path(__file__).resolve().parent.parent.parent / "scripts"
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


@router.post("/voice/run-held-out-eval")
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


@router.post("/voice/run-finetune")
async def post_run_finetune(payload: RunFinetuneRequest) -> dict[str, Any]:
    """Sprint 40 — kick off a LoRA fine-tune in a background thread.

    Fine-tune + after-eval can take 30-60 minutes (Common Voice
    yue is ~50h; LoRA on a single user's 30-min corpus is much
    faster). The thread keeps the FastAPI event loop responsive.

    After the job completes, the user clicks "Activate
    personalised model" on the Sprint 39 ModelSwapDialog to swap
    `voice.asr.backend` + `model_path` in config.toml.
    """
    halo_home = Path(payload.halo_home).expanduser().resolve() if payload.halo_home else Path(get_config().home).resolve()

    store = get_store(halo_home)
    job = store.create_job(JOB_KIND_FINETUNE)

    args = [
        "--mode",
        "finetune",
        "--halo-home",
        str(halo_home),
    ]
    if payload.train_corpus_dir:
        args += ["--train-corpus-dir", payload.train_corpus_dir]
    if payload.output_model_dir:
        args += ["--output-model-dir", payload.output_model_dir]
    thread = threading.Thread(
        target=_run_orchestrator_thread,
        args=(job.job_id, args, halo_home),
        name=f"finetune-{job.job_id}",
        daemon=True,
    )
    thread.start()
    return {"job_id": job.job_id, "status": "pending"}


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


__all__ = [
    "voice_status",
    "get_voice_config",
    "put_voice_config",
    "post_run_held_out_eval",
    "get_run_held_out_eval",
    "post_run_finetune",
    "list_eval_jobs",
]
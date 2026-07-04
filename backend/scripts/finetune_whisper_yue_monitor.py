"""M9-E Layer 2 — background training monitor.

Sprint 19d follow-up: the actual training run lives
in a 3h+ wall clock session (Sprint 20+ in a
dedicated session with the user present). This
helper is the **monitoring wrapper** the user runs
ALONGSIDE the training script:

    # Terminal 1
    cd backend
    .venv/bin/python scripts/finetune_whisper_yue.py \\
        2>&1 | tee /tmp/cv-yue-train.log &
    TRAIN_PID=$!

    # Terminal 2 (or a separate mavis session)
    .venv/bin/python scripts/finetune_whisper_yue_monitor.py \\
        --log /tmp/cv-yue-train.log \\
        --pid $TRAIN_PID

The monitor polls the log file every 5 minutes
(default) and exits when:
  - the training process has exited (clean or
    crash), and the WER eval.json has been written
    (success) or the log shows a fatal error
  - 30 minutes pass without any new log line
    (likely OOM or hang — the user investigates
    manually)
  - the user sends SIGINT to the monitor (Ctrl-C)

The exit codes mirror `finetune_whisper_yue.py`:
  - 0 — success (WER <= threshold; model saved)
  - 1 — bad dataset version (script rejected input)
  - 2 — WER > threshold (model saved, but the eval
    failed the acceptance gate)
  - 3 — process crashed / OOM (not in the
    training script's own exit codes)
  - 4 — no log activity for 30+ minutes (hang /
    stuck; the user must investigate)

The monitor is INTENTIONALLY simple — it does not
parse the training log, does not download datasets,
does not load models. It just watches the log and
the process. The hard work is in the training
script itself; the monitor is the safety net.

This script does NOT depend on the `train` extra
(it's pure stdlib + psutil-free — it reads the log
and uses `os.kill(pid, 0)` to check process
existence).
"""
from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import time
from pathlib import Path

logger = logging.getLogger("finetune_monitor")

# Sprint 56 R1: import the canonical halo_home + models_dir so the
# monitor's default --output_dir tracks $HALO_HOME consistently.
from _script_lib import resolve_halo_home  # noqa: F401  (back-compat)
from app.paths import models_dir as _MODELS_DIR


# Polling interval (seconds). 5 min is a reasonable
# default — fast enough to catch an OOM before the
# user gets back, slow enough to not pollute the log.
DEFAULT_POLL_INTERVAL_S = 300  # 5 min
# No-log-activity timeout (seconds). If the training
# log hasn't been touched for 30 min, something is
# very wrong (likely OOM, or the process is hung in
# a checkpoint save). 30 min is well over the normal
# 60-90 sec per training step on M-series.
DEFAULT_STALL_TIMEOUT_S = 1800  # 30 min


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Background monitor for the M9-E "
        "Layer 2 fine-tune training run. Polls the "
        "log file and the training process; exits "
        "with a non-zero code on crash / hang / "
        "WER-too-high."
    )
    p.add_argument(
        "--log",
        type=Path,
        required=True,
        help="Path to the tee'd training log file (the "
        "monitor reads mtime + tail to detect stalls).",
    )
    p.add_argument(
        "--pid",
        type=int,
        required=True,
        help="PID of the running training process. The "
        "monitor uses os.kill(pid, 0) to check if the "
        "process is still alive (no psutil dep).",
    )
    p.add_argument(
        # Sprint 56 R1: route through `app.paths.models_dir()` so
        # the monitor's default tracks $HALO_HOME consistently.
        "--output_dir",
        type=Path,
        default=_MODELS_DIR() / "whisper-yue-base/",
        help="Training output dir. The monitor waits "
        "for eval.json to appear here as the success "
        "marker.",
    )
    p.add_argument(
        "--poll_interval_s",
        type=int,
        default=DEFAULT_POLL_INTERVAL_S,
        help="Seconds between polls. Default 300 (5 min).",
    )
    p.add_argument(
        "--stall_timeout_s",
        type=int,
        default=DEFAULT_STALL_TIMEOUT_S,
        help="If the log file hasn't been modified in "
        "this many seconds, the monitor exits with "
        "code 4 (hang). Default 1800 (30 min).",
    )
    return p.parse_args()


def _is_process_alive(pid: int) -> bool:
    """Check if a process is alive without psutil.

    Two-step check:
      1. `os.kill(pid, 0)` — fast check. Returns 0
         if the process exists (even if zombie on
         Linux; ESRCH if the PID slot is invalid).
      2. `os.waitpid(pid, WNOHANG)` — slow but
         authoritative. Returns (0, 0) if the
         process is still running, (pid, status)
         if the process has exited, and ESRCH if
         the PID is unknown to the system. **But**
         `waitpid` returns ECHILD if the target is
         the calling process itself (you can't
         reap yourself) — so we fall back to
         `os.kill(pid, 0)` in that case (which
         correctly returns 0 for the live self-
         process).

    Why both: `os.kill(pid, 0)` alone is unreliable
    for zombie processes on Linux — a reaped
    zombie keeps its PID in the system process
    table until the parent calls `wait()`, and
    `kill(pid, 0)` returns 0 (success) for the
    zombie. macOS ESRCHs the zombie immediately,
    so the same code behaves differently on the
    two platforms. `os.waitpid(pid, WNOHANG)` is
    portable: reaped zombies are reported as
    `(pid, status)`, and the monitor treats that
    as "the process has exited".

    The own-pid fallback is the corner case for
    unit tests where the test process is its own
    training process.
    """
    if pid == os.getpid():
        # waitpid on self returns ECHILD. We know
        # the self process is alive (it's running
        # this function), so short-circuit.
        return True
    try:
        pid_reaped, _status = os.waitpid(pid, os.WNOHANG)
    except ChildProcessError:
        # ESRCH / ECHILD — no such process (the
        # PID slot is invalid, has been recycled,
        # or the parent is not us and the kernel
        # refuses to let us reap a non-child).
        return False
    if pid_reaped == 0:
        # WNOHANG didn't find anything to reap. The
        # process is still running.
        return True
    # pid_reaped == pid: we just reaped a zombie.
    # The training script has exited.
    return False


def _log_mtime(path: Path) -> float:
    """Return the log file's mtime as a Unix timestamp,
    or 0.0 if the file doesn't exist yet."""
    try:
        return path.stat().st_mtime
    except FileNotFoundError:
        return 0.0


def _tail_log(path: Path, n: int = 20) -> str:
    """Return the last N lines of the log for the exit
    message. Cheap — the log is line-oriented text
    and we only need a small tail.
    """
    if not path.exists():
        return "<log file does not exist yet>"
    try:
        # Read the whole file (small enough) and
        # return the last n lines. Avoids seek-from-end
        # logic that breaks on log rotation.
        text = path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        return "\n".join(lines[-n:])
    except Exception as e:
        return f"<failed to read log: {e}>"


def _eval_appeared(output_dir: Path) -> bool:
    """The training script writes `eval.json` to the
    output dir only after the WER eval completes
    (success or fail-with-exit-2). Used as the
    primary success marker.
    """
    return (output_dir / "eval.json").exists()


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logger.info(
        f"Monitor started: pid={args.pid} log={args.log} "
        f"output_dir={args.output_dir} "
        f"poll={args.poll_interval_s}s "
        f"stall={args.stall_timeout_s}s"
    )

    # SIGINT handler so the user can Ctrl-C the
    # monitor without killing the training run.
    stop_requested = {"value": False}

    def _request_stop(_signum, _frame):
        stop_requested["value"] = True
        logger.info("SIGINT received, stopping monitor")

    signal.signal(signal.SIGINT, _request_stop)
    signal.signal(signal.SIGTERM, _request_stop)

    last_log_mtime_seen = _log_mtime(args.log)
    last_log_change_at = time.time() if last_log_mtime_seen > 0 else None

    while not stop_requested["value"]:
        time.sleep(args.poll_interval_s)

        # Check 1: process alive?
        if not _is_process_alive(args.pid):
            logger.info(
                f"Training process (pid={args.pid}) has exited. "
                f"Checking for eval.json success marker…"
            )
            if _eval_appeared(args.output_dir):
                logger.info(
                    f"eval.json found at {args.output_dir / 'eval.json'}. "
                    f"Training succeeded."
                )
                return 0
            else:
                logger.error(
                    f"Training process exited without eval.json. "
                    f"Last 20 log lines:\n{_tail_log(args.log)}"
                )
                return 3  # crash

        # Check 2: log activity (stall detection)
        mtime = _log_mtime(args.log)
        if mtime <= 0:
            # The training script hasn't written any
            # log yet. We don't flag a stall here
            # because the script may be still in the
            # dataset download phase (~30 min for 50h
            # CV yue). We only flag a stall once the
            # log has been written at least once.
            continue
        if mtime > last_log_mtime_seen:
            last_log_mtime_seen = mtime
            last_log_change_at = time.time()
            logger.debug(f"Log updated: mtime={mtime}")
        else:
            if last_log_change_at is None:
                # First time we see the log — record the
                # mtime and start the stall timer.
                last_log_mtime_seen = mtime
                last_log_change_at = time.time()
            else:
                stall_s = time.time() - last_log_change_at
                if stall_s > args.stall_timeout_s:
                    logger.error(
                        f"Log file unchanged for {stall_s:.0f}s "
                        f"(>{args.stall_timeout_s}s threshold). "
                        f"Likely OOM or hang. Last 20 log lines:\n"
                        f"{_tail_log(args.log)}"
                    )
                    return 4  # hang

    # If we exit the loop via SIGINT, treat that as
    # "user wants the monitor to stop, but the
    # training is presumably still running" — return
    # 0 (clean exit).
    logger.info("Monitor stopped by user (SIGINT/SIGTERM)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

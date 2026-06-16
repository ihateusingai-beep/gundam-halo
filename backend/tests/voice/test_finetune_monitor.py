"""Smoke tests for the M9-E Layer 2 training monitor.

Verifies:
  - Script imports without errors
  - `python scripts/finetune_whisper_yue_monitor.py --help`
    exits 0
  - `_is_process_alive` correctly reports alive / dead
    using the current process (no psutil dep)
  - `_eval_appeared` returns False when the output
    dir doesn't exist, True after we write the
    marker file
  - `_log_mtime` returns 0.0 for a missing file and
    the actual mtime for a real file
  - The full end-to-end "training done + eval.json
    present" path returns exit code 0
  - The full end-to-end "training done + no eval"
    path returns exit code 3 (crash)
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest


MONITOR_SCRIPT = (
    Path(__file__).resolve().parent.parent.parent
    / "scripts"
    / "finetune_whisper_yue_monitor.py"
)


def _load_monitor_module():
    """Load the monitor as a module. Stdlib-only —
    no app.* deps, so we just use plain importlib."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "finetune_monitor_test", MONITOR_SCRIPT
    )
    if spec is None or spec.loader is None:
        pytest.fail(f"could not load {MONITOR_SCRIPT}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def test_monitor_script_is_importable():
    mod = _load_monitor_module()
    assert hasattr(mod, "main"), "monitor should expose a main()"
    assert hasattr(mod, "_is_process_alive")
    assert hasattr(mod, "_eval_appeared")
    assert hasattr(mod, "_log_mtime")


def test_monitor_script_help_exits_zero():
    result = subprocess.run(
        [sys.executable, str(MONITOR_SCRIPT), "--help"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, (
        f"--help exited with {result.returncode}:\n"
        f"stdout={result.stdout}\nstderr={result.stderr}"
    )
    for flag in ("--log", "--pid", "--output_dir",
                 "--poll_interval_s", "--stall_timeout_s"):
        assert flag in result.stdout, (
            f"--help should document {flag}"
        )


def test_is_process_alive_current_process():
    mod = _load_monitor_module()
    # The current pytest process is alive.
    assert mod._is_process_alive(os.getpid()) is True
    # PID 1 (launchd on macOS) is alive too; we don't
    # assert it because some CI environments use a
    # different init process. Pick a PID that we
    # KNOW is dead: a huge random number.
    assert mod._is_process_alive(999_999_999) is False


def test_eval_appeared_true_and_false(tmp_path):
    mod = _load_monitor_module()
    out_dir = tmp_path / "model"
    # No eval.json yet.
    assert mod._eval_appeared(out_dir) is False
    # Write the marker.
    out_dir.mkdir()
    (out_dir / "eval.json").write_text(
        '{"wer": 0.15, "threshold": 0.20}', encoding="utf-8"
    )
    assert mod._eval_appeared(out_dir) is True


def test_log_mtime_missing_and_real(tmp_path):
    mod = _load_monitor_module()
    missing = tmp_path / "does-not-exist.log"
    assert mod._log_mtime(missing) == 0.0
    real = tmp_path / "real.log"
    real.write_text("hello\n", encoding="utf-8")
    mtime = mod._log_mtime(real)
    assert mtime > 0.0
    # The mtime should be within the last few seconds.
    assert abs(mtime - time.time()) < 5.0


def test_monitor_returns_0_when_process_dies_and_eval_appears(tmp_path):
    """End-to-end happy path: spawn a 2s sleeper,
    write eval.json during the sleep, run the monitor
    pointing at the sleeper. The monitor should
    detect the process death on the next poll, find
    eval.json, and exit 0.
    """
    import subprocess as sp

    out_dir = tmp_path / "model"
    out_dir.mkdir()
    log = tmp_path / "train.log"
    log.write_text("starting...\n", encoding="utf-8")

    # A child process that writes the eval.json file
    # then dies. This simulates a successful training
    # run.
    script = (
        "import json, os, sys, time\n"
        f"out = {str(out_dir)!r}\n"
        f"log = {str(log)!r}\n"
        "with open(log, 'a') as f: f.write('step 1\\n')\n"
        "with open(os.path.join(out, 'eval.json'), 'w') as f:\n"
        "    json.dump({'wer': 0.12, 'threshold': 0.20}, f)\n"
        "with open(log, 'a') as f: f.write('done\\n')\n"
    )
    sleeper = sp.Popen([sys.executable, "-c", script])
    try:
        result = sp.run(
            [
                sys.executable,
                str(MONITOR_SCRIPT),
                "--log", str(log),
                "--pid", str(sleeper.pid),
                "--output_dir", str(out_dir),
                "--poll_interval_s", "1",
                "--stall_timeout_s", "60",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, (
            f"expected 0 (success), got {result.returncode}:\n"
            f"stdout={result.stdout}\nstderr={result.stderr}"
        )
        # The monitor uses logging.basicConfig which
        # writes to stderr by default. Both stdout
        # and stderr are checked.
        combined = result.stdout + result.stderr
        assert "Training succeeded" in combined or "eval.json" in combined, (
            f"output missing success marker: "
            f"stdout={result.stdout!r} "
            f"stderr={result.stderr!r}"
        )
    finally:
        if sleeper.poll() is None:
            sleeper.kill()
            sleeper.wait()


def test_monitor_returns_3_on_no_eval_after_death(tmp_path):
    """End-to-end: a 2s sleeper that does NOT write
    eval.json. The monitor should detect the process
    death on the next poll, find NO eval.json, and
    exit 3 (crash).
    """
    import subprocess as sp

    log = tmp_path / "train.log"
    log.write_text("starting...\n", encoding="utf-8")
    out_dir = tmp_path / "model"
    # Don't mkdir — eval.json won't appear.
    sleeper = sp.Popen(
        [sys.executable, "-c", "import time; time.sleep(2)"],
    )
    try:
        result = sp.run(
            [
                sys.executable,
                str(MONITOR_SCRIPT),
                "--log", str(log),
                "--pid", str(sleeper.pid),
                "--output_dir", str(out_dir),
                "--poll_interval_s", "1",
                "--stall_timeout_s", "60",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 3, (
            f"expected 3 (crash), got {result.returncode}:\n"
            f"stdout={result.stdout}\nstderr={result.stderr}"
        )
        # The log should mention the crash reason.
        combined = result.stdout + result.stderr
        assert "exited without eval.json" in combined, (
            f"output missing crash marker: "
            f"stdout={result.stdout!r} "
            f"stderr={result.stderr!r}"
        )
    finally:
        if sleeper.poll() is None:
            sleeper.kill()
            sleeper.wait()

"""Sprint 40 — held-out eval orchestrator.

A single CLI that composes the existing Sprint 38 scripts:
  - `scripts/record-held-out.sh`    (interactive recorder)
  - `scripts/run_held_out_eval.py`  (single eval runner)
  - `scripts/finetune_whisper_yue.py` (LoRA fine-tune recipe)

into a 1-command pipeline: baseline → fine-tune → after-eval →
diff report. This is the user-facing path that closes M9-E
Layer 2 acceptance criterion 6 (WER < 10% with personalised
model active) in 1-2 hours.

Modes (mutually exclusive):
    record     Just record a held-out clip (delegates to
               scripts/record-held-out.sh).
    eval       Just run eval against the current backend
               (delegates to scripts/run_held_out_eval.py).
    finetune   Just fine-tune on the user's training corpus
               (delegates to scripts/finetune_whisper_yue.py).
    full       Run the complete pipeline:
                 1. baseline eval (current backend)
                 2. fine-tune (Common Voice yue or self-record)
                 3. after eval (whisper_hf + new checkpoint)
                 4. diff report (baseline WER → after WER)

The orchestrator NEVER reimplements the individual scripts. It
subprocess.run()s them and chains their exit codes. This keeps
the single-script paths stable (existing tests + cron jobs
keep working).

Usage:
    cd backend && uv run python scripts/run_held_out_pipeline.py --mode full
    uv run python scripts/run_held_out_pipeline.py --mode eval --threshold 0.10
    uv run python scripts/run_held_out_pipeline.py --mode finetune \
        --train-corpus-dir ~/.gundam-halo/recordings/yue-self-2026-06-27/

Exit codes:
    0 — success (mode completed; for `full`, after-eval PASSED)
    1 — eval failure (mode completed; for `full`, after-eval FAILED)
    2 — dependency missing (no held-out WAV, no corpus, etc.)
    3 — backend / subprocess failure (orchestrator couldn't run)
"""
from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

# Path bootstrap — `python scripts/run_held_out_pipeline.py` needs to find `app.*`
BACKEND_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = BACKEND_DIR / "scripts"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Default locations (overridable via flags).
DEFAULT_HALO_HOME = Path.home() / ".gundam-halo"
DEFAULT_TRAIN_CORPUS_DIR = DEFAULT_HALO_HOME / "recordings"
DEFAULT_BASE_MODEL_PATH = DEFAULT_HALO_HOME / "models" / "whisper-yue-base"
DEFAULT_OUTPUT_MODEL_DIR = DEFAULT_HALO_HOME / "models" / "whisper-yue-personalised"
DEFAULT_THRESHOLD = 0.15  # Sprint 26 §4.3 baseline target
LOG_FILE_SUFFIX = ".orchestrator.log"

logger = logging.getLogger("orchestrator")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__.split("\n\n")[0] if __doc__ else "Eval pipeline",
    )
    p.add_argument(
        "--mode",
        choices=["record", "eval", "finetune", "full"],
        default="full",
        help="Pipeline mode (default: full = baseline → finetune → after → diff).",
    )
    p.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_THRESHOLD,
        help=f"WER pass/fail threshold (default: {DEFAULT_THRESHOLD}).",
    )
    p.add_argument(
        "--model-size",
        choices=["tiny", "base", "small", "medium"],
        default="base",
        help="Whisper base model size (default: base — see M9-E for why not medium).",
    )
    p.add_argument(
        "--train-corpus-dir",
        type=Path,
        default=DEFAULT_TRAIN_CORPUS_DIR,
        help=(
            "Training corpus dir — directory containing manifest.jsonl. "
            "Default: %(default)s. For self-record corpora, point at "
            "$HALO_HOME/recordings/yue-self-<date>/."
        ),
    )
    p.add_argument(
        "--base-model-path",
        # type=str (NOT Path) so empty string '' is preserved — argparse
        # converts '' → '.' (current dir) when type=Path. We need to
        # distinguish "skip the flag" from "default the flag" downstream.
        type=str,
        default=str(DEFAULT_BASE_MODEL_PATH),
        help=(
            "Base HF-format Whisper checkpoint to fine-tune from. "
            "Default: %(default)s (Common Voice yue baseline). "
            "Pass an empty string ('') to skip — falls back to the HF "
            "Hub openai/whisper-base (English-only) for pure self-record "
            "experiments."
        ),
    )
    p.add_argument(
        "--output-model-dir",
        type=Path,
        default=DEFAULT_OUTPUT_MODEL_DIR,
        help=f"Fine-tuned model output dir (default: {DEFAULT_OUTPUT_MODEL_DIR}).",
    )
    p.add_argument(
        "--halo-home",
        type=Path,
        default=None,
        help=f"HALO_HOME override (default: $HALO_HOME or {DEFAULT_HALO_HOME}).",
    )
    p.add_argument(
        "--skip-finetune-eval",
        action="store_true",
        help="In `full` mode, skip the after-eval (just run fine-tune).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands without executing them (for debugging).",
    )
    p.add_argument(
        "--log-file",
        type=Path,
        default=None,
        help="Write orchestrator logs to this file (default: stdout only).",
    )
    return p.parse_args(argv)


# ---------------------------------------------------------------------------
# Subprocess helpers
# ---------------------------------------------------------------------------


def _resolve_halo_home(args: argparse.Namespace) -> Path:
    import os

    if args.halo_home is not None:
        return args.halo_home.expanduser().resolve()
    env = os.environ.get("HALO_HOME")
    if env:
        return Path(env).expanduser().resolve()
    return DEFAULT_HALO_HOME.resolve()


def _run_subprocess(
    cmd: list[str],
    cwd: Path,
    log_path: Path | None,
    dry_run: bool,
) -> int:
    """Run a single subprocess. Streams stdout to log_path (if given).

    Returns the exit code. NEVER raises — caller decides what to
    do with non-zero.
    """
    print(f"[orchestrator] running: {' '.join(cmd)}")
    if dry_run:
        return 0
    log_fp = None
    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_fp = log_path.open("a", encoding="utf-8")
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            stdout=log_fp if log_fp else subprocess.PIPE,
            stderr=subprocess.STDOUT if log_fp else subprocess.PIPE,
            text=True,
            check=False,
        )
        if log_fp is None:
            # We captured — echo to stdout for the pilot's eyes.
            if proc.stdout:
                print(proc.stdout, end="")
            if proc.stderr:
                print(proc.stderr, end="")
        return proc.returncode
    finally:
        if log_fp is not None:
            log_fp.close()


# ---------------------------------------------------------------------------
# Per-mode dispatch
# ---------------------------------------------------------------------------


def _cmd_record(args: argparse.Namespace, halo_home: Path, log_path: Path | None) -> int:
    script = SCRIPTS_DIR / "record-held-out.sh"
    if not script.exists():
        print(f"[orchestrator] missing script: {script}", file=sys.stderr)
        return 2
    return _run_subprocess(
        ["bash", str(script)],
        cwd=BACKEND_DIR,
        log_path=log_path,
        dry_run=args.dry_run,
    )


# Sprint 46: derive a corpus_id from a training-corpus path. The
# convention is documented in `docs/HELD-OUT-EVAL.md` (Sprint 46
# section) and `FEATURE-SPEC-SPRINT46-PER-CORPUS-WER.md`.
_CORPUS_DIR_SELF_PREFIX = "yue-self-"


def _corpus_id_from_train_dir(train_dir: Path | None) -> str:
    """Derive a corpus_id from the `--train-corpus-dir` path.

    Convention:
      - `.../yue-self-YYYY-MM-DD/`  → "self:YYYY-MM-DD"
      - `.../common-voice-yue*/`    → pass-through basename
      - any other path              → "self:<basename>" (fallback)
      - empty/None                  → "" (orchestrator will skip
                                            the --corpus-id flag)

    Returns the corpus_id string (possibly empty). Caller decides
    whether to forward it as `--corpus-id` to the eval subprocess.
    """
    if train_dir is None:
        return ""
    name = Path(train_dir).name
    if not name:
        return ""
    if name.startswith(_CORPUS_DIR_SELF_PREFIX):
        date_part = name[len(_CORPUS_DIR_SELF_PREFIX):]
        return f"self:{date_part}"
    if name.startswith("common-voice-yue"):
        return name
    # Fallback: tag as self with the basename. Avoids the corpus
    # silently being bucketed as "unattributed".
    return f"self:{name}"


def _cmd_eval(args: argparse.Namespace, halo_home: Path, log_path: Path | None) -> int:
    script = SCRIPTS_DIR / "run_held_out_eval.py"
    if not script.exists():
        print(f"[orchestrator] missing script: {script}", file=sys.stderr)
        return 2
    cmd = [
        "python",
        str(script),
        "--threshold",
        str(args.threshold),
    ]
    # Sprint 46: auto-derive --corpus-id from --train-corpus-dir
    # (the orchestrator always knows which corpus it ran against).
    corpus_id = _corpus_id_from_train_dir(args.train_corpus_dir)
    if corpus_id:
        cmd += ["--corpus-id", corpus_id]
    return _run_subprocess(
        cmd,
        cwd=BACKEND_DIR,
        log_path=log_path,
        dry_run=args.dry_run,
    )


def _cmd_finetune(args: argparse.Namespace, halo_home: Path, log_path: Path | None) -> int:
    script = SCRIPTS_DIR / "finetune_whisper_yue.py"
    if not script.exists():
        print(f"[orchestrator] missing script: {script}", file=sys.stderr)
        return 2
    cmd = [
        "python",
        str(script),
        "--train_audio_dir",
        str(args.train_corpus_dir),
        "--output_dir",
        str(args.output_model_dir),
        "--num_train_epochs",
        "1",  # 1 epoch is enough for ~30min corpus; user can bump later
    ]
    # Sprint 45: --base-model-path is now an explicit flag with the
    # Common Voice yue baseline as default. Empty string skips the
    # flag entirely (lets finetune_whisper_yue.py fall back to HF Hub).
    base_str = (args.base_model_path or "").strip()
    if base_str:
        cmd += ["--base_model_path", base_str]
    return _run_subprocess(
        cmd,
        cwd=BACKEND_DIR,
        log_path=log_path,
        dry_run=args.dry_run,
    )


# ---------------------------------------------------------------------------
# Diff report (Sprint 40 — closes M9-E criterion 6 visually)
# ---------------------------------------------------------------------------


def _latest_two_trends(results_dir: Path) -> tuple[dict | None, dict | None]:
    """Read the 2 most recent trend JSONs (newest + previous).

    Returns (latest, previous) — either may be None if not enough
    history exists.
    """
    if not results_dir.is_dir():
        return None, None
    json_paths = sorted(
        results_dir.glob("*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not json_paths:
        return None, None
    try:
        latest = json.loads(json_paths[0].read_text(encoding="utf-8"))
        previous = (
            json.loads(json_paths[1].read_text(encoding="utf-8"))
            if len(json_paths) >= 2
            else None
        )
    except (json.JSONDecodeError, OSError):
        return None, None
    return latest, previous


def _summary_wer(summary: dict) -> float | None:
    """Extract a single WER% from an EvalRunSummary JSON.

    Averages across all results in the summary (current CLI writes
    1, but the dataclass supports N).
    """
    results = summary.get("results", [])
    if not results:
        return None
    return round(
        sum(r.get("wer", 0.0) for r in results) / len(results) * 100,
        2,
    )


def _summary_backend(summary: dict) -> str:
    """Extract the asr_backend name from the first result."""
    results = summary.get("results", [])
    if not results:
        return ""
    return results[0].get("asr_backend", "")


def _print_diff_report(results_dir: Path) -> int:
    """Print a 3-line before/after diff. Returns 0 if improvement found,
    1 otherwise (informational — caller doesn't gate on this)."""
    latest, previous = _latest_two_trends(results_dir)
    if latest is None:
        print("[orchestrator] no eval runs in trend dir yet.")
        return 0

    latest_wer = _summary_wer(latest)
    latest_backend = _summary_backend(latest)
    print()
    print("=" * 60)
    print("Held-out eval — diff report")
    print("=" * 60)
    print(f"Latest run:  WER = {latest_wer}%  (backend: {latest_backend})")
    if previous is not None:
        prev_wer = _summary_wer(previous)
        prev_backend = _summary_backend(previous)
        print(f"Previous:    WER = {prev_wer}%  (backend: {prev_backend})")
        if latest_wer is not None and prev_wer is not None:
            delta_pp = round(prev_wer - latest_wer, 2)
            delta_pct = (
                round((prev_wer - latest_wer) / prev_wer * 100, 1)
                if prev_wer > 0
                else 0.0
            )
            backend_changed = prev_backend != latest_backend
            print()
            if backend_changed and delta_pp > 0:
                print(f"Improvement: −{delta_pp}pp WER (−{delta_pct}%)")
                if latest_wer < 10.0:
                    print("✓ M9-E Layer 2 acceptance criterion 6 MET (WER < 10%)")
                else:
                    print("  (improvement observed; criterion 6 still requires WER < 10%)")
            elif delta_pp > 0:
                print(f"Improvement: −{delta_pp}pp (same backend; expected to fluctuate)")
            elif delta_pp < 0:
                print(f"Regression: +{abs(delta_pp)}pp (model got worse — investigate)")
            else:
                print("No change.")
    else:
        print("(no previous run to compare against)")
    print("=" * 60)
    return 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    halo_home = _resolve_halo_home(args)
    results_dir = halo_home / "tests" / "voice" / "held_out_results"

    # Per-run log file (in $HALO_HOME/logs/).
    log_path: Path | None = None
    if args.log_file is not None:
        log_path = args.log_file
    else:
        logs_dir = halo_home / "logs"
        log_path = logs_dir / f"eval-{int(time.time())}{LOG_FILE_SUFFIX}"

    if args.mode == "record":
        rc = _cmd_record(args, halo_home, log_path)
        return rc
    elif args.mode == "eval":
        rc = _cmd_eval(args, halo_home, log_path)
        return rc
    elif args.mode == "finetune":
        rc = _cmd_finetune(args, halo_home, log_path)
        return rc
    elif args.mode == "full":
        print("[orchestrator] === full mode: baseline → finetune → after → diff ===")
        # Step 1: baseline eval (current backend).
        print("[orchestrator] step 1/3: baseline eval")
        baseline_rc = _cmd_eval(args, halo_home, log_path)
        if baseline_rc == 2:
            print(
                "[orchestrator] baseline eval failed: no held-out WAV found. "
                "Run with --mode record first.",
                file=sys.stderr,
            )
            return 2
        if baseline_rc not in (0, 1):
            print(f"[orchestrator] baseline eval crashed (rc={baseline_rc})", file=sys.stderr)
            return 3

        # Step 2: fine-tune.
        print("[orchestrator] step 2/3: fine-tune")
        ft_rc = _cmd_finetune(args, halo_home, log_path)
        if ft_rc != 0:
            print(f"[orchestrator] fine-tune failed (rc={ft_rc})", file=sys.stderr)
            return 3

        if args.skip_finetune_eval:
            print("[orchestrator] step 3/3: skipped (--skip-finetune-eval)")
            return 0

        # Step 3: after eval (whisper_hf + new model_path).
        print("[orchestrator] step 3/3: after eval (whisper_hf + new checkpoint)")
        after_rc = _cmd_eval(args, halo_home, log_path)
        if after_rc not in (0, 1):
            print(f"[orchestrator] after eval crashed (rc={after_rc})", file=sys.stderr)
            return 3

        # Diff report.
        _print_diff_report(results_dir)
        return after_rc  # 0 = PASS, 1 = FAIL

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
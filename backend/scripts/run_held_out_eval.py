"""Sprint 38 — held-out Cantonese eval CLI runner.

Runs real `asr_factory.create_asr(config).transcribe(...)` against
the user's held-out WAV (recorded by `scripts/record-held-out.sh`),
computes WER, prints pass/fail, and writes a trend JSON.

Usage:
    cd backend && uv run python scripts/run_held_out_eval.py
    uv run python scripts/run_held_out_eval.py --wav /path/to/held.wav --txt /path/to/held.txt
    uv run python scripts/run_held_out_eval.py --threshold 0.10
    uv run python scripts/run_held_out_eval.py --backend whisper_hf
    uv run python scripts/run_held_out_eval.py --dry-run   # skip inference

Exit codes:
    0 — pass (WER < threshold)
    1 — fail (WER >= threshold)
    2 — no held-out WAV found
    3 — backend load failed (model missing, dep missing, etc.)
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from pathlib import Path

# Path bootstrap — `python scripts/run_held_out_eval.py` needs to find `app.*`
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import get_config, load_config  # noqa: E402
from app.voice.asr import asr_factory  # noqa: E402
from app.voice.held_out_eval import (  # noqa: E402
    EvalResult,
    EvalRunSummary,
    held_out_results_dir,
    heldout_paths,
    load_wer_threshold,
    wav_to_pcm_bytes,
    word_error_rate,
)

logger = logging.getLogger("held_out_eval")


def _resolve_paths(args) -> tuple[Path, Path] | None:
    """Return (wav, txt) or None if not found.

    CLI `--wav` / `--txt` override the default latest-holdout
    lookup (which honours HALO_HOME per the testable path
    helper).
    """
    if args.wav is not None:
        wav = Path(args.wav).expanduser().resolve()
        txt = (
            Path(args.txt).expanduser().resolve()
            if args.txt
            else wav.with_suffix(".txt")
        )
        if not wav.is_file():
            print(f"error: WAV not found: {wav}", file=sys.stderr)
            return None
        if not txt.is_file():
            print(f"error: TXT not found: {txt}", file=sys.stderr)
            return None
        return wav, txt

    wav, txt = heldout_paths()
    if wav is None or txt is None:
        print(
            "error: No held-out WAV found in ~/.gundam-halo/recordings/.\n"
            "Run scripts/record-held-out.sh first (5 min).",
            file=sys.stderr,
        )
        return None
    return wav, txt


def _resolve_asr_backend(args):
    """Build the ASR backend instance via asr_factory.

    Honours `--backend` CLI override (default: from config).
    The config's `voice.asr.model_size` / `model_path` flow
    through transparently — no script changes needed when
    the user swaps to a personalised `whisper_hf` checkpoint.
    """
    cfg = load_config()
    if args.backend:
        # Mutate the cfg's `voice.asr.backend` for this run only
        # (load_config already cached the singleton; we mutate
        # the in-memory object directly).
        cfg.voice.asr.backend = args.backend

    try:
        asr = asr_factory.create_asr(cfg.voice.asr)
    except Exception as e:
        print(f"error: Failed to construct ASR backend: {e}", file=sys.stderr)
        return None
    return asr


async def _run_inference(asr, pcm: bytes, sample_rate: int) -> tuple[str, float]:
    """Call warmup + transcribe; return (hypothesis, duration_s)."""
    t0 = time.time()
    await asr.warmup()
    warmup_s = time.time() - t0

    t1 = time.time()
    hypothesis = await asr.transcribe(pcm, sample_rate=sample_rate)
    inference_s = time.time() - t1
    return hypothesis, warmup_s + inference_s


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.split("\n\n")[0] if __doc__ else "Held-out eval",
    )
    parser.add_argument(
        "--wav",
        type=Path,
        default=None,
        help="Override WAV path (default: latest held-out-<date>.wav)",
    )
    parser.add_argument(
        "--txt",
        type=Path,
        default=None,
        help="Override transcript path (default: <wav>.txt)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=None,
        help=(
            "Override WER threshold (default: ~/.gundam-halo/test-config.toml "
            "[held_out_eval].wer_threshold, fallback 0.15)"
        ),
    )
    parser.add_argument(
        "--backend",
        type=str,
        default=None,
        choices=["whisper_local", "whisper_hf", "yuesub"],
        help="Override ASR backend (default: from config)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip warmup + inference; just report file paths + threshold",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help=(
            "Output JSON path (default: tests/voice/held_out_results/<ts>.json)"
        ),
    )
    parser.add_argument(
        "--corpus-id",
        type=str,
        default="",
        help=(
            "Sprint 46: optional tag identifying which corpus the eval WAV "
            "came from. Format convention: 'self:<date>' (self-record), "
            "'common-voice-yue:<version>' (Common Voice), "
            "'synthetic:<name>' (test fixtures). Empty string = "
            "unattributed (legacy runs)."
        ),
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Verbose logging"
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    )

    # 1. Resolve WAV + TXT.
    paths = _resolve_paths(args)
    if paths is None:
        return 2
    wav, txt = paths

    # 2. Read reference transcript + compute threshold.
    reference = txt.read_text(encoding="utf-8").strip()
    threshold = (
        args.threshold
        if args.threshold is not None
        else load_wer_threshold()
    )

    # 3. Dry-run path: skip inference, just report the would-be eval.
    if args.dry_run:
        result = EvalResult.now(
            wav_path=str(wav),
            transcript_path=str(txt),
            reference=reference,
            hypothesis="<dry-run>",
            wer=0.0,
            threshold=threshold,
            passed=False,
            asr_backend=args.backend or "(from config)",
            notes="--dry-run; no inference performed",
            # Sprint 46: forward corpus-id even in dry-run.
            corpus_id=args.corpus_id,
        )
        print(f"DRY RUN — no inference performed")
        print(f"  WAV:        {wav}")
        print(f"  Transcript: {txt} ({len(reference.split())} words)")
        print(f"  Threshold:  {threshold:.1%}")
        print(f"  Backend:    {result.asr_backend}")
        return 0

    # 4. Construct ASR backend + read WAV.
    asr = _resolve_asr_backend(args)
    if asr is None:
        return 3

    try:
        pcm, sample_rate = wav_to_pcm_bytes(wav)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 3

    # 5. Run inference.
    try:
        hypothesis, duration_s = asyncio.run(_run_inference(asr, pcm, sample_rate))
    except Exception as e:
        print(f"error: Inference failed: {e}", file=sys.stderr)
        return 3

    # 6. Compute WER + pass/fail.
    wer = word_error_rate(reference, hypothesis)
    passed = wer < threshold

    result = EvalResult.now(
        wav_path=str(wav),
        transcript_path=str(txt),
        reference=reference,
        hypothesis=hypothesis,
        wer=wer,
        threshold=threshold,
        passed=passed,
        duration_s=duration_s,
        asr_backend=args.backend or "(from config)",
        # Sprint 46: forward the corpus tag (empty = unattributed).
        corpus_id=args.corpus_id,
    )

    # 7. Print.
    print("=" * 60)
    print("Held-out Cantonese Eval — Sprint 38")
    print("=" * 60)
    print(f"WAV:        {result.wav_path}")
    print(f"Transcript: {result.transcript_path}")
    print(f"Backend:    {result.asr_backend}")
    print(f"Threshold:  {result.threshold:.1%}")
    print(f"Duration:   {result.duration_s:.1f}s")
    print("-" * 60)
    print(f"Reference : {result.reference}")
    print(f"Hypothesis: {result.hypothesis}")
    print("-" * 60)
    print(f"WER: {result.wer:.1%} ({'PASS' if result.passed else 'FAIL'})")
    print("=" * 60)

    # 8. Write trend JSON.
    out_path = args.out
    if out_path is None:
        results_dir = held_out_results_dir()
        results_dir.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        out_path = results_dir / f"{ts}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    summary = EvalRunSummary.now([result])
    out_path.write_text(summary.to_json(), encoding="utf-8")
    print(f"\nWrote: {out_path}")

    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

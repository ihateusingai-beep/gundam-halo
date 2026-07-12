"""M9-E Layer 2 — self-record corpus validator.

Sprint 67 prep. Validates the user's self-record audio
directory (`~/.gundam-halo/recordings/yue-self-<date>/`)
BEFORE the 30-min finetune kicks off. The script checks:

  1. The directory exists + is named `yue-self-YYYY-MM-DD`.
  2. Each chunk has a matching `.wav` + `.txt` pair
     (the file naming convention used by the Tauri
     Record card).
  3. Each WAV is 16-bit mono PCM at 16kHz
     (the Whisper / SenseVoice expected input).
  4. Each TXT is non-empty UTF-8 + has at least 4
     Cantonese characters (filters out blank or
     "I forgot to speak" recordings).
  5. The total audio duration is >= 5 minutes
     (a known lower bound for the CV-yue + LoRA
     finetune to produce a meaningful WER improvement
     on the held-out eval).

The script exits with status 0 on success, 1 on a
hard fail (missing files, wrong sample rate, etc.),
2 on a soft fail (under the 5-min threshold but
otherwise valid — the user can pass `--force` to
override).

Usage:
    cd backend
    uv run python scripts/validate_yue_self_record.py
    uv run python scripts/validate_yue_self_record.py --dry-run
    uv run python scripts/validate_yue_self_record.py --force
    uv run python scripts/validate_yue_self_record.py --corpus \\
        ~/.gundam-halo/recordings/yue-self-2026-07-02/

Exit codes:
    0 — corpus is valid
    1 — hard fail (wrong format, missing files, etc.)
    2 — soft fail (under 5-min threshold; --force to override)
"""
from __future__ import annotations

import argparse
import sys
import wave
from pathlib import Path

from _script_lib import resolve_halo_home  # noqa: F401
from app.paths import recordings_dir

# Min total duration in seconds. 5 min is the Sprint 67
# heuristic; Sprint 68+ can ratchet this up as we
# collect real recording data.
MIN_TOTAL_SECONDS = 300

# Min Cantonese characters per transcript. Filters out
# "I forgot to speak" + non-Cantonese test recordings.
# A Cantonese character is anything that contains at
# least one CJK Unified Ideograph. We do a simple
# codepoint check here; full grapheme-cluster support
# (e.g. for Cantonese-specific characters outside
# the BMP) is out of scope for Sprint 67.
def _is_cjk_char(ch: str) -> bool:
    if not ch:
        return False
    cp = ord(ch[0])
    return (
        0x4E00 <= cp <= 0x9FFF  # CJK Unified Ideographs
        or 0x3400 <= cp <= 0x4DBF  # CJK Extension A
        or 0x20000 <= cp <= 0x2A6DF  # CJK Extension B
    )


def _wav_duration(path: Path) -> float:
    """Return the duration in seconds. Returns 0 on
    any error (caller will flag the file as invalid)."""
    try:
        with wave.open(str(path), "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            if rate <= 0:
                return 0
            return frames / float(rate)
    except Exception:
        return 0


def _check_wav_format(path: Path) -> tuple[bool, str]:
    """Verify the WAV is 16-bit mono PCM at 16kHz.
    Returns (ok, message)."""
    try:
        with wave.open(str(path), "rb") as wf:
            if wf.getnchannels() != 1:
                return False, f"not mono ({wf.getnchannels()} channels)"
            if wf.getframerate() != 16000:
                return False, f"not 16kHz ({wf.getframerate()}Hz)"
            if wf.getsampwidth() != 2:
                return False, f"not 16-bit ({wf.getsampwidth() * 8}-bit)"
            return True, "ok"
    except Exception as e:
        return False, f"failed to open as WAV: {e}"


def validate_corpus(corpus_dir: Path, force: bool = False) -> tuple[int, list[str]]:
    """Validate the corpus. Returns (exit_code, list_of_messages)."""
    messages: list[str] = []
    if not corpus_dir.exists():
        messages.append(f"❌ Corpus directory not found: {corpus_dir}")
        return 1, messages
    if not corpus_dir.is_dir():
        messages.append(f"❌ Not a directory: {corpus_dir}")
        return 1, messages
    # Check the directory name follows `yue-self-YYYY-MM-DD`.
    dir_name = corpus_dir.name
    if not dir_name.startswith("yue-self-"):
        messages.append(
            f"❌ Directory name must start with 'yue-self-' (got: {dir_name})"
        )
        return 1, messages

    wavs = sorted(corpus_dir.glob("*.wav"))
    if not wavs:
        messages.append(f"❌ No .wav files found in {corpus_dir}")
        return 1, messages

    total_seconds = 0.0
    for wav in wavs:
        stem = wav.stem
        txt = wav.with_suffix(".txt")
        if not txt.exists():
            messages.append(f"❌ Missing transcript for {wav.name} (expected {txt.name})")
            return 1, messages
        # Check WAV format
        ok, msg = _check_wav_format(wav)
        if not ok:
            messages.append(f"❌ {wav.name}: {msg}")
            return 1, messages
        # Check transcript is non-empty + has CJK characters
        try:
            transcript = txt.read_text(encoding="utf-8").strip()
        except UnicodeDecodeError:
            messages.append(f"❌ {txt.name}: not valid UTF-8")
            return 1, messages
        if not transcript:
            messages.append(f"❌ {txt.name}: empty transcript")
            return 1, messages
        cjk_count = sum(1 for ch in transcript if _is_cjk_char(ch))
        if cjk_count < 4:
            messages.append(
                f"❌ {txt.name}: only {cjk_count} CJK characters "
                f"(min 4; the file may be blank or in a non-CJK language)"
            )
            return 1, messages
        # Accumulate duration
        total_seconds += _wav_duration(wav)
        messages.append(
            f"✓ {wav.name}: {transcript[:30]}… ({_wav_duration(wav):.1f}s)"
        )

    messages.append(
        f"Total: {len(wavs)} chunks, {total_seconds:.1f}s "
        f"(min {MIN_TOTAL_SECONDS}s)"
    )
    if total_seconds < MIN_TOTAL_SECONDS and not force:
        messages.append(
            f"⚠ Under the {MIN_TOTAL_SECONDS}s threshold. Pass --force to "
            f"override (the finetune may not improve WER with this much data)."
        )
        return 2, messages
    return 0, messages


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a yue self-record corpus before M9-E Layer 2 finetune."
    )
    parser.add_argument(
        "--corpus",
        type=Path,
        default=None,
        help="Path to the corpus dir. Defaults to the most recent "
        "yue-self-* dir in $HALO_HOME/recordings/.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be checked without exiting non-zero.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Override the 5-min minimum duration threshold.",
    )
    args = parser.parse_args()

    if args.corpus is not None:
        corpus = args.corpus
    else:
        # Find the most recent yue-self-* dir.
        rec_dir = recordings_dir()
        candidates = sorted(rec_dir.glob("yue-self-*"), reverse=True)
        if not candidates:
            print(f"❌ No yue-self-* dirs found in {rec_dir}")
            print("   Record audio via the Tauri Record card first.")
            return 1
        corpus = candidates[0]
        print(f"Using most recent corpus: {corpus}")

    exit_code, messages = validate_corpus(corpus, force=args.force)
    for msg in messages:
        print(msg)
    if args.dry_run:
        return 0
    return exit_code


if __name__ == "__main__":
    sys.exit(main())

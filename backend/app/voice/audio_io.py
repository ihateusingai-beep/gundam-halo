"""Canonical audio I/O helpers for the voice pipeline.

Before this module existed (Sprint 56 R2), both
`scripts/gen_cantonese_corpus.py` and
`scripts/prepare_fsicoli_cv_yue.py` shipped near-identical
`ffmpeg → 16 kHz mono s16le WAV` helpers. Sprint 55 discovered
that the pre-Sprint-55 helper (`wave.open()` for duration
probing) returned 0.001s for every clip — it didn't account
for ffmpeg's LIST metadata chunk insertion between the `fmt ` and
`data` sub-chunks.

This module owns the correct contract: one function
(`ffmpeg_to_wav`), one duration probe (`wav_duration_seconds`),
one SAMPLE_RATE constant, one ffmpeg arg template.

`soundfile` (libsndfile C library under the hood) reads the
actual WAV header so it works for BOTH the standard layout and
ffmpeg's LIST-extended layout — fixes the 0.001s bug class
automatically.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Final

import soundfile as sf

# 16 kHz mono int16 PCM — matches the Whisper / openai-whisper
# contract consumed by `app.voice.asr.whisper_local` and
# `app.voice.asr.whisper_hf`. Also matches the ASR factory sample-rate
# invariant `SAMPLE_RATE = 16_000` referenced by
# `app.voice.held_out_eval`.
SAMPLE_RATE: Final[int] = 16_000


# ffmpeg arg template — uses {INPUT} / {OUTPUT} placeholders so the
# actual paths get substituted at call time. Keeping them as
# placeholders (not f-strings) lets us log the resolved cmd for
# debugging without re-substituting.
_FFMPEG_CMD_TEMPLATE: Final[list[str]] = [
    "-y",                  # overwrite output if exists
    "-nostdin",            # never read from stdin (CI / no-tty safety)
    "-loglevel", "error",  # only emit errors to stderr — keep stdout clean
    "-i", "{INPUT}",
    "-ar", str(SAMPLE_RATE),
    "-ac", "1",            # mono
    "-f", "wav",
    "-acodec", "pcm_s16le",  # 16-bit signed PCM (Whisper expected format)
    "{OUTPUT}",
]


def ffmpeg_to_wav(input_path: Path, output_path: Path) -> tuple[float, int]:
    """Convert any audio file (mp3, m4a, ogg, …) to 16 kHz mono
    s16le WAV via ffmpeg.

    Returns (duration_seconds, sample_rate) probed from the
    resulting WAV header via soundfile (handles both standard
    WAVs + ffmpeg's LIST-chunk-extended WAVs).

    Raises:
        RuntimeError: ffmpeg not on PATH, or ffmpeg exited non-zero.
        FileNotFoundError: input file missing.
    """
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError(
            "ffmpeg not on PATH. Install with `brew install ffmpeg` "
            "or `apt install ffmpeg`."
        )
    if not input_path.exists():
        raise FileNotFoundError(f"input audio not found: {input_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [ffmpeg, *_substitute(_FFMPEG_CMD_TEMPLATE, input_path, output_path)]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(
            f"ffmpeg failed for {input_path.name}: "
            f"{res.stderr[:200] if res.stderr else 'no stderr'}"
        )
    return wav_duration_seconds(output_path), SAMPLE_RATE


def wav_duration_seconds(wav_path: Path) -> float:
    """Probe a WAV file's duration via soundfile.

    soundfile (libsndfile C library under the hood) reads the
    actual WAV header — works for BOTH the standard layout
    (data chunk at byte 44) AND ffmpeg-emitted WAVs (LIST
    metadata chunk inserts at variable offset).

    Returns duration in seconds (float).

    Note: this is the canonical probe — if a future caller
    needs to re-probe an existing WAV without re-running
    ffmpeg, use this rather than reading the `data` chunk
    size manually (which has the LIST-chunk bug class).
    """
    info = sf.info(str(wav_path))
    return float(info.frames) / float(info.samplerate)


def _substitute(
    template: list[str],
    input_path: Path,
    output_path: Path,
) -> list[str]:
    """Replace {INPUT} / {OUTPUT} placeholders in the ffmpeg
    command template with the actual paths.
    """
    in_s, out_s = str(input_path), str(output_path)
    return [s.replace("{INPUT}", in_s).replace("{OUTPUT}", out_s) for s in template]


__all__ = ["SAMPLE_RATE", "ffmpeg_to_wav", "wav_duration_seconds"]

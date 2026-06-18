"""Sprint 33 (Track 31-B) — self-record manifest schema.

The Layer 2 v2 personalised fine-tune (FEATURE-SPEC-SPRINT26.md
§4.1) is fed by a JSONL manifest the Tauri recording pipeline
writes during the Record card flow:

    ~/.gundam-halo/recordings/yue-self-<date>/
        chunk-001.wav    # 30s @ 16kHz mono
        chunk-002.wav
        ...
        manifest.jsonl   # one JSON object per line

Each `manifest.jsonl` line is exactly:

    {
      "audio_path":   "/abs/path/chunk-001.wav",
      "text":         "今日天氣好好",   # WhisperHFASR transcription
      "duration_s":   30.0,
      "sample_rate":  16000
    }

The `prepare_common_voice_yue` adapter treats the self-record
manifest the same way it treats the Common Voice yue manifest
— one extra `data_source = "self_record"` field on the
materialised parquet rows so the trainer can see the corpus
origin. The format is **identical** between the two sources
because the trainer consumes a single unified schema.

Schema invariants (enforced by `validate_record`):

  - `audio_path` is a non-empty absolute string ending in `.wav`.
  - `text` is a non-empty stripped string (no whitespace-only).
  - `duration_s` is a positive float (typical ~30s, range 1-120).
  - `sample_rate` is a positive int (the v0.1.4 contract is 16000).

Lines that fail validation are **skipped** (logged warning) by
the streaming reader — the Tauri pipeline may append mid-session
and a partial chunk with empty text should not crash the trainer.

This module is intentionally framework-free (no `datasets`, no
`pyarrow`, no `transformers`) so it can be unit-tested in the
default venv and imported by both the recording pipeline
(recording.rs → Python via subprocess) and the trainer
(`scripts/finetune_whisper_yue.py --train_audio_dir`).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterator

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schema constants — surfaced here so callers can introspect the
# canonical names without hard-coding strings.
# ---------------------------------------------------------------------------

AUDIO_PATH_KEY = "audio_path"
TEXT_KEY = "text"
DURATION_S_KEY = "duration_s"
SAMPLE_RATE_KEY = "sample_rate"

# v0.1.4 contract: every chunk is 16kHz mono s16le WAV.
EXPECTED_SAMPLE_RATE = 16000

# Soft duration range — chunks outside this range are flagged in
# the summary but not rejected. The Tauri pipeline targets 30s
# but the user may stop early (≥10s) or extend (≤60s).
MIN_DURATION_S = 1.0
MAX_DURATION_S = 120.0

MANIFEST_FILENAME = "manifest.jsonl"


# ---------------------------------------------------------------------------
# Data class — the in-memory shape of one manifest line.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SelfRecordSample:
    """One chunk of user-recorded Cantonese + its WhisperHFASR transcription.

    Frozen so it can be safely passed between threads (the Tauri
    recording pipeline writes from the recording thread and reads
    from the transcription thread; both share the same dataclass
    instance after the manifest flush).
    """

    audio_path: str
    text: str
    duration_s: float
    sample_rate: int

    def to_dict(self) -> dict:
        """Serialise back to the JSONL dict shape (round-trip-safe)."""
        return asdict(self)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class ManifestFormatError(ValueError):
    """Raised by `validate_record` when a single record's shape is wrong.

    The streaming reader catches this and logs a warning instead
    of crashing — partial / mid-session appends can produce
    short-lived invalid rows that the trainer should skip, not
    abort on.
    """


def validate_record(record: dict) -> SelfRecordSample:
    """Validate one JSONL line → return a typed `SelfRecordSample`.

    Raises `ManifestFormatError` on any schema violation. The
    caller decides whether to skip (streaming reader) or
    propagate (a strict unit test, for instance).
    """
    if not isinstance(record, dict):
        raise ManifestFormatError(
            f"manifest line must be a JSON object, got {type(record).__name__}"
        )

    audio_path = record.get(AUDIO_PATH_KEY)
    if not isinstance(audio_path, str) or not audio_path.strip():
        raise ManifestFormatError(
            f"{AUDIO_PATH_KEY!r} must be a non-empty string; got {audio_path!r}"
        )
    if not audio_path.endswith(".wav"):
        raise ManifestFormatError(
            f"{AUDIO_PATH_KEY!r} must end in '.wav'; got {audio_path!r}"
        )

    text = record.get(TEXT_KEY)
    if not isinstance(text, str):
        raise ManifestFormatError(
            f"{TEXT_KEY!r} must be a string; got {type(text).__name__}"
        )
    stripped_text = text.strip()
    if not stripped_text:
        raise ManifestFormatError(
            f"{TEXT_KEY!r} must be non-empty after strip(); got {text!r}"
        )

    duration_s = record.get(DURATION_S_KEY)
    if not isinstance(duration_s, (int, float)) or isinstance(duration_s, bool):
        raise ManifestFormatError(
            f"{DURATION_S_KEY!r} must be a number; got {duration_s!r}"
        )
    if duration_s < MIN_DURATION_S or duration_s > MAX_DURATION_S:
        raise ManifestFormatError(
            f"{DURATION_S_KEY!r}={duration_s} out of range "
            f"[{MIN_DURATION_S}, {MAX_DURATION_S}]"
        )

    sample_rate = record.get(SAMPLE_RATE_KEY)
    if not isinstance(sample_rate, int) or isinstance(sample_rate, bool):
        raise ManifestFormatError(
            f"{SAMPLE_RATE_KEY!r} must be an int; got {sample_rate!r}"
        )
    if sample_rate <= 0:
        raise ManifestFormatError(
            f"{SAMPLE_RATE_KEY!r} must be positive; got {sample_rate}"
        )

    return SelfRecordSample(
        audio_path=audio_path.strip(),
        text=stripped_text,
        duration_s=float(duration_s),
        sample_rate=sample_rate,
    )


# ---------------------------------------------------------------------------
# Streaming reader — line-by-line, validates each row, skips on error.
# ---------------------------------------------------------------------------


def iter_manifest(manifest_path: Path) -> Iterator[SelfRecordSample]:
    """Stream a `manifest.jsonl` line-by-line, yielding validated samples.

    Lines that fail `validate_record` are logged at WARNING and
    skipped — they do not abort the stream. Empty lines are
    silently skipped (a JSONL-friendly no-op).

    The function is a generator; callers should iterate once
    and materialise if they need a list (e.g. for tests).
    """
    manifest_path = Path(manifest_path)
    if not manifest_path.is_file():
        raise FileNotFoundError(
            f"manifest not found: {manifest_path}. "
            "The Tauri recording pipeline writes this file as it "
            "captures chunks; if you ran the recording pipeline "
            "and the manifest is still missing, check the "
            "~/.gundam-halo/recordings/yue-self-<date>/ directory."
        )

    with manifest_path.open("r", encoding="utf-8") as f:
        for line_no, raw_line in enumerate(f, start=1):
            stripped = raw_line.strip()
            if not stripped:
                continue
            try:
                record = json.loads(stripped)
            except json.JSONDecodeError as e:
                logger.warning(
                    f"manifest {manifest_path}:{line_no} invalid JSON, "
                    f"skipping ({e})"
                )
                continue
            try:
                yield validate_record(record)
            except ManifestFormatError as e:
                logger.warning(
                    f"manifest {manifest_path}:{line_no} schema violation, "
                    f"skipping ({e})"
                )
                continue


# ---------------------------------------------------------------------------
# Summary helper — for the "Record" card's completion summary.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ManifestSummary:
    """Aggregate stats for the "Record" card's completion summary."""

    total_chunks: int
    total_duration_s: float
    sample_rate: int
    rejected_lines: int

    @property
    def total_minutes(self) -> float:
        return self.total_duration_s / 60.0


def summarise(manifest_path: Path) -> ManifestSummary:
    """Read the whole manifest and return aggregate stats.

    Cheaper than the production aggregator (`prepare_common_voice_yue`)
    for the dashboard summary card — no I/O beyond reading the
    JSONL file, no parquet writes. The Tauri recording card
    calls this after `stop_record` finishes flushing chunks.
    """
    total_chunks = 0
    total_duration = 0.0
    sample_rate: int | None = None
    rejected = 0

    manifest_path = Path(manifest_path)
    if not manifest_path.is_file():
        # Empty / new manifest — the dashboard renders "0 chunks,
        # 0 minutes" without crashing. The recording pipeline
        # hasn't written anything yet.
        return ManifestSummary(
            total_chunks=0,
            total_duration_s=0.0,
            sample_rate=EXPECTED_SAMPLE_RATE,
            rejected_lines=0,
        )

    with manifest_path.open("r", encoding="utf-8") as f:
        for raw_line in f:
            stripped = raw_line.strip()
            if not stripped:
                continue
            try:
                record = json.loads(stripped)
                sample = validate_record(record)
            except (json.JSONDecodeError, ManifestFormatError):
                rejected += 1
                continue
            total_chunks += 1
            total_duration += sample.duration_s
            if sample_rate is None:
                sample_rate = sample.sample_rate
            elif sample_rate != sample.sample_rate:
                # Heterogeneous sample rates are a schema violation;
                # count the line as rejected but keep going.
                rejected += 1
                total_chunks -= 1
                total_duration -= sample.duration_s

    return ManifestSummary(
        total_chunks=total_chunks,
        total_duration_s=total_duration,
        sample_rate=sample_rate if sample_rate is not None else EXPECTED_SAMPLE_RATE,
        rejected_lines=rejected,
    )


__all__ = [
    "AUDIO_PATH_KEY",
    "TEXT_KEY",
    "DURATION_S_KEY",
    "SAMPLE_RATE_KEY",
    "EXPECTED_SAMPLE_RATE",
    "MIN_DURATION_S",
    "MAX_DURATION_S",
    "MANIFEST_FILENAME",
    "SelfRecordSample",
    "ManifestFormatError",
    "ManifestSummary",
    "validate_record",
    "iter_manifest",
    "summarise",
]

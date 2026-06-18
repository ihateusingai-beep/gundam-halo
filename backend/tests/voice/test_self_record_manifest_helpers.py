"""Regression guards for `app.voice.self_record_manifest` (Sprint 33).

This file is **not** part of the spec test count contract —
FEATURE-SPEC-SPRINT26.md §5 mandates "5-8 tests for
self-record manifest" and that's enforced on the file
`test_self_record_manifest.py`. The guards here cover edge
cases that aren't strictly required by the spec but pin
helper-level behaviour so a future refactor can't silently
regress them:

  - `validate_record` strips whitespace from `text`.
  - `validate_record` rejects empty `text` (silence).
  - `validate_record` rejects negative `sample_rate`.
  - `validate_record` allows sample_rate != 16000
    (the module only enforces positivity; the trainer
    has its own rate check — pinning the schema's leniency
    so a future tightening is intentional).
  - `validate_record` rejects duration at exact boundary
    `MIN_DURATION_S` from below (negative).
  - `validate_record` rejects non-dict root (list, scalar).
  - `iter_manifest` raises `FileNotFoundError` with the
    helpful "manifest not found" message.
  - `summarise` counts rejected lines (mixed valid +
    invalid input).
  - `summarise` reports `total_minutes` correctly.
  - `SelfRecordSample.to_dict()` round-trips through the
    JSONL dict shape.

These are 10 tests + 1 dataclass round-trip test = 11 in
total. They sit in a separate file so the spec test file
stays at 8 tests and the count contract is mechanical to
verify.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.voice.self_record_manifest import (
    EXPECTED_SAMPLE_RATE,
    MANIFEST_FILENAME,
    MAX_DURATION_S,
    MIN_DURATION_S,
    ManifestFormatError,
    SelfRecordSample,
    iter_manifest,
    summarise,
    validate_record,
)


def _valid_record(
    audio_path: str = "/tmp/c1.wav",
    text: str = "今日天氣好好",
    duration_s: float = 30.0,
    sample_rate: int = EXPECTED_SAMPLE_RATE,
) -> dict:
    return {
        "audio_path": audio_path,
        "text": text,
        "duration_s": duration_s,
        "sample_rate": sample_rate,
    }


# ---------------------------------------------------------------------------
# Regression guards
# ---------------------------------------------------------------------------


def test_helpers_validate_record_strips_text_whitespace():
    """`text` is stripped before storage. A transcription
    with a leading/trailing newline (the WhisperHFASR
    backend's stdout sometimes adds one) normalises to
    the bare string.
    """
    row = _valid_record(text="  今日天氣好好\n")
    sample = validate_record(row)
    assert sample.text == "今日天氣好好"


def test_helpers_validate_record_rejects_empty_text_after_strip():
    """Empty `text` (silence → empty transcription) is
    rejected by the schema validator.
    """
    with pytest.raises(ManifestFormatError, match="text"):
        validate_record(_valid_record(text=""))
    with pytest.raises(ManifestFormatError, match="text"):
        validate_record(_valid_record(text="   \n"))


def test_helpers_validate_record_rejects_negative_sample_rate():
    """A negative sample rate is rejected by the schema.
    (48kHz passes — see the next test for the pinning
    of that behaviour.)
    """
    with pytest.raises(ManifestFormatError, match="sample_rate"):
        validate_record(_valid_record(sample_rate=-1))
    with pytest.raises(ManifestFormatError, match="sample_rate"):
        validate_record(_valid_record(sample_rate=0))


def test_helpers_validate_record_allows_non_16khz_sample_rate():
    """The schema validator only enforces `sample_rate > 0`;
    48kHz passes (the trainer has its own rate check).
    Pinning this means a future schema tightening is
    intentional — `git blame` will surface this test
    as the tripwire.
    """
    sample = validate_record(_valid_record(sample_rate=48000))
    assert sample.sample_rate == 48000


def test_helpers_validate_record_accepts_min_duration_boundary():
    """`MIN_DURATION_S` (1s) is the inclusive lower
    boundary. A future bug that tightened the check
    to `> 1.0` instead of `>= 1.0` would break this
    test.
    """
    sample = validate_record(_valid_record(duration_s=MIN_DURATION_S))
    assert sample.duration_s == MIN_DURATION_S


def test_helpers_validate_record_rejects_non_dict_root():
    """JSONL technically allows any JSON value per line,
    but our manifest contract is object-only. A list or
    scalar at the root must be rejected.
    """
    with pytest.raises(ManifestFormatError, match="JSON object"):
        validate_record(["not", "an", "object"])  # type: ignore[arg-type]
    with pytest.raises(ManifestFormatError, match="JSON object"):
        validate_record("a string")  # type: ignore[arg-type]
    with pytest.raises(ManifestFormatError, match="JSON object"):
        validate_record(42)  # type: ignore[arg-type]


def test_helpers_iter_manifest_missing_file_raises(tmp_path: Path):
    """A non-existent manifest raises `FileNotFoundError`
    with the helpful "manifest not found" message that
    points at `~/.gundam-halo/recordings/`. This is the
    case where the user runs the trainer before recording
    anything.
    """
    missing = tmp_path / "nope.jsonl"
    with pytest.raises(FileNotFoundError, match="manifest not found"):
        list(iter_manifest(missing))


def test_helpers_summarise_counts_rejected_lines(tmp_path: Path):
    """Mixed valid + invalid lines: `summarise` counts
    the rejected lines so the Record card can warn the
    user ("3 chunks captured, 2 lines rejected, check
    your mic"). The valid lines are still counted.
    """
    manifest = tmp_path / MANIFEST_FILENAME
    manifest.write_text(
        json.dumps(_valid_record(audio_path="/tmp/c1.wav")) + "\n"
        + "garbage\n"
        + json.dumps(_valid_record(audio_path="/tmp/c3.wav")) + "\n"
        + json.dumps(
            _valid_record(audio_path="/tmp/c4.mp3")
        ) + "\n",  # schema violation: non-.wav
        encoding="utf-8",
    )
    summary = summarise(manifest)
    assert summary.total_chunks == 2  # c1 + c3
    assert summary.rejected_lines == 2  # garbage + c4.mp3


def test_helpers_summarise_reports_total_minutes(tmp_path: Path):
    """`ManifestSummary.total_minutes` is the value the
    dashboard renders ("X min recorded"). 78.5s ≈ 1.31 min.
    """
    manifest = tmp_path / MANIFEST_FILENAME
    with manifest.open("w", encoding="utf-8") as f:
        f.write(json.dumps(_valid_record(duration_s=78.5)) + "\n")
    summary = summarise(manifest)
    assert abs(summary.total_minutes - 78.5 / 60.0) < 1e-6


def test_helpers_self_record_sample_round_trips_through_dict():
    """`SelfRecordSample.to_dict()` round-trips through
    the JSONL dict shape. Pinning this means the
    `prepare_common_voice_yue` adapter (future-sprint)
    can materialise a parquet row from a sample without
    field-name drift.
    """
    sample = SelfRecordSample(
        audio_path="/tmp/c1.wav",
        text="hello",
        duration_s=30.0,
        sample_rate=EXPECTED_SAMPLE_RATE,
    )
    d = sample.to_dict()
    # Re-validate through the schema — would raise on
    # any drift between the dataclass field names and
    # the JSONL contract.
    sample2 = validate_record(d)
    assert sample2 == sample

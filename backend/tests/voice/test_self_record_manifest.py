"""Tests for the self-record manifest JSONL format (Sprint 33 / Track 31-B).

The manifest is the artefact the Tauri app's Record card
(`frontend/src-tauri/src/recording.rs`) writes during a
30-minute Cantonese self-record session. Each line is a JSON
object describing one 30s audio chunk plus its v0.1.4
`WhisperHFASR` transcription:

    {"audio_path": "/Users/.../yue-self-2026-06-18/chunk-001.wav",
     "text": "幫我讀 gundam-halo backend 嘅 README 嘅第一行",
     "duration_s": 30.0,
     "sample_rate": 16000}

The Python `finetune_whisper_yue.py` script (Sprint 33
extension) consumes this manifest via the new
`--train_audio_dir <dir>` flag — the manifest file lives at
`<dir>/manifest.jsonl`. See
`docs/FEATURE-SPEC-SPRINT26.md` §4.1 (Track 1 — Layer 2 v2
self-record corpus) for the full UX flow.

This file is the **spec test file** per Sprint 31 §5 — it
ships exactly 8 tests that pin the JSONL contract on
`app.voice.self_record_manifest` (the framework-free helper
module shipped in this sprint). Regression guards (text
stripping, empty-text rejection, non-wav suffix, dataclass
round-trip, etc.) live in a separate file —
`test_self_record_manifest_helpers.py` — so the spec's
"5-8 tests" count is preserved here while the broader
coverage is still in the suite.

What we test in this file (the 8 spec tests):
  1. validate_record accepts a valid chunk → typed sample.
  2. validate_record rejects a chunk missing sample_rate.
  3. validate_record rejects a chunk with non-.wav audio.
  4. validate_record rejects a chunk with duration out of
     range (0 / negative / over MAX).
  5. iter_manifest yields validated samples in file order.
  6. iter_manifest skips invalid lines (lenient reader).
  7. summarise computes total_chunks / total_duration_s.
  8. summarise returns an empty summary for a missing file
     (graceful Record-card render when no recording yet).

What we DON'T test here:
- The actual audio files exist on disk (covered by the
  Tauri Rust tests in a follow-up sprint).
- The transcription quality (covered by the held-out
  eval in Sprint 32, `tests/voice/test_held_out_eval.py`).
- The LoRA training itself (covered by
  `test_finetune_script.py` end-to-end runbook tests).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.voice.self_record_manifest import (
    EXPECTED_SAMPLE_RATE,
    MANIFEST_FILENAME,
    MAX_DURATION_S,
    ManifestFormatError,
    ManifestSummary,
    SelfRecordSample,
    iter_manifest,
    summarise,
    validate_record,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _valid_record(
    audio_path: str = "/tmp/yue-self-2026-06-18/chunk-001.wav",
    text: str = "今日天氣好好",
    duration_s: float = 30.0,
    sample_rate: int = EXPECTED_SAMPLE_RATE,
) -> dict:
    """Build a valid manifest row as a dict (the shape
    `recording.rs` will write per line)."""
    return {
        "audio_path": audio_path,
        "text": text,
        "duration_s": duration_s,
        "sample_rate": sample_rate,
    }


def _write_manifest(path: Path, rows: list[dict]) -> None:
    """Write a JSONL manifest to disk (mirror of the
    Tauri writer's output format). One JSON object per line;
    trailing newline on every line is fine — `iter_manifest`
    strips before parsing.
    """
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Tests (8 spec tests — matches FEATURE-SPEC-SPRINT26.md §5
# "5-8 tests for self-record manifest")
# ---------------------------------------------------------------------------


def test_validate_record_accepts_valid_chunk():
    """A 4-key dict with the canonical types + values
    returns a typed `SelfRecordSample`. Pinning this means
    the JSONL contract has a single source of truth —
    `validate_record` — and any future contract change has
    to flow through here.
    """
    row = _valid_record()
    sample = validate_record(row)
    assert isinstance(sample, SelfRecordSample)
    assert sample.audio_path == row["audio_path"]
    assert sample.text == row["text"]
    assert sample.duration_s == 30.0
    assert sample.sample_rate == EXPECTED_SAMPLE_RATE


def test_validate_record_rejects_missing_sample_rate():
    """A chunk missing `sample_rate` raises
    `ManifestFormatError`. The error message must
    include the field name so the operator can find
    the bad row in a 60-chunk recording without
    bisecting the file.
    """
    bad = _valid_record()
    bad.pop("sample_rate")
    with pytest.raises(ManifestFormatError, match="sample_rate"):
        validate_record(bad)


def test_validate_record_rejects_non_wav_audio_path():
    """`audio_path` must end with `.wav`. The chunker
    writes 16kHz mono s16le WAV (WhisperProcessor's
    expected format); allowing other formats would
    force every downstream consumer to guess.
    """
    with pytest.raises(ManifestFormatError, match=r"\.wav"):
        validate_record(_valid_record(audio_path="/tmp/chunk-001.mp3"))


def test_validate_record_rejects_duration_out_of_range():
    """Duration outside `[MIN_DURATION_S, MAX_DURATION_S]`
    (1s..120s per the module contract) raises. The Tauri
    pipeline targets 30s but allows 10s (early stop) up
    to 60s (extend); 120s is the hard upper bound that
    covers any pathological chunker bug.
    """
    # Zero / negative: rejected
    with pytest.raises(ManifestFormatError, match="duration_s"):
        validate_record(_valid_record(duration_s=0))
    # Above the upper bound: rejected
    with pytest.raises(ManifestFormatError, match="duration_s"):
        validate_record(_valid_record(duration_s=MAX_DURATION_S + 1))
    # At the boundary: accepted (positive control)
    sample = validate_record(_valid_record(duration_s=MAX_DURATION_S))
    assert sample.duration_s == MAX_DURATION_S


def test_iter_manifest_yields_validated_samples(tmp_path: Path):
    """A 3-chunk valid manifest yields 3 `SelfRecordSample`
    in file order. Round-trip check: write → iterate →
    assert equal content.
    """
    manifest = tmp_path / MANIFEST_FILENAME
    rows = [
        _valid_record(
            audio_path="/tmp/yue-self-2026-06-18/chunk-001.wav",
            text="第一句",
        ),
        _valid_record(
            audio_path="/tmp/yue-self-2026-06-18/chunk-002.wav",
            text="第二句",
        ),
        _valid_record(
            audio_path="/tmp/yue-self-2026-06-18/chunk-003.wav",
            text="第三句",
            duration_s=18.5,  # short final chunk
        ),
    ]
    _write_manifest(manifest, rows)
    samples = list(iter_manifest(manifest))
    assert len(samples) == 3
    assert [s.text for s in samples] == ["第一句", "第二句", "第三句"]
    assert samples[2].duration_s == 18.5


def test_iter_manifest_skips_invalid_lines_with_warning(tmp_path: Path):
    """Invalid lines are **skipped** (not fatal) by the
    streaming reader — a mid-session partial chunk
    shouldn't crash the trainer. We assert (a) the valid
    lines survive, (b) the invalid lines don't appear in
    the output, and (c) the streaming reader doesn't
    raise on the malformed input.
    """
    manifest = tmp_path / MANIFEST_FILENAME
    manifest.write_text(
        json.dumps(_valid_record(audio_path="/tmp/chunk-001.wav")) + "\n"
        + "this is not json\n"  # malformed line 2
        + json.dumps(
            _valid_record(audio_path="/tmp/chunk-003.wav")
        ) + "\n"
        + json.dumps(
            _valid_record(audio_path="/tmp/chunk-004.mp3")
        ) + "\n",  # schema violation line 4 (wrong suffix)
        encoding="utf-8",
    )
    samples = list(iter_manifest(manifest))
    # Only chunks 001 and 003 (the .wav ones) survive.
    assert len(samples) == 2
    assert samples[0].audio_path.endswith("chunk-001.wav")
    assert samples[1].audio_path.endswith("chunk-003.wav")


def test_summarise_total_duration_and_count(tmp_path: Path):
    """A 3-chunk manifest (30 + 30 + 18.5 = 78.5s)
    summarises to total_chunks=3, total_duration_s=78.5,
    sample_rate=16000, rejected_lines=0. The Record
    card's completion summary uses these numbers.
    """
    manifest = tmp_path / MANIFEST_FILENAME
    _write_manifest(
        manifest,
        [
            _valid_record(audio_path="/tmp/c1.wav", duration_s=30.0),
            _valid_record(audio_path="/tmp/c2.wav", duration_s=30.0),
            _valid_record(audio_path="/tmp/c3.wav", duration_s=18.5),
        ],
    )
    summary = summarise(manifest)
    assert isinstance(summary, ManifestSummary)
    assert summary.total_chunks == 3
    assert summary.total_duration_s == 78.5
    assert summary.sample_rate == EXPECTED_SAMPLE_RATE
    assert summary.rejected_lines == 0


def test_summarise_missing_file_returns_empty_summary(tmp_path: Path):
    """A missing manifest file returns an empty summary
    (not a crash). The Record card shows "0 chunks, 0
    minutes" while the recording pipeline hasn't
    written anything yet. The default `sample_rate`
    is `EXPECTED_SAMPLE_RATE` so the schema's positivity
    invariant doesn't surface as `None` to the UI.
    """
    summary = summarise(tmp_path / "nope.jsonl")
    assert summary.total_chunks == 0
    assert summary.total_duration_s == 0.0
    assert summary.sample_rate == EXPECTED_SAMPLE_RATE
    assert summary.rejected_lines == 0

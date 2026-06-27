"""Sprint 45 — manifest preflight validation tests.

Coverage (4 tests):
1. Valid manifest → no error.
2. Missing manifest.jsonl → friendly error.
3. Empty manifest → "manifest is empty" error.
4. All-rows-garbage manifest → still reports empty (iter yields 0).

The preflight check is a thin wrapper over
`app.voice.self_record_manifest.iter_manifest` — these tests
exercise it directly without going through the FastAPI layer.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.api.voice_config_api import _preflight_validate_manifest


def test_preflight_passes_with_valid_manifest(tmp_path: Path):
    """Happy path: 3 valid rows → returns None."""
    manifest = tmp_path / "manifest.jsonl"
    lines = []
    for i in range(3):
        lines.append(json.dumps({
            "audio_path": str(tmp_path / f"chunk-{i:03}.wav"),
            "text": f"正常 {i}",
            "duration_s": 30.0,
            "sample_rate": 16000,
        }))
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")

    err = _preflight_validate_manifest(tmp_path)
    assert err is None


def test_preflight_fails_with_missing_manifest_jsonl(tmp_path: Path):
    """No manifest at all → error message starts with the expected hint."""
    err = _preflight_validate_manifest(tmp_path)
    assert err is not None
    assert err.startswith("manifest.jsonl not found")
    assert "Did the Record card finish flushing" in err


def test_preflight_fails_with_empty_manifest(tmp_path: Path):
    """Empty JSONL file → 'manifest is empty'."""
    (tmp_path / "manifest.jsonl").write_text("", encoding="utf-8")
    err = _preflight_validate_manifest(tmp_path)
    assert err is not None
    assert "manifest is empty" in err


def test_preflight_fails_with_garbage_jsonl(tmp_path: Path):
    """Manifest with all-invalid rows → still treated as empty."""
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text(
        "{not valid json}\n"
        + json.dumps({"audio_path": "x.wav", "text": "", "duration_s": 30.0, "sample_rate": 16000})
        + "\n",
        encoding="utf-8",
    )
    err = _preflight_validate_manifest(tmp_path)
    # Either "manifest is empty" (no valid rows) or the garbage
    # JSON parses but the empty text gets rejected, leaving 0
    # valid rows → still "manifest is empty".
    assert err is not None
    assert "manifest is empty" in err
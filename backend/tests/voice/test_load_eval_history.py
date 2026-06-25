"""Sprint 39 — held_out_eval.load_eval_history() tests.

Verifies the trend JSON loader directly (no FastAPI surface).
The 4 scenarios:
  1. Empty dir → [].
  2. Sort order is timestamp_ms DESC (newest first), not filename order.
  3. Limit truncates to top N.
  4. Corrupted JSONs skipped; valid ones still returned.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.voice.held_out_eval import load_eval_history


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_run(results_dir: Path, iso_ts: str, wer: float, passed: bool) -> Path:
    results_dir.mkdir(parents=True, exist_ok=True)
    body = {
        "timestamp": iso_ts,
        "results": [
            {
                "timestamp": iso_ts,
                "wav_path": f"/tmp/held-out-{iso_ts}.wav",
                "transcript_path": f"/tmp/held-out-{iso_ts}.txt",
                "reference": "你好 世界",
                "hypothesis": "你好 世界",
                "wer": wer,
                "threshold": 0.15,
                "passed": passed,
                "duration_s": 1.23,
                "asr_backend": "whisper_local",
                "notes": "",
            }
        ],
    }
    safe_ts = iso_ts.replace("-", "").replace(":", "").replace("+", "")[:15] + "Z"
    out = results_dir / f"{safe_ts}.json"
    out.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
    return out


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_empty_dir_returns_empty_list(tmp_path: Path):
    """No `*.json` files → [] (no crash, no fallback to source tree)."""
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    assert load_eval_history(results_dir, limit=7) == []


def test_missing_dir_returns_empty_list(tmp_path: Path):
    """Non-existent dir → [] (no crash)."""
    missing = tmp_path / "does-not-exist"
    assert load_eval_history(missing, limit=7) == []


def test_sort_order_is_newest_first(tmp_path: Path):
    """10 files written in ASC order → loader returns them DESC."""
    results_dir = tmp_path / "results"
    for i in range(10):
        # Filename order: 00, 01, ..., 09
        # Sort key (timestamp) is identical ascending pattern.
        iso_ts = f"2026-06-25T12:00:0{i}+00:00"
        # WER pattern: 0.00 .. 0.45 — lets us assert the row's
        # position by WER value, which is unique per row.
        _write_run(results_dir, iso_ts, wer=0.01 * i, passed=True)

    rows = load_eval_history(results_dir, limit=10)
    assert len(rows) == 10
    # Newest first: row[0] is ts=09 → wer_pct=9.0
    assert rows[0]["wer_pct"] == pytest.approx(9.0)
    assert rows[9]["wer_pct"] == pytest.approx(0.0)
    # Strictly descending wer_pct.
    for i in range(len(rows) - 1):
        assert rows[i]["wer_pct"] > rows[i + 1]["wer_pct"]


def test_limit_truncates_to_top_n(tmp_path: Path):
    """`limit=3` → exactly 3 rows, the 3 newest."""
    results_dir = tmp_path / "results"
    for i in range(10):
        iso_ts = f"2026-06-25T12:00:0{i}+00:00"
        _write_run(results_dir, iso_ts, wer=0.01 * i, passed=True)

    rows = load_eval_history(results_dir, limit=3)
    assert len(rows) == 3
    # Newest first: 09, 08, 07.
    assert rows[0]["wer_pct"] == pytest.approx(9.0)
    assert rows[1]["wer_pct"] == pytest.approx(8.0)
    assert rows[2]["wer_pct"] == pytest.approx(7.0)


def test_corrupted_json_skipped_gracefully(tmp_path: Path):
    """5 valid + 3 corrupted → 5 rows returned (in newest-first order)."""
    results_dir = tmp_path / "results"
    for i in range(5):
        iso_ts = f"2026-06-25T13:00:0{i}+00:00"
        _write_run(results_dir, iso_ts, wer=0.05, passed=True)

    # Bad wer type — _parse_summary returns None on this row.
    (results_dir / "bad-wer.json").write_text(json.dumps({
        "timestamp": "2026-06-25T13:00:00+00:00",
        "results": [{"wer": "not-a-number"}],
    }), encoding="utf-8")

    # Missing summary timestamp — _parse_summary returns None.
    (results_dir / "no-ts.json").write_text(json.dumps({
        "results": [{"wer": 0.05}],
    }), encoding="utf-8")

    # Broken JSON — json.JSONDecodeError caught.
    (results_dir / "syntax.json").write_text("{ not json", encoding="utf-8")

    rows = load_eval_history(results_dir, limit=10)
    assert len(rows) == 5
    for r in rows:
        assert r["wer_pct"] == pytest.approx(5.0)
        assert r["passed"] is True

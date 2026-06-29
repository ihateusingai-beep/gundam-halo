"""Sprint 46 — GET /voice/eval-corpus-breakdown endpoint tests.

Coverage (4 tests):
1. Empty results dir → empty breakdown.
2. Single-corpus breakdown (3 runs all tagged self:2026-06-27).
3. Multi-corpus breakdown isolates per-corpus stats.
4. Unattributed runs bucket under the \"unattributed\" key.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


def _write_trend(
    results_dir: Path,
    filename: str,
    wer: float,
    backend: str,
    corpus_id: str,
    ts: str = "2026-06-27T10:00:00+00:00",
    mtime_offset: float = 0.0,
) -> None:
    """Write a trend JSON + force mtime so ordering is deterministic."""
    results_dir.mkdir(parents=True, exist_ok=True)
    path = results_dir / filename
    path.write_text(
        json.dumps({
            "timestamp": ts,
            "results": [
                {
                    "timestamp": ts,
                    "wav_path": "/tmp/x.wav",
                    "transcript_path": "/tmp/x.txt",
                    "reference": "你好",
                    "hypothesis": "你好",
                    "wer": wer,
                    "threshold": 0.15,
                    "passed": wer < 0.15,
                    "duration_s": 30.0,
                    "asr_backend": backend,
                    "notes": "",
                    "corpus_id": corpus_id,
                }
            ],
        }),
        encoding="utf-8",
    )
    # Force mtime so the endpoint's load_eval_history sees a
    # deterministic sort order.
    if mtime_offset:
        mtime = time.time() + mtime_offset
        os.utime(path, (mtime, mtime))


@pytest.fixture
def client_with_home(monkeypatch, tmp_path):
    """TestClient + the breakdown endpoint's source dir redirected.

    held_out_results_dir() is a module-level function that returns
    a hardcoded path under the repo. We patch it so the endpoint
    reads from our tmp_path instead of the real 18 historical
    files in tests/voice/held_out_results/.
    """
    import app.api.voice_config_api as vc

    fake_results_dir = tmp_path / "tests" / "voice" / "held_out_results"
    fake_results_dir.mkdir(parents=True)
    monkeypatch.setattr(
        vc, "held_out_results_dir", lambda: fake_results_dir
    )
    with TestClient(__import__("app.main", fromlist=["halo_app"]).halo_app) as client:
        yield client, tmp_path


def test_empty_results_dir_returns_empty_breakdown(client_with_home):
    """No trend JSONs → empty breakdown (not 404)."""
    client, _home = client_with_home
    res = client.get("/voice/eval-corpus-breakdown?limit=20")
    assert res.status_code == 200
    data = res.json()
    assert data["by_corpus"] == {}
    assert data["timeline"] == []
    assert data["total_runs"] == 0


def test_single_corpus_breakdown_basic(client_with_home):
    """3 runs all tagged self:2026-06-27 → 1 corpus entry + 3 timeline rows."""
    client, home = client_with_home
    results_dir = home / "tests" / "voice" / "held_out_results"
    _write_trend(results_dir, "run-1.json", 0.10, "whisper_local", "self:2026-06-27",
                 ts="2026-06-27T10:00:00+00:00", mtime_offset=-200)
    _write_trend(results_dir, "run-2.json", 0.08, "whisper_hf", "self:2026-06-27",
                 ts="2026-06-27T11:00:00+00:00", mtime_offset=-100)
    _write_trend(results_dir, "run-3.json", 0.06, "whisper_hf", "self:2026-06-27",
                 ts="2026-06-27T12:00:00+00:00", mtime_offset=0)

    res = client.get("/voice/eval-corpus-breakdown?limit=20")
    assert res.status_code == 200
    data = res.json()
    assert data["total_runs"] == 3
    assert len(data["by_corpus"]) == 1
    assert "self:2026-06-27" in data["by_corpus"]
    entry = data["by_corpus"]["self:2026-06-27"]
    assert entry["run_count"] == 3
    assert entry["avg_wer_pct"] == 8.0  # avg of 10, 8, 6
    assert entry["best_wer_pct"] == 6.0
    assert entry["passed"] is True
    # Latest run is 6.0% (run-3).
    assert entry["latest_wer_pct"] == 6.0

    # Timeline sorted oldest-first.
    assert len(data["timeline"]) == 3
    assert data["timeline"][0]["wer_pct"] == 10.0
    assert data["timeline"][-1]["wer_pct"] == 6.0


def test_multi_corpus_breakdown_isolates_stats(client_with_home):
    """2 corpora → by_corpus has 2 entries with isolated stats."""
    client, home = client_with_home
    results_dir = home / "tests" / "voice" / "held_out_results"
    # self:2026-06-27: 2 runs, average (12 + 8) / 2 = 10
    _write_trend(results_dir, "self-1.json", 0.12, "whisper_hf", "self:2026-06-27",
                 ts="2026-06-27T10:00:00+00:00", mtime_offset=-200)
    _write_trend(results_dir, "self-2.json", 0.08, "whisper_hf", "self:2026-06-27",
                 ts="2026-06-27T11:00:00+00:00", mtime_offset=-100)
    # common-voice-yue: 1 run
    _write_trend(results_dir, "cv-1.json", 0.15, "whisper_local", "common-voice-yue",
                 ts="2026-06-26T10:00:00+00:00", mtime_offset=0)

    res = client.get("/voice/eval-corpus-breakdown?limit=20")
    assert res.status_code == 200
    data = res.json()
    assert data["total_runs"] == 3
    assert len(data["by_corpus"]) == 2
    self_entry = data["by_corpus"]["self:2026-06-27"]
    assert self_entry["run_count"] == 2
    assert self_entry["avg_wer_pct"] == 10.0
    cv_entry = data["by_corpus"]["common-voice-yue"]
    assert cv_entry["run_count"] == 1
    assert cv_entry["avg_wer_pct"] == 15.0


def test_unattributed_runs_bucketed_under_key(client_with_home):
    """Legacy run with corpus_id=\"\" → bucketed as \"unattributed\"."""
    client, home = client_with_home
    results_dir = home / "tests" / "voice" / "held_out_results"
    _write_trend(results_dir, "legacy.json", 0.20, "whisper_local", "",
                 ts="2026-06-25T10:00:00+00:00", mtime_offset=0)

    res = client.get("/voice/eval-corpus-breakdown?limit=20")
    assert res.status_code == 200
    data = res.json()
    assert data["total_runs"] == 1
    assert "unattributed" in data["by_corpus"]
    entry = data["by_corpus"]["unattributed"]
    assert entry["run_count"] == 1
    assert entry["avg_wer_pct"] == 20.0
    assert entry["passed"] is False  # 20 > 15 threshold
    # Timeline entry has corpus_id="unattributed" (not "").
    assert data["timeline"][0]["corpus_id"] == "unattributed"
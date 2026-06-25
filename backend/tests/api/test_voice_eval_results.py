"""Sprint 39 — /voice/eval-results route tests.

Verifies:
  1. Empty results dir → `{ latest: null, history: [], threshold_pct: 15.0 }`.
  2. 10 trend JSONs → `latest` is the newest, `history` is 7 most recent.
  3. Corrupted JSONs are skipped; valid ones still load.

Note: voice routes live at `/voice/*` (no `/api` prefix), per the
pre-Sprint-42 convention used by `/voice/status` and `/voice/config`.
`/api/setup/voice-*` is a separate setup-wizard surface that mounts
under `/api/setup/` and shouldn't be confused with this endpoint.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client(monkeypatch, tmp_path):
    """Fresh HALO_HOME → backend with the new eval-results route."""
    monkeypatch.setenv("HALO_HOME", str(tmp_path))
    monkeypatch.setenv("MINIMAX_API_KEY", "test-fake")

    from app.core import config as config_mod
    config_mod.reset_config()

    from app.main import create_app
    return TestClient(create_app())


def _write_run(
    results_dir: Path,
    iso_ts: str,
    wer: float,
    passed: bool,
    asr_backend: str = "whisper_local",
) -> Path:
    """Write one trend JSON matching the CLI's `to_json()` shape."""
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
                "asr_backend": asr_backend,
                "notes": "",
            }
        ],
    }
    # Mirror the CLI filename pattern: YYYYMMDDTHHMMSSZ.json
    safe_ts = iso_ts.replace("-", "").replace(":", "").replace("+", "")[:15] + "Z"
    out = results_dir / f"{safe_ts}.json"
    out.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
    return out


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_empty_results_dir_returns_empty(client, tmp_path):
    """No trend JSONs → empty list, null latest, default threshold."""
    # Ensure the helper resolves to a directory under our tmp_path so
    # the test doesn't accidentally read the live source-tree dir.
    fake_results = tmp_path / "tests" / "voice" / "held_out_results"
    fake_results.mkdir(parents=True, exist_ok=True)

    from app.voice import held_out_eval
    monkey_results_dir = fake_results
    held_out_eval.held_out_results_dir = lambda: monkey_results_dir

    r = client.get("/voice/eval-results")
    assert r.status_code == 200
    body = r.json()
    assert body["latest"] is None
    assert body["history"] == []
    assert body["threshold_pct"] == 15.0


def test_ten_runs_returns_latest_plus_seven(client, tmp_path):
    """10 trend JSONs → `latest` is the newest, `history` is 7 most recent."""
    fake_results = tmp_path / "tests" / "voice" / "held_out_results"
    fake_results.mkdir(parents=True, exist_ok=True)

    from app.voice import held_out_eval
    held_out_eval.held_out_results_dir = lambda: fake_results

    # Write 10 runs with ascending timestamps + ascending WER (so we
    # can verify the sort is newest-first, not file-creation order).
    timestamps = [
        f"2026-06-25T10:00:0{i}+00:00" for i in range(10)
    ]
    wers = [0.05 * i for i in range(10)]   # 0.00, 0.05, ..., 0.45
    passed = [w < 0.15 for w in wers]      # first 3 pass, rest fail
    for ts, w, p in zip(timestamps, wers, passed):
        _write_run(fake_results, ts, w, p)

    r = client.get("/voice/eval-results")
    assert r.status_code == 200
    body = r.json()

    # Newest first: history[0] is 09, history[6] is 03.
    assert len(body["history"]) == 7
    assert body["history"][0]["wer_pct"] == pytest.approx(45.0)
    assert body["history"][6]["wer_pct"] == pytest.approx(15.0)

    # `latest` is history[0].
    assert body["latest"] is not None
    assert body["latest"]["wer_pct"] == pytest.approx(45.0)
    assert body["latest"]["passed"] is False  # 0.45 > 0.15

    # Threshold default (no test-config.toml) is 15.0.
    assert body["threshold_pct"] == 15.0


def test_corrupted_json_is_skipped_not_fatal(client, tmp_path):
    """Malformed trend JSONs are silently skipped; valid ones still load."""
    fake_results = tmp_path / "tests" / "voice" / "held_out_results"
    fake_results.mkdir(parents=True, exist_ok=True)

    from app.voice import held_out_eval
    held_out_eval.held_out_results_dir = lambda: fake_results

    # 5 valid runs (ascending ts)
    for i in range(5):
        _write_run(
            fake_results,
            f"2026-06-25T11:00:0{i}+00:00",
            wer=0.10,
            passed=True,
        )

    # 1 with bad wer type (string instead of float)
    (fake_results / "bad-wer.json").write_text(json.dumps({
        "timestamp": "2026-06-25T11:00:00+00:00",
        "results": [{"wer": "not-a-number"}],
    }), encoding="utf-8")

    # 1 with missing timestamp on the summary itself
    (fake_results / "no-ts.json").write_text(json.dumps({
        "results": [],
    }), encoding="utf-8")

    # 1 with broken JSON
    (fake_results / "syntax.json").write_text("{ not json", encoding="utf-8")

    r = client.get("/voice/eval-results")
    assert r.status_code == 200
    body = r.json()

    # Only the 5 valid runs survive.
    assert len(body["history"]) == 5
    # All 5 have valid WER + pass state.
    for entry in body["history"]:
        assert entry["wer_pct"] == pytest.approx(10.0)
        assert entry["passed"] is True


def test_threshold_reads_from_test_config_toml(client, tmp_path, monkeypatch):
    """When `~/.gundam-halo/test-config.toml` exists with a custom
    threshold, the endpoint surfaces it as `threshold_pct`."""
    halo_home = tmp_path
    (halo_home / "test-config.toml").write_text(
        "[held_out_eval]\nwer_threshold = 0.10\n",
        encoding="utf-8",
    )
    # Pin HALO_HOME so `halo_home()` resolves to our tmp_path.
    monkeypatch.setenv("HALO_HOME", str(halo_home))

    # We also need the endpoint to read from the source-tree results dir
    # for the empty-history check; isolate that too.
    fake_results = halo_home / "tests" / "voice" / "held_out_results"
    fake_results.mkdir(parents=True, exist_ok=True)
    from app.voice import held_out_eval
    held_out_eval.held_out_results_dir = lambda: fake_results

    r = client.get("/voice/eval-results")
    assert r.status_code == 200
    body = r.json()
    assert body["threshold_pct"] == 10.0
    assert body["history"] == []

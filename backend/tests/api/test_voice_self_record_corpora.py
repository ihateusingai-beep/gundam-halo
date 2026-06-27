"""Sprint 45 — GET /voice/self-record-corpora endpoint tests.

Coverage (5 tests):
1. Empty HALO_HOME / no recordings dir → empty list.
2. Single corpus → summarised correctly.
3. Multiple corpora → sorted newest-first by mtime.
4. Latest flag only on first item.
5. Rejected manifest lines surface in the summary.

These use FastAPI's TestClient against a fresh app instance with
`HALO_HOME` redirected to a tmp dir, so they don't pollute the
user's real `$HALO_HOME/recordings/`.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import halo_app


def _write_valid_manifest(manifest: Path, n: int = 3) -> None:
    """Write n valid manifest rows."""
    manifest.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for i in range(n):
        lines.append(json.dumps({
            "audio_path": str(manifest.parent / f"chunk-{i:03}.wav"),
            "text": f"測試第 {i} 段",
            "duration_s": 30.0,
            "sample_rate": 16000,
        }))
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _make_chunk_wavs(corpus_dir: Path, n: int = 3) -> None:
    """Create n placeholder chunk-NNN.wav files (empty)."""
    for i in range(n):
        (corpus_dir / f"chunk-{i:03}.wav").write_bytes(b"")


@pytest.fixture
def client_with_home(monkeypatch, tmp_path: Path):
    """TestClient + HALO_HOME redirected to tmp_path."""
    monkeypatch.setenv("HALO_HOME", str(tmp_path))
    # The endpoint reads HALO_HOME via _resolve_halo_home at request
    # time, so the env var must be set BEFORE the TestClient is
    # constructed (or at least before the request fires).
    with TestClient(halo_app) as client:
        yield client, tmp_path


def test_no_recordings_dir_returns_empty_list(client_with_home):
    """Missing recordings/ dir → empty list (NOT 404)."""
    client, _home = client_with_home
    res = client.get("/voice/self-record-corpora")
    assert res.status_code == 200
    data = res.json()
    assert data["corpora"] == []
    assert data["latest_path"] is None


def test_single_corpus_summarised_correctly(client_with_home):
    """One corpus dir + 3 chunks + 3 valid manifest rows."""
    client, home = client_with_home
    recordings = home / "recordings"
    corpus = recordings / "yue-self-2026-06-27"
    corpus.mkdir(parents=True)
    _make_chunk_wavs(corpus, n=3)
    _write_valid_manifest(corpus / "manifest.jsonl", n=3)

    res = client.get("/voice/self-record-corpora")
    assert res.status_code == 200
    data = res.json()
    assert len(data["corpora"]) == 1
    c = data["corpora"][0]
    assert c["date"] == "2026-06-27"
    assert c["chunk_count"] == 3
    assert c["manifest_chunks"] == 3
    assert c["total_duration_s"] == 90.0
    assert c["rejected_lines"] == 0
    assert c["is_latest"] is True
    assert data["latest_path"] == str(corpus)


def test_multiple_corpora_sorted_newest_first(client_with_home):
    """Three corpora with different mtimes → order = newest first."""
    client, home = client_with_home
    recordings = home / "recordings"
    for date_str, mtime_offset in [
        ("2026-06-25", -7200),
        ("2026-06-27", 0),
        ("2026-06-26", -3600),
    ]:
        corpus = recordings / f"yue-self-{date_str}"
        corpus.mkdir(parents=True)
        _make_chunk_wavs(corpus, n=1)
        _write_valid_manifest(corpus / "manifest.jsonl", n=1)
        # Force mtime ordering.
        ts = time.time() + mtime_offset
        os.utime(corpus, (ts, ts))

    res = client.get("/voice/self-record-corpora")
    assert res.status_code == 200
    data = res.json()
    dates = [c["date"] for c in data["corpora"]]
    assert dates == ["2026-06-27", "2026-06-26", "2026-06-25"]


def test_latest_flag_only_on_first(client_with_home):
    """`is_latest: true` only on the first (newest) corpus."""
    client, home = client_with_home
    recordings = home / "recordings"
    for date_str in ["2026-06-26", "2026-06-27"]:
        corpus = recordings / f"yue-self-{date_str}"
        corpus.mkdir(parents=True)
        _write_valid_manifest(corpus / "manifest.jsonl", n=1)
    # Force mtime ordering so 2026-06-27 is newest.
    os.utime(recordings / "yue-self-2026-06-26", (time.time() - 3600, time.time() - 3600))
    os.utime(recordings / "yue-self-2026-06-27", (time.time(), time.time()))

    res = client.get("/voice/self-record-corpora")
    assert res.status_code == 200
    corpora = res.json()["corpora"]
    assert corpora[0]["is_latest"] is True
    assert corpora[1]["is_latest"] is False


def test_corpus_with_rejected_manifest_lines_reports_count(client_with_home):
    """1 valid + 1 garbage JSONL row → rejected_lines=1, manifest_chunks=1."""
    client, home = client_with_home
    recordings = home / "recordings"
    corpus = recordings / "yue-self-2026-06-27"
    corpus.mkdir(parents=True)
    _make_chunk_wavs(corpus, n=2)
    manifest = corpus / "manifest.jsonl"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        json.dumps({
            "audio_path": str(corpus / "chunk-000.wav"),
            "text": "正常嘅一行",
            "duration_s": 30.0,
            "sample_rate": 16000,
        })
        + "\n"
        + "{not valid json}\n"
        + json.dumps({
            "audio_path": str(corpus / "chunk-001.wav"),
            "text": "",  # empty text → schema violation
            "duration_s": 30.0,
            "sample_rate": 16000,
        })
        + "\n",
        encoding="utf-8",
    )

    res = client.get("/voice/self-record-corpora")
    assert res.status_code == 200
    c = res.json()["corpora"][0]
    assert c["manifest_chunks"] == 1
    assert c["rejected_lines"] == 2  # 1 bad JSON + 1 empty text
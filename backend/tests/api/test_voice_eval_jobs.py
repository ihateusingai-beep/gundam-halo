"""Sprint 40 — /voice/run-held-out-eval + /voice/run-finetune route tests.

Coverage (5 tests):
1. POST /run-held-out-eval returns 202 with job_id.
2. POST /run-finetune returns 202 with job_id.
3. GET /run-held-out-eval/{job_id} returns 404 for unknown id.
4. GET /run-held-out-eval/{job_id} returns the full job state for known id.
5. GET /voice/list-jobs returns the list newest-first.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _reset_eval_job_singleton():
    """Wipe the module-level EvalJobStore singleton between tests.

    Without this, jobs from a previous test persist in the
    in-memory dict + JSON state file, leaking into the next
    test's /list-jobs assertion.
    """
    from app.core import eval_jobs as ej
    global _singleton_ref  # noqa: F824 — declared below for type clarity
    _singleton_ref = ej._singleton
    ej._singleton = None
    yield
    ej._singleton = _singleton_ref


_singleton_ref = None  # module-level holder for the prior singleton


@pytest.fixture
def client(monkeypatch, tmp_path):
    """Fresh HALO_HOME → backend with the new Sprint 40 endpoints."""
    monkeypatch.setenv("HALO_HOME", str(tmp_path))
    monkeypatch.setenv("MINIMAX_API_KEY", "test-fake")

    from app.core import config as config_mod
    config_mod.reset_config()

    from app.main import create_app
    return TestClient(create_app())


def test_post_run_held_out_eval_returns_job_id(client):
    """POST starts a background eval thread + returns job_id."""
    r = client.post(
        "/voice/run-held-out-eval",
        json={"threshold": 0.15, "model_size": "base"},
    )
    assert r.status_code == 200
    body = r.json()
    assert "job_id" in body
    assert body["status"] == "pending"
    assert body["job_id"].startswith("held-out-eval-")


def test_post_run_finetune_returns_job_id(client, tmp_path):
    """POST starts a background finetune thread + returns job_id.

    Sprint 45: the endpoint now requires a valid manifest at the
    resolved corpus dir (preflight). Test writes a fake manifest
    + chunk wav so preflight passes.
    """
    corpus = tmp_path / "yue-self-2026-06-27"
    corpus.mkdir()
    (corpus / "manifest.jsonl").write_text(
        json.dumps({
            "audio_path": str(corpus / "chunk-000.wav"),
            "text": "你好世界",
            "duration_s": 30.0,
            "sample_rate": 16000,
        }) + "\n",
        encoding="utf-8",
    )
    r = client.post(
        "/voice/run-finetune",
        json={
            "train_corpus_dir": str(corpus),
            "output_model_dir": "/tmp/model",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert "job_id" in body
    assert body["job_id"].startswith("finetune-")
    # Sprint 45: response echoes back the resolved paths.
    assert body["train_corpus_dir"] == str(corpus)


def test_get_run_held_out_eval_returns_404_for_unknown_job(client):
    """GET with a non-existent job_id → 404."""
    r = client.get("/voice/run-held-out-eval/nonexistent-id-12345")
    assert r.status_code == 404
    body = r.json()
    assert "not found" in body["detail"].lower()


def test_get_run_held_out_eval_returns_full_state_for_known_job(client):
    """After POST + GET, the job's state is reflected."""
    r_post = client.post(
        "/voice/run-held-out-eval",
        json={"threshold": 0.10},
    )
    assert r_post.status_code == 200
    job_id = r_post.json()["job_id"]

    r_get = client.get(f"/voice/run-held-out-eval/{job_id}")
    assert r_get.status_code == 200
    body = r_get.json()
    assert body["job_id"] == job_id
    assert body["kind"] == "held-out-eval"
    assert body["status"] in ("pending", "running", "succeeded", "failed")


def test_list_jobs_returns_newest_first(client, tmp_path):
    """After 2 POSTs, /list-jobs returns both, newest first.

    Sprint 45: the finetune endpoint requires a valid manifest.
    Write a fake one before the second POST.
    """
    r1 = client.post("/voice/run-held-out-eval", json={})
    assert r1.status_code == 200
    time.sleep(0.05)  # ensure distinct started_at timestamps

    corpus = tmp_path / "yue-self-2026-06-27"
    corpus.mkdir()
    (corpus / "manifest.jsonl").write_text(
        json.dumps({
            "audio_path": str(corpus / "chunk-000.wav"),
            "text": "test",
            "duration_s": 30.0,
            "sample_rate": 16000,
        }) + "\n",
        encoding="utf-8",
    )
    r2 = client.post(
        "/voice/run-finetune",
        json={"train_corpus_dir": str(corpus)},
    )
    assert r2.status_code == 200

    r = client.get("/voice/list-jobs")
    assert r.status_code == 200
    body = r.json()
    assert "jobs" in body
    assert len(body["jobs"]) == 2
    # Newest first.
    assert body["jobs"][0]["job_id"] == r2.json()["job_id"]
    assert body["jobs"][1]["job_id"] == r1.json()["job_id"]


def test_run_held_out_eval_persists_trend_json_path(client, monkeypatch, tmp_path):
    """When the orchestrator writes a trend JSON, the job state
    records its path (verifies the success path through the thread)."""
    # Stub the orchestrator thread target so it doesn't actually run.
    # Sprint 56 R4: patch the actual call-site module
    # (`app.api.voice.eval_jobs`), not the legacy shim
    # (`app.api.voice_config_api`). The shim re-exports the function
    # so legacy tests still see the symbol, but `from ... import`
    # inside the endpoint binds to the original module — patching
    # the shim wouldn't affect the call site.
    import app.api.voice.eval_jobs as ej
    import app.api.voice_config_api as vc

    def fake_thread(job_id, args, halo_home):
        store = vc.get_store(halo_home)
        store.mark_running(job_id)
        # Write a fake trend JSON.
        results_dir = halo_home / "tests" / "voice" / "held_out_results"
        results_dir.mkdir(parents=True, exist_ok=True)
        results_dir.joinpath("fake-trend.json").write_text(
            json.dumps({"timestamp": "2026-06-27T10:00:00+00:00", "results": []}),
            encoding="utf-8",
        )
        store.complete_job(
            job_id, exit_code=0, trend_json_path=str(results_dir / "fake-trend.json")
        )

    monkeypatch.setattr(ej, "_run_orchestrator_thread", fake_thread)

    r = client.post("/voice/run-held-out-eval", json={})
    job_id = r.json()["job_id"]

    # Wait for the thread to finish (it's instant in the test).
    deadline = time.time() + 5
    while time.time() < deadline:
        state = client.get(f"/voice/run-held-out-eval/{job_id}").json()
        if state["status"] == "succeeded":
            break
        time.sleep(0.05)

    final = client.get(f"/voice/run-held-out-eval/{job_id}").json()
    assert final["status"] == "succeeded"
    assert final["exit_code"] == 0
    assert final["trend_json_path"] is not None
    assert final["trend_json_path"].endswith("fake-trend.json")
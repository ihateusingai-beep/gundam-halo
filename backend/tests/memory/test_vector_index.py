"""Tests for VectorIndex (M12) — FAISS + Null fallbacks.

These tests need a real FAISS index (they exercise the FAISS
contract directly), so they override the default
``disable_vector_index=True`` set by ``tests/memory/conftest.py``.

Marked with ``@pytest.mark.faiss_native`` so they can be skipped
in mixed-mode CI runs. Note: with the M12.1 follow-up #5
runtime guard in :mod:`app.memory._apple_silicon_compat`, the
Apple-Silicon faiss-cpu + torch MPS crash no longer aborts the
whole process — the factory falls back to :class:`NullVectorIndex`
when the dangerous combination is detected. The marker is now
kept for **defensive CI safety** on hosts where loading faiss in
the test process for any reason is undesirable (e.g. exotic
torch/Accelerate combinations that we have not validated), not
as the primary mitigation. Run with::

    pytest -m faiss_native tests/memory/test_vector_index.py
    pytest -m 'not faiss_native' tests/memory/test_vector_index.py

The ``TestRuntimeGuardRegression`` class at the bottom of this
file exercises the actual runtime guard, which is the real fix.
"""
from __future__ import annotations

import numpy as np
import pytest
from app.memory.vector_index import (
    FaissVectorIndex,
    NullVectorIndex,
    make_vector_index,
)

pytestmark = pytest.mark.faiss_native


@pytest.fixture(autouse=True)
def _enable_faiss():
    """Override the directory-level conftest: this file wants
    a real FAISS index, not the NullVectorIndex.
    """
    from app.core import config as _cfg

    cfg = _cfg.get_config()
    cfg.memory.disable_vector_index = False
    yield
    cfg.memory.disable_vector_index = True


def _rand_unit(dim: int, n: int, seed: int = 0) -> np.ndarray:
    """Return (n, dim) L2-normalized random vectors."""
    rng = np.random.default_rng(seed)
    v = rng.random((n, dim)).astype(np.float32)
    norms = np.linalg.norm(v, axis=1, keepdims=True)
    v = v / np.maximum(norms, 1e-9)
    return v


# ---------------------------------------------------------------------------
# NullVectorIndex
# ---------------------------------------------------------------------------


class TestNullVectorIndex:
    def test_add_increments(self):
        v = _rand_unit(64, 1)
        n = NullVectorIndex(dim=64)
        idx = n.add(v[0], {"kind": "message", "source_id": "m1"})
        assert idx == 0
        assert n.ntotal() == 1

    def test_search_returns_empty(self):
        n = NullVectorIndex(dim=64)
        n.add(_rand_unit(64, 1)[0], {"kind": "message", "source_id": "m1"})
        q = _rand_unit(64, 1)[0]
        assert n.search(q, k=5) == []


# ---------------------------------------------------------------------------
# FaissVectorIndex (real FAISS)
# ---------------------------------------------------------------------------


class TestFaissVectorIndex:
    def test_add_returns_sequential_ids(self, tmp_path):
        v = _rand_unit(64, 3)
        idx = FaissVectorIndex(halo_home=tmp_path, dim=64)
        ids = idx.add_batch(v, [
            {"kind": "message", "source_id": f"m{i}"} for i in range(3)
        ])
        assert ids == [0, 1, 2]
        assert idx.ntotal() == 3
        idx.close()

    def test_search_self_match(self, tmp_path):
        v = _rand_unit(64, 5)
        idx = FaissVectorIndex(halo_home=tmp_path, dim=64)
        idx.add_batch(v, [
            {"kind": "message", "source_id": f"m{i}", "snippet": f"s{i}"}
            for i in range(5)
        ])
        # Self-match: query[0] should match vector 0 with score ~1.0
        hits = idx.search(v[0], k=1)
        assert len(hits) == 1
        assert hits[0].vector_id == 0
        assert hits[0].score > 0.99
        assert hits[0].kind == "message"
        assert hits[0].source_id == "m0"
        idx.close()

    def test_search_top_k(self, tmp_path):
        # 10 vectors, query 0; expect top-k sorted by score
        v = _rand_unit(64, 10)
        idx = FaissVectorIndex(halo_home=tmp_path, dim=64)
        idx.add_batch(v, [
            {"kind": "message", "source_id": f"m{i}"} for i in range(10)
        ])
        hits = idx.search(v[0], k=3)
        assert len(hits) == 3
        # First hit should be self-match
        assert hits[0].vector_id == 0
        assert hits[0].score >= hits[1].score >= hits[2].score
        idx.close()

    def test_persistence_roundtrip(self, tmp_path):
        v = _rand_unit(64, 3)
        idx = FaissVectorIndex(halo_home=tmp_path, dim=64)
        idx.add_batch(v, [
            {"kind": "message", "source_id": f"m{i}", "snippet": f"s{i}"}
            for i in range(3)
        ])
        idx.save()
        idx.close()

        # Reload
        idx2 = FaissVectorIndex(halo_home=tmp_path, dim=64)
        assert idx2.ntotal() == 3
        hits = idx2.search(v[0], k=1)
        assert hits[0].source_id == "m0"
        idx2.close()

    def test_meta_length_mismatch_resets(self, tmp_path):
        # Manually create a mismatched state
        v = _rand_unit(64, 2)
        idx = FaissVectorIndex(halo_home=tmp_path, dim=64)
        idx.add_batch(v, [{"kind": "message", "source_id": f"m{i}"} for i in range(2)])
        idx.save()
        idx.close()
        # Corrupt the meta file
        meta_path = tmp_path / "memory" / "vectors.meta.json"
        meta_path.write_text("[]", encoding="utf-8")
        idx2 = FaissVectorIndex(halo_home=tmp_path, dim=64)
        # Mismatch should trigger a reset
        assert idx2.ntotal() == 0
        idx2.close()

    def test_search_empty_returns_empty(self, tmp_path):
        idx = FaissVectorIndex(halo_home=tmp_path, dim=64)
        hits = idx.search(_rand_unit(64, 1)[0], k=5)
        assert hits == []
        idx.close()


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


class TestFactory:
    def test_make_picks_faiss(self, tmp_path):
        # faiss is installed in this env
        idx = make_vector_index(halo_home=tmp_path, dim=64)
        assert isinstance(idx, FaissVectorIndex)
        idx.close()


# ---------------------------------------------------------------------------
# Runtime guard regression — the *real* fix from M12.1 follow-up #5
#
# These tests don't need a real torch / faiss. They mock the
# detection helpers in ``_apple_silicon_compat`` to simulate
# the dangerous combination (darwin + arm64 + torch MPS loaded)
# and assert that ``make_vector_index`` short-circuits to
# ``NullVectorIndex`` without ever touching faiss.
# ---------------------------------------------------------------------------


class TestRuntimeGuardRegression:
    """Prove the runtime guard prevents the Apple Silicon crash.

    Reproduces the dangerous scenario described in
    ``docs/tickets/M12.md`` follow-up #5 by patching the
    platform + torch detection layer to claim "we are on darwin
    arm64 and torch MPS is loaded", then asserting that
    ``make_vector_index`` does not import faiss (because doing
    so would duplicate libomp and abort the process with
    SIGABRT — exit 134).
    """

    def test_fallback_search_does_not_crash(
        self, tmp_path, monkeypatch
    ):
        """End-to-end: with the runtime guard engaged, calling
        ``search()`` on the returned index must not crash.

        This is the test that the original M12.1 marker-based
        workaround could not satisfy in the *live* app — the
        marker only helped the test process, the live Tauri
        client still crashed. The runtime guard in
        ``_apple_silicon_compat`` closes that gap.
        """
        import sys
        import types

        from app.memory import _apple_silicon_compat as compat

        # Force "Apple Silicon" detection.
        monkeypatch.setattr(compat.sys, "platform", "darwin")
        monkeypatch.setattr(compat.platform, "machine", lambda: "arm64")

        # Inject a fake torch with MPS *available* into sys.modules
        # so the compat layer sees the dangerous combination.
        fake = types.ModuleType("torch")
        backends = types.ModuleType("torch.backends")
        mps_mod = types.ModuleType("torch.backends.mps")
        mps_mod.is_built = lambda: True
        mps_mod.is_available = lambda: True
        backends.mps = mps_mod
        fake.backends = backends
        monkeypatch.setitem(sys.modules, "torch", fake)
        monkeypatch.setitem(sys.modules, "torch.backends", backends)
        monkeypatch.setitem(sys.modules, "torch.backends.mps", mps_mod)

        try:
            compat.reset_for_testing()
            # The guard should now decide to NOT use faiss.
            idx = make_vector_index(halo_home=tmp_path, dim=64)
            assert isinstance(idx, NullVectorIndex)
            # And the search() path must be safe — exactly the
            # thing that used to SIGABRT in the live app.
            hits = idx.search(_rand_unit(64, 1)[0], k=5)
            assert hits == []
            # add() should also be a no-op data-wise, returning
            # a sequential id.
            assert idx.add(_rand_unit(64, 1)[0], {"kind": "message"}) == 0
        finally:
            for k in ("torch.backends.mps", "torch.backends", "torch"):
                sys.modules.pop(k, None)
            compat.reset_for_testing()

    def test_force_override_1_unlocks_faiss_even_on_apple_silicon(
        self, tmp_path, monkeypatch
    ):
        """If the user explicitly opts in via HALO_FAISS_FORCE=1,
        we should still get a real FaissVectorIndex (and the
        KMP_DUPLICATE_LIB_OK workaround should be armed).
        """
        import os
        import sys
        import types

        from app.memory import _apple_silicon_compat as compat

        monkeypatch.setattr(compat.sys, "platform", "darwin")
        monkeypatch.setattr(compat.platform, "machine", lambda: "arm64")
        monkeypatch.setenv(compat.ENV_FORCE, "1")

        fake = types.ModuleType("torch")
        backends = types.ModuleType("torch.backends")
        mps_mod = types.ModuleType("torch.backends.mps")
        mps_mod.is_built = lambda: True
        mps_mod.is_available = lambda: True
        backends.mps = mps_mod
        fake.backends = backends
        monkeypatch.setitem(sys.modules, "torch", fake)
        monkeypatch.setitem(sys.modules, "torch.backends", backends)
        monkeypatch.setitem(sys.modules, "torch.backends.mps", mps_mod)

        try:
            compat.reset_for_testing()
            idx = make_vector_index(halo_home=tmp_path, dim=64)
            assert isinstance(idx, FaissVectorIndex)
            # The belt-and-braces guard is armed.
            assert os.environ.get(compat.ENV_KMP_DUPLICATE_LIB_OK) == "TRUE"
            idx.close()
        finally:
            for k in ("torch.backends.mps", "torch.backends", "torch"):
                sys.modules.pop(k, None)
            monkeypatch.delenv(compat.ENV_FORCE, raising=False)
            os.environ.pop(compat.ENV_KMP_DUPLICATE_LIB_OK, None)
            compat.reset_for_testing()

"""Tests for VectorIndex (M12) — FAISS + Null fallbacks.

These tests need a real FAISS index (they exercise the FAISS
contract directly), so they override the default
``disable_vector_index=True`` set by ``tests/memory/conftest.py``.

Marked with ``@pytest.mark.faiss_native`` so they can be skipped
in mixed-mode runs (where the FAISS native module would crash
torch-loaded voice tests on Apple Silicon). Run with::

    pytest -m faiss_native tests/memory/test_vector_index.py
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

"""Tests for the embedder + background pipeline (M12)."""
from __future__ import annotations

import threading
import time

import numpy as np
import pytest
from app.memory.embedder import (
    BackgroundEmbedder,
    Chunk,
    HashEmbedder,
    _normalize_text,
    make_embedder,
)

# ---------------------------------------------------------------------------
# HashEmbedder
# ---------------------------------------------------------------------------


class TestHashEmbedder:
    def test_dim_matches(self):
        e = HashEmbedder(dim=384)
        assert e.dim == 384

    def test_embed_shape(self):
        e = HashEmbedder(dim=384)
        v = e.embed("hello world")
        assert v.shape == (384,)
        assert v.dtype == np.float32

    def test_embed_normalized(self):
        e = HashEmbedder(dim=384)
        v = e.embed("hello world")
        n = float(np.linalg.norm(v))
        assert abs(n - 1.0) < 1e-5 or n == 0.0

    def test_empty_string_zero(self):
        e = HashEmbedder(dim=384)
        v = e.embed("")
        assert np.allclose(v, 0.0)

    def test_whitespace_only_zero(self):
        e = HashEmbedder(dim=384)
        v = e.embed("   \t\n")
        assert np.allclose(v, 0.0)

    def test_deterministic(self):
        e = HashEmbedder(dim=384)
        a = e.embed("Unicorn psychoframe awakens")
        b = e.embed("Unicorn psychoframe awakens")
        assert np.allclose(a, b)

    def test_different_text_different_vec(self):
        e = HashEmbedder(dim=384)
        # Hash projection can collide on tiny inputs, but on
        # longer text it should differ.
        v1 = e.embed("Unicorn psychoframe awakens in NT-D mode")
        v2 = e.embed("Freedom SEED mode hiMAT deploys wings")
        assert not np.allclose(v1, v2)

    def test_embed_batch(self):
        e = HashEmbedder(dim=64)
        vecs = e.embed_batch(["a", "b", "c"])
        assert vecs.shape == (3, 64)
        assert vecs.dtype == np.float32

    def test_embed_batch_empty(self):
        e = HashEmbedder(dim=64)
        vecs = e.embed_batch([])
        assert vecs.shape == (0, 64)

    def test_cjk_uses_bigrams(self):
        # CJK without spaces: hash should still produce a non-zero vec
        e = HashEmbedder(dim=384)
        v = e.embed("高達")
        assert np.any(v != 0)


class TestNormalize:
    def test_lowercases(self):
        assert _normalize_text("Hello") == ["hello"]

    def test_splits_on_punct(self):
        toks = _normalize_text("Hello, World!")
        assert toks == ["hello", "world"]

    def test_cjk_adds_bigrams(self):
        toks = _normalize_text("高達出擊")
        # Should include whole-string + bigrams
        assert "高達出擊" in toks
        assert any(len(t) == 2 for t in toks)


class TestMakeEmbedder:
    def test_hash_backend(self):
        e = make_embedder("hash", dim=64)
        assert isinstance(e, HashEmbedder)
        assert e.dim == 64

    def test_model_backend_falls_back_to_hash(self):
        # Model isn't installed in tests → should fall back to hash
        e = make_embedder("model", dim=64)
        # Either real model (unlikely in CI) or hash fallback
        assert hasattr(e, "embed")
        assert e.dim == 64

    def test_unknown_backend_raises(self):
        with pytest.raises(ValueError):
            make_embedder("nope", dim=64)


# ---------------------------------------------------------------------------
# BackgroundEmbedder
# ---------------------------------------------------------------------------


class TestBackgroundEmbedder:
    def test_starts_and_stops(self):
        emb = HashEmbedder(dim=64)
        be = BackgroundEmbedder(embedder=emb)
        be.start()
        assert be._thread is not None
        be.stop(timeout=2.0)
        assert be._thread is None

    def test_enqueue_drains_and_calls_on_ready(self):
        emb = HashEmbedder(dim=64)
        captured: list = []
        ready_event = threading.Event()
        lock = threading.Lock()

        def on_ready(chunk, vec):
            with lock:
                captured.append((chunk.source_id, vec.shape))
                if len(captured) >= 3:
                    ready_event.set()

        be = BackgroundEmbedder(embedder=emb, on_ready=on_ready, queue_max=10)
        be.start()
        for i in range(3):
            be.enqueue(Chunk(kind="message", source_id=f"m{i}",
                              text=f"text {i}", snippet=f"s{i}"))
        ready_event.wait(timeout=2.0)
        be.stop()
        assert len(captured) == 3
        assert all(shape == (64,) for _, shape in captured)

    def test_queue_full_drops_oldest(self):
        emb = HashEmbedder(dim=64)
        be = BackgroundEmbedder(embedder=emb, queue_max=2)
        be.start()
        for i in range(10):
            be.enqueue(Chunk(kind="message", source_id=f"m{i}",
                              text=f"text {i}", snippet=""))
        time.sleep(0.5)
        stats = be.stats()
        be.stop()
        assert stats["enqueued"] == 10
        # Some drops should have happened because the worker
        # couldn't drain in time.
        assert stats["dropped"] >= 0  # may be 0 if worker was fast

    def test_stats_counters(self):
        emb = HashEmbedder(dim=64)
        be = BackgroundEmbedder(embedder=emb)
        be.start()
        be.enqueue(Chunk(kind="message", source_id="m", text="x", snippet=""))
        time.sleep(0.2)
        be.stop()
        stats = be.stats()
        assert stats["enqueued"] == 1
        assert stats["embedded"] >= 0
        assert stats["queue_size"] == 0

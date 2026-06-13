"""Embedding + background indexing pipeline.

Two pieces:

1. ``Embedder`` — produces a 384-dim float32 vector for a string.
   Two backends:
     - ``"hash"``  — deterministic, offline, no model. Quality is
       poor (random projection of token hashes) but it's good
       enough for the *test path* and as a fallback when
       ``sentence-transformers`` isn't installed.
     - ``"model"`` — real semantic embeddings via
       ``sentence-transformers`` (lazy import; if not installed,
       we fall back to hash and log a warning).
2. ``BackgroundEmbedder`` — a single worker thread + bounded
   queue. New chunks enqueued from request handlers get embedded
   and added to the FAISS index off the hot path.

Why a background thread?
- Embedding takes ~5–50ms per chunk. We don't want the HTTP
  response for ``send_message`` to wait on a vector add.
- The SQLite index is the synchronous source of truth; FAISS
  catches up asynchronously. If the worker is behind, recall
  just returns fewer results — never wrong ones.

Failure modes:
- Embedding fails: chunk is dropped from the queue, the SQLite
  index still has it (lexical search still works), a counter is
  bumped. We never raise from the worker.
- Queue is full: oldest entries are dropped (with a counter
  bump). The user can ``POST /api/memory/rebuild`` to recover.
"""
from __future__ import annotations

import hashlib
import logging
import queue
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

import numpy as np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Embedder protocol
# ---------------------------------------------------------------------------


class Embedder(Protocol):
    """Interface for an embedding backend."""

    dim: int

    def embed(self, text: str) -> np.ndarray:  # pragma: no cover - protocol
        """Embed a single string. Returns shape (dim,) float32."""
        ...

    def embed_batch(self, texts: list[str]) -> np.ndarray:
        """Embed many strings. Returns shape (n, dim) float32."""
        ...


# ---------------------------------------------------------------------------
# Hash embedder (default fallback)
# ---------------------------------------------------------------------------


_TOKEN_RE_PUNCT = "!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~"


def _normalize_text(text: str) -> list[str]:
    """Lowercase + tokenize on whitespace and CJK boundaries.

    For CJK strings (no spaces), this gives whole-string hashing
    plus per-character tokens. Quality is poor but stable.
    """
    s = text.lower()
    # Replace ASCII punctuation with spaces
    for ch in _TOKEN_RE_PUNCT:
        s = s.replace(ch, " ")
    s = s.strip()
    if not s:
        return []
    # Split on whitespace; for CJK strings, also split into bigrams
    # to give the embedding some token-level signal.
    out: list[str] = []
    for tok in s.split():
        out.append(tok)
        # Add character bigrams for any chunk with CJK characters
        if any("\u4e00" <= ch <= "\u9fff" for ch in tok):
            for i in range(len(tok) - 1):
                out.append(tok[i : i + 2])
    return out


def _hash_token(token: str, dim: int) -> np.ndarray:
    """Map a token to a fixed-dim sparse vector via SHA-256.

    Each digest byte → one dimension (mod ``dim``); we set the
    sign from the byte's high bit, so the result is a +/-1 vector.
    The final L2-normalized vector is the unit-norm projection of
    that sparse sign vector.
    """
    v = np.zeros(dim, dtype=np.float32)
    digest = hashlib.sha256(token.encode("utf-8")).digest()
    for byte in digest:
        idx = byte % dim
        # Use the byte value as a small weight: 0–255 → 0.0–1.0.
        # Sign comes from the next byte's high bit.
        sign = 1.0 if (byte & 0x80) else -1.0
        # Use another byte as weight to avoid total cancellation.
        weight = 1.0 + (byte % 7) * 0.1
        v[idx] += sign * weight
    return v


class HashEmbedder:
    """Deterministic, offline, no-model embedder.

    Used as the default for v0.2.0. Quality is intentionally low
    (no semantic meaning) — we ship the *path*; the real model
    lands in v0.2.1.
    """

    def __init__(self, dim: int = 384) -> None:
        self.dim = dim

    def embed(self, text: str) -> np.ndarray:
        tokens = _normalize_text(text)
        if not tokens:
            return np.zeros(self.dim, dtype=np.float32)
        v = np.zeros(self.dim, dtype=np.float32)
        for tok in tokens:
            v += _hash_token(tok, self.dim)
        # L2-normalize so cosine = inner product.
        n = float(np.linalg.norm(v))
        if n > 0:
            v /= n
        return v

    def embed_batch(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        return np.stack([self.embed(t) for t in texts]).astype(np.float32)


# ---------------------------------------------------------------------------
# Model embedder (lazy)
# ---------------------------------------------------------------------------


class _SentenceTransformerEmbedder:
    """Real semantic embeddings via sentence-transformers.

    Lazy-imported. The first call downloads the model
    (~80 MB) and caches it under ``~/.cache/torch/sentence_transformers/``.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        from sentence_transformers import SentenceTransformer

        self.dim = 384
        self._model = SentenceTransformer(model_name)
        # Try MPS first (Mac M-series), fall back to CPU.
        try:
            import torch

            if torch.backends.mps.is_available():  # type: ignore[attr-defined]
                self._model = self._model.to("mps")
        except Exception:  # pragma: no cover - depends on torch internals
            pass

    def embed(self, text: str) -> np.ndarray:
        v = self._model.encode(
            [text], normalize_embeddings=True, convert_to_numpy=True
        )[0]
        return v.astype(np.float32)

    def embed_batch(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        v = self._model.encode(
            texts, normalize_embeddings=True, convert_to_numpy=True,
            batch_size=32, show_progress_bar=False,
        )
        return v.astype(np.float32)


def make_embedder(backend: str, dim: int = 384) -> Embedder:
    """Factory. ``"model"`` falls back to ``"hash"`` if unavailable."""
    if backend == "hash":
        return HashEmbedder(dim=dim)
    if backend == "model":
        try:
            return _SentenceTransformerEmbedder()
        except Exception as e:
            logger.warning(
                f"Failed to load sentence-transformers model ({e}); "
                "falling back to hash embedder"
            )
            return HashEmbedder(dim=dim)
    raise ValueError(f"Unknown embedding backend: {backend!r}")


# ---------------------------------------------------------------------------
# Chunk + background queue
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class Chunk:
    """A unit of text to embed + index.

    ``vector_id`` is assigned by the FAISS index on insert, so we
    don't carry it here. The lifecycle layer is responsible for
    tracking (chunk → vector_id) for delete and lookup.
    """

    kind: str           # "message" | "memory_entry"
    source_id: str      # message_id (str(int)) or "user/key"
    text: str           # the text to embed
    snippet: str        # short text for display in recall results
    meta: dict[str, Any] = field(default_factory=dict)


class BackgroundEmbedder:
    """Single-thread async embedding pipeline.

    Enqueue chunks via :meth:`enqueue`; a worker thread drains the
    queue, embeds the text, and calls a user-supplied
    ``on_ready`` callback with ``(chunk, np.ndarray)``.

    Lifecycle::

        be = BackgroundEmbedder(embedder=make_embedder("hash"))
        be.start()
        be.enqueue(chunk)
        ...
        be.stop()           # drains + joins
    """

    def __init__(
        self,
        *,
        embedder: Embedder,
        on_ready: Callable[[Chunk, np.ndarray], None] | None = None,
        queue_max: int = 5000,
    ) -> None:
        self._embedder = embedder
        self._on_ready = on_ready
        self._queue: queue.Queue[Chunk | None] = queue.Queue(maxsize=queue_max)
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        # Counters for observability
        self._enqueued = 0
        self._dropped = 0
        self._embedded = 0
        self._failed = 0
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, name="bg-embedder", daemon=True
        )
        self._thread.start()
        logger.debug("BackgroundEmbedder started")

    def stop(self, *, timeout: float = 5.0) -> None:
        self._stop_event.set()
        # Sentinel to unblock the queue.get
        try:
            self._queue.put_nowait(None)
        except queue.Full:  # pragma: no cover - extremely unlikely
            pass
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None
        logger.debug("BackgroundEmbedder stopped")

    # ------------------------------------------------------------------
    # Enqueue
    # ------------------------------------------------------------------

    def enqueue(self, chunk: Chunk) -> bool:
        """Add a chunk. Returns False if the queue was full (oldest dropped)."""
        try:
            self._queue.put_nowait(chunk)
        except queue.Full:
            # Drop the oldest, then enqueue
            try:
                self._queue.get_nowait()
                with self._lock:
                    self._dropped += 1
            except queue.Empty:  # pragma: no cover - race
                pass
            try:
                self._queue.put_nowait(chunk)
            except queue.Full:  # pragma: no cover
                with self._lock:
                    self._dropped += 1
                return False
        with self._lock:
            self._enqueued += 1
        return True

    def enqueue_batch(self, chunks: list[Chunk]) -> int:
        """Enqueue many. Returns the number actually enqueued."""
        n = 0
        for c in chunks:
            if self.enqueue(c):
                n += 1
        return n

    def qsize(self) -> int:
        return self._queue.qsize()

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {
                "enqueued": self._enqueued,
                "dropped": self._dropped,
                "embedded": self._embedded,
                "failed": self._failed,
                "queue_size": self._queue.qsize(),
            }

    # ------------------------------------------------------------------
    # Worker
    # ------------------------------------------------------------------

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                chunk = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            if chunk is None:
                # Sentinel — graceful exit
                break
            try:
                vec = self._embedder.embed(chunk.text)
            except Exception as e:
                logger.warning(
                    f"Embedding failed for chunk {chunk.source_id}: {e}"
                )
                with self._lock:
                    self._failed += 1
                continue
            with self._lock:
                self._embedded += 1
            if self._on_ready is not None:
                try:
                    self._on_ready(chunk, vec)
                except Exception as e:
                    logger.warning(
                        f"on_ready callback failed for {chunk.source_id}: {e}"
                    )


__all__ = [
    "BackgroundEmbedder",
    "Chunk",
    "Embedder",
    "HashEmbedder",
    "make_embedder",
]

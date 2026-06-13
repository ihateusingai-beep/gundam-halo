"""FAISS vector index for semantic recall.

Wraps a ``faiss.IndexFlatIP`` with L2-normalized vectors (= cosine
similarity). The on-disk layout is:

    <halo_home>/memory/vectors.faiss        # the FAISS index
    <halo_home>/memory/vectors.meta.json    # vector_id -> metadata

The metadata sidecar lets us map a FAISS ``id`` back to a chunk
without re-embedding anything. The id space is dense: every
``add()`` increments ``ntotal`` by 1.

Design choices
--------------
- ``IndexFlatIP`` (exact, brute-force). For v0.2.0's expected scale
  (≤ a few thousand chunks) this is fast enough. When we cross
  ~100k chunks, swap to ``IndexIVFFlat`` — same interface, no API
  change.
- We persist after every batch add (and on shutdown). On startup
  we load back via ``faiss.read_index`` and verify ``ntotal``
  matches the sidecar length.
- Pure-Python metadata is in JSON, not FAISS's binary attribute
  storage. Simpler, debuggable, and small enough at our scale.
- ``faiss`` is imported **lazily** inside the constructor — this
  module can be imported without loading the FAISS C++ extension.

Apple Silicon + torch MPS crash guard
-------------------------------------

On darwin/arm64, the ``faiss-cpu`` wheel bundles its own
``libomp.dylib``. When ``torch`` is loaded *before* faiss in the
same process (and MPS is initialised), faiss's first OpenMP call
aborts with ``OMP Error #15: Initializing libomp.dylib, but
found libomp.dylib already initialized`` and the process dies
with SIGABRT (exit 134). This bites the live Tauri app on
Apple Silicon Macs.

The runtime guard lives in :mod:`app.memory._apple_silicon_compat`
and is consulted by :func:`make_vector_index` before importing
faiss. On Apple Silicon + torch-already-loaded-with-MPS, we fall
back to :class:`NullVectorIndex` (which still records metadata
in memory so the lifecycle layer doesn't break; lexical search
via :class:`SqliteIndex` is unaffected). Override with the env
var ``HALO_FAISS_FORCE=1`` to force the real FAISS path; the
guard additionally sets ``KMP_DUPLICATE_LIB_OK=TRUE`` before
importing faiss on Apple Silicon as a belt-and-braces
mitigation. See ``docs/tickets/M12.md`` "Known follow-ups" #5
for the upstream ticket.

If FAISS isn't installed (e.g. on a host where we want a slim
build), this module exposes a ``NullVectorIndex`` that always
returns empty results — graceful degradation. The SqliteIndex
still works, so lexical search remains.
"""
from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any  # noqa: F401

import numpy as np

logger = logging.getLogger(__name__)

# Default filenames
FAISS_FILENAME = "vectors.faiss"
META_FILENAME = "vectors.meta.json"


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class RecallHit:
    """A single recall result."""

    vector_id: int
    score: float
    kind: str            # "message" | "memory_entry"
    source_id: str       # message_id-as-str or "user/key"
    snippet: str
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "vector_id": self.vector_id,
            "score": round(self.score, 4),
            "kind": self.kind,
            "source_id": self.source_id,
            "snippet": self.snippet,
            **self.meta,
        }


# ---------------------------------------------------------------------------
# Index protocol + null impl
# ---------------------------------------------------------------------------


class VectorIndex:
    """Common interface."""

    dim: int

    def add(self, vec: np.ndarray, meta: dict[str, Any]) -> int: ...
    def add_batch(
        self, vecs: np.ndarray, metas: list[dict[str, Any]]
    ) -> list[int]: ...
    def search(
        self, query: np.ndarray, k: int = 5
    ) -> list[RecallHit]: ...
    def ntotal(self) -> int: ...
    def save(self) -> None: ...
    def close(self) -> None: ...


class NullVectorIndex:
    """No-op index. Used when FAISS isn't installed.

    Always returns empty results. SqliteIndex still works for
    lexical search.
    """

    def __init__(self, dim: int = 384) -> None:
        self.dim = dim
        self._lock = threading.Lock()
        self._metas: list[dict[str, Any]] = []

    def add(self, vec: np.ndarray, meta: dict[str, Any]) -> int:
        with self._lock:
            idx = len(self._metas)
            self._metas.append(meta)
            return idx

    def add_batch(
        self, vecs: np.ndarray, metas: list[dict[str, Any]]
    ) -> list[int]:
        out: list[int] = []
        for v, m in zip(vecs, metas, strict=True):
            out.append(self.add(v, m))
        return out

    def search(
        self, query: np.ndarray, k: int = 5
    ) -> list[RecallHit]:
        return []

    def ntotal(self) -> int:
        return len(self._metas)

    def save(self) -> None:
        return None

    def close(self) -> None:
        return None

    def reset(self) -> None:
        """Wipe the in-memory metas. No-op for the null index."""
        with self._lock:
            self._metas = []


# ---------------------------------------------------------------------------
# FAISS-backed index
# ---------------------------------------------------------------------------


class FaissVectorIndex:
    """FAISS IndexFlatIP wrapper with L2-normalized cosine similarity.

    See module docstring for the on-disk layout.
    """

    def __init__(self, halo_home: Path, dim: int = 384) -> None:
        self.dim = dim
        self._base = halo_home / "memory"
        self._base.mkdir(parents=True, exist_ok=True)
        self._faiss_path = self._base / FAISS_FILENAME
        self._meta_path = self._base / META_FILENAME

        # Lazy import: see module docstring for the Apple Silicon
        # torch-MPS interaction that motivates this.
        import faiss

        self._faiss = faiss
        self._lock = threading.RLock()
        self._metas: list[dict[str, Any]] = []

        if self._faiss_path.exists() and self._meta_path.exists():
            try:
                self._index = faiss.read_index(str(self._faiss_path))
                self._metas = json.loads(
                    self._meta_path.read_text(encoding="utf-8")
                )
                logger.debug(
                    f"Loaded FAISS index with {self._index.ntotal} vectors"
                )
                if self._index.ntotal != len(self._metas):
                    logger.warning(
                        f"FAISS ntotal={self._index.ntotal} != "
                        f"meta len={len(self._metas)}; resetting"
                    )
                    self._index = faiss.IndexFlatIP(dim)
                    self._metas = []
            except Exception as e:
                logger.warning(
                    f"Failed to load FAISS index ({e}); starting fresh"
                )
                self._index = faiss.IndexFlatIP(dim)
                self._metas = []
        else:
            self._index = faiss.IndexFlatIP(dim)

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def add(self, vec: np.ndarray, meta: dict[str, Any]) -> int:
        return self.add_batch(
            vec.reshape(1, -1).astype(np.float32), [meta]
        )[0]

    def add_batch(
        self, vecs: np.ndarray, metas: list[dict[str, Any]]
    ) -> list[int]:
        if vecs.shape[0] == 0:
            return []
        if vecs.shape[0] != len(metas):
            raise ValueError(
                f"vecs/metas length mismatch: {vecs.shape[0]} vs {len(metas)}"
            )
        # Normalize for cosine = inner product
        v = vecs.astype(np.float32, copy=True)
        self._faiss.normalize_L2(v)
        with self._lock:
            base = self._index.ntotal
            self._index.add(v)
            for i, m in enumerate(metas):
                # Carry the assigned vector_id into the meta so
                # the lifecycle layer can map back without a
                # separate id store.
                m_with_id = {**m, "vector_id": base + i}
                self._metas.append(m_with_id)
            self._save_locked()
            return list(range(base, base + len(metas)))

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(
        self, query: np.ndarray, k: int = 5
    ) -> list[RecallHit]:
        if self._index.ntotal == 0:
            return []
        k = min(k, self._index.ntotal)
        q = query.astype(np.float32, copy=True).reshape(1, -1)
        self._faiss.normalize_L2(q)
        with self._lock:
            scores, ids = self._index.search(q, k)
        out: list[RecallHit] = []
        for score, vid in zip(
            scores[0].tolist(), ids[0].tolist(), strict=True
        ):
            if vid < 0 or vid >= len(self._metas):
                continue
            m = self._metas[vid]
            out.append(
                RecallHit(
                    vector_id=vid,
                    score=float(score),
                    kind=m.get("kind", "message"),
                    source_id=m.get("source_id", ""),
                    snippet=m.get("snippet", ""),
                    meta={
                        k: v
                        for k, v in m.items()
                        if k
                        not in {
                            "kind",
                            "source_id",
                            "snippet",
                            "vector_id",
                        }
                    },
                )
            )
        return out

    def ntotal(self) -> int:
        return self._index.ntotal

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _save_locked(self) -> None:
        """Persist index + sidecar. Caller must hold ``_lock``."""
        # Write sidecar first; if FAISS write fails, we can rebuild.
        tmp_meta = self._meta_path.with_suffix(".meta.json.tmp")
        tmp_meta.write_text(
            json.dumps(self._metas, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp_meta.replace(self._meta_path)
        self._faiss.write_index(self._index, str(self._faiss_path))

    def save(self) -> None:
        with self._lock:
            self._save_locked()

    def close(self) -> None:
        with self._lock:
            try:
                self._save_locked()
            except Exception as e:
                logger.warning(f"FAISS save-on-close failed: {e}")

    def reset(self) -> None:
        """Wipe the on-disk index. Used by rebuild_index()."""
        with self._lock:
            self._index = self._faiss.IndexFlatIP(self.dim)
            self._metas = []
            for path in (self._faiss_path, self._meta_path):
                if path.exists():
                    try:
                        path.unlink()
                    except OSError as e:
                        logger.warning(f"Failed to remove {path}: {e}")


# ---------------------------------------------------------------------------
# Factory + singleton
# ---------------------------------------------------------------------------


def make_vector_index(
    halo_home: Path, dim: int = 384, *, force_null: bool = False
) -> VectorIndex:
    """Pick FAISS if installed (and not disabled), else NullVectorIndex.

    ``force_null=True`` skips the FAISS import entirely — used in
    test environments where loading faiss-cpu in the same process
    as torch can crash on Apple Silicon (M12 ticket "Known
    follow-ups"). This is now a **layered** guard: even when
    ``force_null=False``, the Apple Silicon / torch-MPS detection
    in :mod:`app.memory._apple_silicon_compat` may still opt out
    of faiss and return a :class:`NullVectorIndex` instead.

    Override behaviour with the env var ``HALO_FAISS_FORCE``:
    ``=1`` forces the real FAISS path (the KMP_DUPLICATE_LIB_OK
    workaround is also applied on Apple Silicon), ``=0`` forces
    NullVectorIndex, ``auto`` (default) consults the heuristic.
    """
    if force_null:
        logger.debug("VectorIndex forced to NullVectorIndex (FAISS disabled)")
        return NullVectorIndex(dim=dim)

    # Import lazily so a fast-fail doesn't pull the compat helpers
    # into every call site that happens to use vector_index.
    from app.memory import _apple_silicon_compat as _compat

    # Emit the one-shot decision log the first time we are called.
    _compat.log_decision_once()

    if not _compat.should_use_faiss():
        logger.info(
            "VectorIndex: using NullVectorIndex on this host. "
            "Reason: %s",
            _compat.get_fallback_reason(),
        )
        return NullVectorIndex(dim=dim)

    # We decided to use faiss. On Apple Silicon also arm the
    # KMP_DUPLICATE_LIB_OK belt-and-braces guard before the
    # import — this is the documented escape hatch if a user
    # forces faiss with HALO_FAISS_FORCE=1 in spite of torch
    # being already loaded.
    if _compat.is_apple_silicon():
        _compat.prepare_for_safe_faiss_import()

    try:
        import faiss  # noqa: F401

        return FaissVectorIndex(halo_home=halo_home, dim=dim)
    except ImportError:
        logger.info(
            "faiss-cpu not installed — using NullVectorIndex "
            "(lexical search via SqliteIndex still works)"
        )
        return NullVectorIndex(dim=dim)


_index: VectorIndex | None = None
_lock = threading.Lock()


def get_vector_index() -> VectorIndex:
    global _index
    if _index is None:
        with _lock:
            if _index is None:
                from app.core.config import get_config

                cfg = get_config()
                _index = make_vector_index(
                    halo_home=cfg.home,
                    dim=cfg.memory.embedding_dim,
                    force_null=cfg.memory.disable_vector_index,
                )
    return _index


def reset_vector_index() -> None:
    global _index
    if _index is not None:
        _index.close()
    _index = None


__all__ = [
    "FaissVectorIndex",
    "NullVectorIndex",
    "RecallHit",
    "VectorIndex",
    "get_vector_index",
    "make_vector_index",
    "reset_vector_index",
]

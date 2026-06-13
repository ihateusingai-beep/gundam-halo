"""User memory + structured memory layer (M12).

This package owns:

- :mod:`app.memory.user_memory`  — per-user key/value notes (file-backed)
- :mod:`app.memory.sqlite_index` — queryable index over sessions/messages
- :mod:`app.memory.vector_index`  — FAISS cosine recall (or null fallback)
- :mod:`app.memory.embedder`      — async embedding pipeline
- :mod:`app.memory.lifecycle`     — hooks that keep indices in sync

The JSON / MD files on disk are the source of truth. The SQLite
DB and FAISS index are derived, rebuildable indices.
"""
from app.memory.user_memory import (
    MemoryEntry,
    UserMemoryStore,
    get_user_memory_store,
    reset_user_memory_store,
    slugify_key,
    user_key_for,
)

__all__ = [
    "MemoryEntry",
    "UserMemoryStore",
    "get_user_memory_store",
    "reset_user_memory_store",
    "slugify_key",
    "user_key_for",
]

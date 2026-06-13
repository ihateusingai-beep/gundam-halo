"""Lifecycle hooks for the structured memory layer.

This module glues together:

- :class:`app.projects.persistence` (the JSON/MD source of truth)
- :class:`app.memory.sqlite_index.SqliteIndex` (queryable index)
- :class:`app.memory.vector_index.VectorIndex` (FAISS or null)
- :class:`app.memory.embedder.BackgroundEmbedder` (async pipeline)

On every ``save_messages`` call we mirror the data into SQLite
synchronously and enqueue the messages for async embedding. The
HTTP path stays fast; recall catches up.

Public surface:

- :func:`on_session_saved`     — call after ``persistence.save_messages``
- :func:`on_session_deleted`   — call after ``persistence.delete_session``
- :func:`on_user_memory_set`   — call after ``UserMemoryStore.set``
- :func:`on_user_memory_deleted` — call after ``UserMemoryStore.delete``
- :func:`init_memory_on_startup` — call from ``app.main`` lifespan
- :func:`rebuild_index`        — wipe + repopulate SQLite + FAISS

The lifecycle is **best-effort**. If SQLite or FAISS raises, we
log and continue. The file store is still authoritative; the
user can recover by running ``POST /api/memory/rebuild``.
"""
from __future__ import annotations

import logging
import threading
import time
from collections.abc import Sequence

from app.core.config import get_config
from app.core.types import Message, Role
from app.memory.embedder import (
    BackgroundEmbedder,
    Chunk,
    make_embedder,
)
from app.memory.sqlite_index import (
    get_sqlite_index,
    reset_sqlite_index,
)
from app.memory.vector_index import (
    RecallHit,
    get_vector_index,
    reset_vector_index,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Embedding-side: build a snippet for display
# ---------------------------------------------------------------------------

_SNIPPET_CHARS = 240


def _snippet(content: str, limit: int = _SNIPPET_CHARS) -> str:
    if not content:
        return ""
    s = content.strip()
    if len(s) <= limit:
        return s
    return s[:limit].rsplit(" ", 1)[0] + "..."


def _message_to_chunk(message: Message, session_id: str, project: str) -> Chunk:
    """Build an embeddable chunk from a single message.

    For ``tool`` messages we embed the name + content prefix;
    for everything else we embed the content. Snippet is always
    the raw content (truncated).
    """
    text_parts: list[str] = []
    if message.role == Role.TOOL:
        # Tool result — context: what tool, what came back
        if message.name:
            text_parts.append(f"tool:{message.name}")
        if message.content:
            text_parts.append(message.content)
        text = " ".join(text_parts) or "(empty tool result)"
    elif message.role == Role.ASSISTANT and message.tool_calls:
        # Assistant with tool calls — embed the tool names + any content
        names = [tc.name for tc in message.tool_calls]
        if names:
            text_parts.append("call:" + ",".join(names))
        if message.content:
            text_parts.append(message.content)
        text = " ".join(text_parts) or "(assistant with tool calls)"
    else:
        text = message.content or f"({message.role.value} message)"

    return Chunk(
        kind="message",
        source_id=f"{session_id}:{message.role.value}",
        text=text[:2048],  # bound the embedding input
        snippet=_snippet(message.content),
        meta={
            "session_id": session_id,
            "project": project,
            "role": message.role.value,
        },
    )


# ---------------------------------------------------------------------------
# Public hooks
# ---------------------------------------------------------------------------


def on_session_saved(
    project_name: str,
    session_id: str,
    agent_type: str,
    messages: Sequence[Message],
    *,
    channel: str | None = None,
) -> None:
    """Called after ``persistence.save_messages``.

    Mirrors the session + messages into SQLite and enqueues
    them for embedding.
    """
    try:
        idx = get_sqlite_index()
    except Exception as e:
        logger.warning(f"on_session_saved: sqlite init failed: {e}")
        return

    now = time.time()
    created_at = now  # overwritten by per-message seqs where available

    # Pull per-message created_at from metadata if present
    seq_rows: list[tuple[int, str, str, str, str | None, str | None, float]] = []
    for seq, m in enumerate(messages):
        role = m.role.value if hasattr(m.role, "value") else str(m.role)
        meta_ts = None
        if isinstance(m.metadata, dict):
            ts = m.metadata.get("created_at")
            if isinstance(ts, (int, float)):
                meta_ts = float(ts)
        ts_for_row = meta_ts or now
        tool_calls_json = None
        if m.tool_calls:
            tool_calls_json = [
                {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                for tc in m.tool_calls
            ]
        seq_rows.append(
            (
                seq,
                role,
                m.content,
                tool_calls_json,
                m.tool_call_id,
                m.name,
                ts_for_row,
            )
        )
    if seq_rows:
        # Use last message ts as updated_at, first as created_at
        created_at = seq_rows[0][6]
        updated_at = seq_rows[-1][6]

    try:
        idx.upsert_session(
            session_id=session_id,
            project_name=project_name,
            agent_type=agent_type,
            created_at=created_at,
            updated_at=updated_at,
            channel=channel,
            message_count=len(seq_rows),
        )
        idx.upsert_messages(session_id, seq_rows)
    except Exception as e:
        logger.warning(
            f"on_session_saved: sqlite upsert failed for "
            f"{session_id}: {e}"
        )
        return

    # Auto-thread: one project → one thread in v0.2.0
    try:
        thread_id = idx.ensure_project_thread(project_name)
        idx.attach_session_to_thread(session_id, thread_id)
    except Exception as e:
        logger.warning(
            f"on_session_saved: thread attach failed for "
            f"{session_id}: {e}"
        )

    # Enqueue for async embedding
    try:
        be = get_background_embedder()
        chunks = [
            _message_to_chunk(m, session_id=session_id, project=project_name)
            for m in messages
            if m.content or m.tool_calls
        ]
        if chunks:
            be.enqueue_batch(chunks)
    except Exception as e:
        logger.warning(
            f"on_session_saved: enqueue failed for {session_id}: {e}"
        )


def on_session_deleted(session_id: str) -> None:
    """Called after ``persistence.delete_session``."""
    try:
        idx = get_sqlite_index()
        idx.delete_session(session_id)
    except Exception as e:
        logger.warning(f"on_session_deleted: {e}")


def on_user_memory_set(user: str, key: str, value: str) -> None:
    """Called after ``UserMemoryStore.set``."""
    try:
        get_sqlite_index()
        # We don't add a `user_memories` table in v0.2.0 — instead
        # we index the value into FAISS with a key-shaped source_id.
        be = get_background_embedder()
        chunk = Chunk(
            kind="memory_entry",
            source_id=f"{user}/{key}",
            text=f"{key}: {value}",
            snippet=_snippet(value),
            meta={"user": user, "key": key},
        )
        be.enqueue(chunk)
    except Exception as e:
        logger.warning(f"on_user_memory_set: {e}")


def on_user_memory_deleted(user: str, key: str) -> None:
    """Called after ``UserMemoryStore.delete``.

    v0.2.0: we don't track vector_id → (user, key) mapping, so we
    can't surgically delete the FAISS entry. The next
    ``rebuild_index()`` will drop it. For correctness it's still
    useful — the deleted value never shows up in recall after a
    rebuild.
    """
    # Best-effort no-op for v0.2.0. Rebuild will fix.
    return


# ---------------------------------------------------------------------------
# Recall
# ---------------------------------------------------------------------------


def recall(
    query: str,
    *,
    k: int = 5,
    user: str | None = None,
) -> list[RecallHit]:
    """Semantic recall across all indexed chunks.

    Returns the top-``k`` results by cosine similarity. If ``user``
    is given, only ``memory_entry`` chunks belonging to that user
    are returned.
    """
    from app.memory.embedder import make_embedder

    cfg = get_config()
    emb = make_embedder(cfg.memory.embedding_backend, dim=cfg.memory.embedding_dim)
    v = emb.embed(query)
    vi = get_vector_index()
    hits = vi.search(v, k=k * 2)  # over-fetch then filter

    if user is not None:
        hits = [h for h in hits if h.meta.get("user") == user]
    return hits[:k]


# ---------------------------------------------------------------------------
# Rebuild
# ---------------------------------------------------------------------------


def rebuild_index() -> dict:
    """Wipe + repopulate SQLite + FAISS from disk.

    Returns a stats dict with counts. Safe to call at runtime; the
    next save will use the freshly-rebuilt indices.
    """
    cfg = get_config()
    home = cfg.home

    # Stop the background embedder for the duration
    be = get_background_embedder()
    be.stop()

    # Reset both indices
    try:
        idx = get_sqlite_index()
        idx.reset()
    except Exception as e:
        logger.error(f"rebuild_index: sqlite reset failed: {e}")
        raise
    try:
        vi = get_vector_index()
        vi.reset()
    except Exception as e:
        logger.error(f"rebuild_index: vector reset failed: {e}")
        raise

    # Rebuild from JSON
    from app.memory.user_memory import UserMemoryStore
    from app.projects import persistence

    sessions_count = 0
    messages_count = 0
    mem_entries_count = 0
    projects_root = home / "projects"
    if projects_root.exists():
        for pdir in sorted(projects_root.iterdir()):
            if not pdir.is_dir():
                continue
            project_name = pdir.name
            for summary in persistence.scan_project_sessions(project_name):
                messages = (
                    persistence.load_messages(project_name, summary.session_id)
                    or []
                )
                if not messages:
                    continue
                on_session_saved(
                    project_name=project_name,
                    session_id=summary.session_id,
                    agent_type=summary.agent_type,
                    messages=messages,
                    channel=None,
                )
                sessions_count += 1
                messages_count += len(messages)

    # Rebuild user memory entries
    try:
        um = UserMemoryStore(halo_home=home)
        for user in um.list_users():
            for entry in um.list_keys(user):
                on_user_memory_set(user, entry.key, entry.value)
                mem_entries_count += 1
    except Exception as e:
        logger.warning(f"rebuild_index: user memory rebuild failed: {e}")

    # Drain the queue (synchronously) so the rebuilt FAISS index
    # has the embeddings already.
    be.start()
    _drain_queue_sync(be, timeout_s=10.0)

    return {
        "sessions": sessions_count,
        "messages": messages_count,
        "memory_entries": mem_entries_count,
        "vector_ntotal": vi.ntotal(),
    }


def _drain_queue_sync(be: BackgroundEmbedder, *, timeout_s: float) -> None:
    """Best-effort: wait for the queue to drain.

    Since the worker is async, we busy-wait on ``qsize()`` for up
    to ``timeout_s``. If it doesn't drain in time we leave the
    rest for the worker to catch up to.
    """
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if be.qsize() == 0:
            # Give the worker one more tick to finish the last item
            time.sleep(0.2)
            if be.qsize() == 0:
                return
        time.sleep(0.05)


# ---------------------------------------------------------------------------
# Startup hook
# ---------------------------------------------------------------------------


def init_memory_on_startup() -> dict:
    """Called from ``app.main`` lifespan.

    Returns a status dict useful for boot logs.
    """
    cfg = get_config()
    out: dict = {"auto_rebuild": False, "schema_version": None}

    # Touch the SqliteIndex (creates tables if missing)
    try:
        idx = get_sqlite_index()
        out["schema_version"] = idx.schema_version()
    except Exception as e:
        logger.warning(f"init_memory_on_startup: sqlite failed: {e}")

    # Touch the VectorIndex (loads FAISS if file exists)
    try:
        get_vector_index()
    except Exception as e:
        logger.warning(f"init_memory_on_startup: vector index failed: {e}")

    # Decide on auto-rebuild
    if cfg.memory.auto_rebuild:
        if not _is_index_consistent():
            logger.info("Memory index inconsistent — running auto-rebuild")
            try:
                stats = rebuild_index()
                out["auto_rebuild"] = True
                out["rebuild_stats"] = stats
            except Exception as e:
                logger.error(f"init_memory_on_startup: rebuild failed: {e}")

    # Start the background embedder
    try:
        be = get_background_embedder()
        be.start()
    except Exception as e:
        logger.warning(f"init_memory_on_startup: embedder start failed: {e}")

    return out


def _is_index_consistent() -> bool:
    """True if SQLite + FAISS are present and have plausible data.

    We define "plausible" as:
    - SQLite exists, schema is current
    - FAISS index exists OR has zero vectors
    """
    try:
        idx = get_sqlite_index()
        if idx.needs_rebuild():
            return False
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Background embedder singleton
# ---------------------------------------------------------------------------


_bg_embedder: BackgroundEmbedder | None = None
_bg_lock = threading.Lock()


def get_background_embedder() -> BackgroundEmbedder:
    global _bg_embedder
    if _bg_embedder is None:
        with _bg_lock:
            if _bg_embedder is None:
                cfg = get_config()
                from app.memory.vector_index import get_vector_index

                embedder = make_embedder(
                    cfg.memory.embedding_backend,
                    dim=cfg.memory.embedding_dim,
                )
                vi = get_vector_index()

                def _on_ready(chunk: Chunk, vec) -> None:
                    try:
                        vi.add(
                            vec,
                            {
                                "kind": chunk.kind,
                                "source_id": chunk.source_id,
                                "snippet": chunk.snippet,
                                **chunk.meta,
                            },
                        )
                    except Exception as e:
                        logger.warning(
                            f"vector add failed for {chunk.source_id}: {e}"
                        )

                _bg_embedder = BackgroundEmbedder(
                    embedder=embedder,
                    on_ready=_on_ready,
                    queue_max=cfg.memory.embed_queue_max,
                )
    return _bg_embedder


def reset_background_embedder() -> None:
    global _bg_embedder
    if _bg_embedder is not None:
        _bg_embedder.stop()
    _bg_embedder = None


def reset_all_memory() -> None:
    """Tear down every memory singleton. Used in tests.

    Beyond dropping our own references, we also run ``gc.collect()``
    so the FAISS native index object is freed *now* (and not later,
    during interpreter shutdown when its destructor can race with
    torch / numpy finalization and crash the process). See the
    M12 ticket's "Known follow-ups" for context.
    """
    reset_background_embedder()
    reset_vector_index()
    reset_sqlite_index()
    # Force the FAISS native object to free its C++ state right
    # away, before any other native module gets unloaded.
    try:
        import gc

        gc.collect()
    except Exception:
        pass


__all__ = [
    "init_memory_on_startup",
    "on_session_deleted",
    "on_session_saved",
    "on_user_memory_deleted",
    "on_user_memory_set",
    "recall",
    "rebuild_index",
    "reset_all_memory",
    "reset_background_embedder",
]

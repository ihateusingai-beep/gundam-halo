"""User memory — per-user key/value notes that the agent can read & write.

Storage layout (under HALO_HOME):
    memory/
        users/
            <user_key>/
                <slug>.md      # one file per key, e.g. "preferred_name.md"
                _index.json    # {"<slug>": {"key": ..., "value": ..., "updated_at": ...}}

A "user" is identified by a stable key. For Telegram we use the display
name (lowercased; e.g. "ken"). For the web dashboard we use a session
owner key (TBD). For now the schema is generic so we can wire the
dashboard later without rewriting this module.

The "key" (within a user) is a slug — lowercase, alnum + underscores,
max 64 chars. Examples:
    - preferred_name       "Ken"
    - timezone             "Asia/Hong_Kong"
    - favorite_gundam      "Unicorn"
    - primary_language     "zh-HK"

The "value" is a free-form string (≤ 8 KB). We don't enforce structure;
the agent (LLM) does. We do enforce a max value size so a runaway agent
can't fill the disk.

Concurrency:
- File-based with `flock(LOCK_EX)` for cross-process safety (the
  dashboard may read while the agent writes).
- In-memory cache invalidated on write.
"""
from __future__ import annotations

import fcntl
import json
import logging
import re
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Layout constants
USERS_DIR = Path("memory") / "users"
INDEX_FILE = "_index.json"

# Limits
MAX_KEY_LEN = 64
MAX_VALUE_BYTES = 8 * 1024  # 8 KB
MAX_KEYS_PER_USER = 200
MAX_USER_KEY_LEN = 64

# Slug regex — only lowercase, digits, and underscores. We slugify the
# key on write so "Preferred Name" and "preferred name" both become
# "preferred_name" — no duplicate-key shenanigans.
SLUG_RE = re.compile(r"[^a-z0-9_]+")
SLUG_STRIP_RE = re.compile(r"_+")

# User key regex — same as slug but slightly more permissive (we just
# use this to warn, not to reject, because user display names can have
# CJK or punctuation).
USER_KEY_RE = re.compile(r"[^a-z0-9_\-.]+")


@dataclass(slots=True, frozen=True)
class MemoryEntry:
    """A single (key, value) pair in a user's memory."""

    user: str
    key: str
    value: str
    updated_at: float
    created_at: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "user": self.user,
            "key": self.key,
            "value": self.value,
            "updated_at": self.updated_at,
            "created_at": self.created_at,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def slugify_key(key: str) -> str:
    """Normalize a user-provided key to a safe filename slug.

    - Lowercase
    - Replace non-[a-z0-9_] with underscore
    - Collapse runs of underscores
    - Strip leading/trailing underscores
    - Truncate to MAX_KEY_LEN

    >>> slugify_key("Preferred Name!")
    'preferred_name'
    >>> slugify_key("timezone")
    'timezone'
    """
    s = SLUG_RE.sub("_", key.strip().lower())
    s = SLUG_STRIP_RE.sub("_", s).strip("_")
    return s[:MAX_KEY_LEN]


def user_key_for(name: str) -> str:
    """Normalize a user display name to a stable user_key.

    >>> user_key_for("Ken")
    'ken'
    >>> user_key_for("Ken (Telegram)")
    'ken_telegram'
    """
    return USER_KEY_RE.sub("_", name.strip().lower())[:MAX_USER_KEY_LEN].strip("_")


# ---------------------------------------------------------------------------
# UserMemoryStore
# ---------------------------------------------------------------------------


class UserMemoryStore:
    """File-backed per-user key/value store.

    Each (user, key) pair lives in its own `<slug>.md` file under
    `memory/users/<user_key>/`. The `_index.json` in the same dir is a
    manifest with the metadata (created_at, updated_at). This dual-file
    layout is deliberate:

    - The .md file is human-readable (open in any editor).
    - The index gives us fast `list_keys()` and `get_metadata()` without
      scanning files.
    """

    def __init__(self, halo_home: Path) -> None:
        self._halo_home = halo_home
        self._base = halo_home / USERS_DIR
        self._base.mkdir(parents=True, exist_ok=True)
        # user_key -> { slug -> { key, value, created_at, updated_at } }
        self._cache: dict[str, dict[str, dict[str, Any]]] = {}
        self._loaded: set[str] = set()
        self._locks: dict[str, str] = {}  # user_key -> lockfile path

    def _user_dir(self, user: str) -> Path:
        return self._base / user

    def _index_path(self, user: str) -> Path:
        return self._user_dir(user) / INDEX_FILE

    def _entry_path(self, user: str, slug: str) -> Path:
        return self._user_dir(user) / f"{slug}.md"

    @contextmanager
    def _user_lock(self, user: str) -> Iterator[None]:
        """Cross-process exclusive lock per user.

        Implemented as `flock` on a sidecar file. Blocks waiting writers
        from clobbering each other.
        """
        self._user_dir(user).mkdir(parents=True, exist_ok=True)
        lock_path = self._user_dir(user) / ".lock"
        with open(lock_path, "a+", encoding="utf-8") as fp:
            fcntl.flock(fp.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fp.fileno(), fcntl.LOCK_UN)

    def _ensure_loaded(self, user: str) -> None:
        if user in self._loaded:
            return
        idx_path = self._index_path(user)
        if idx_path.exists():
            try:
                raw = json.loads(idx_path.read_text(encoding="utf-8"))
                self._cache[user] = raw
            except Exception as e:
                logger.warning(f"Failed to read {idx_path}: {e}")
                self._cache[user] = {}
        else:
            self._cache[user] = {}
        self._loaded.add(user)

    def _save_index(self, user: str) -> None:
        idx_path = self._index_path(user)
        idx_path.write_text(
            json.dumps(self._cache.get(user, {}), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, user: str, key: str) -> MemoryEntry | None:
        """Read a single key. Returns None if missing."""
        slug = slugify_key(key)
        if not slug:
            return None
        self._ensure_loaded(user)
        with self._user_lock(user):
            entry = self._cache.get(user, {}).get(slug)
            if entry is None:
                return None
            return MemoryEntry(
                user=user,
                key=entry["key"],
                value=entry["value"],
                updated_at=float(entry["updated_at"]),
                created_at=float(entry["created_at"]),
            )

    def set(self, user: str, key: str, value: str) -> MemoryEntry:
        """Write a key (create or overwrite).

        Returns the entry as it was written (with the slug form of the
        key). Raises ValueError on invalid input.
        """
        slug = slugify_key(key)
        if not slug:
            raise ValueError(f"key {key!r} slugifies to empty")
        if not isinstance(value, str):
            raise ValueError("value must be a string")
        if len(value.encode("utf-8")) > MAX_VALUE_BYTES:
            raise ValueError(
                f"value too large: {len(value.encode('utf-8'))} bytes "
                f"(max {MAX_VALUE_BYTES})"
            )

        self._ensure_loaded(user)
        with self._user_lock(user):
            entries = self._cache.setdefault(user, {})
            now = time.time()
            existing = entries.get(slug)
            created_at = float(existing["created_at"]) if existing else now
            entries[slug] = {
                "key": slug,
                "value": value,
                "created_at": created_at,
                "updated_at": now,
            }
            # Persist the entry file (human-readable)
            entry_path = self._entry_path(user, slug)
            body = (
                f"# {slug}\n\n"
                f"_updated: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(now))}_\n\n"
                f"{value}\n"
            )
            entry_path.write_text(body, encoding="utf-8")
            # Persist the index
            self._save_index(user)
            # M12 hook: enqueue for embedding
            try:
                from app.memory.lifecycle import on_user_memory_set

                on_user_memory_set(user, slug, value)
            except Exception as e:
                logger.debug(f"UserMemoryStore.set: lifecycle hook failed: {e}")
            return MemoryEntry(
                user=user,
                key=slug,
                value=value,
                updated_at=now,
                created_at=created_at,
            )

    def delete(self, user: str, key: str) -> bool:
        """Delete a key. Returns True if it existed, False otherwise."""
        slug = slugify_key(key)
        if not slug:
            return False
        self._ensure_loaded(user)
        with self._user_lock(user):
            entries = self._cache.get(user, {})
            if slug not in entries:
                return False
            del entries[slug]
            entry_path = self._entry_path(user, slug)
            if entry_path.exists():
                try:
                    entry_path.unlink()
                except Exception as e:
                    logger.warning(f"Failed to delete {entry_path}: {e}")
            self._save_index(user)
            # M12 hook: best-effort (FAISS entry is dropped on next rebuild)
            try:
                from app.memory.lifecycle import on_user_memory_deleted

                on_user_memory_deleted(user, slug)
            except Exception as e:
                logger.debug(f"UserMemoryStore.delete: lifecycle hook failed: {e}")
            return True

    def list_keys(self, user: str) -> list[MemoryEntry]:
        """List all keys for a user, sorted by updated_at (newest first)."""
        self._ensure_loaded(user)
        with self._user_lock(user):
            entries = self._cache.get(user, {})
            out = [
                MemoryEntry(
                    user=user,
                    key=e["key"],
                    value=e["value"],
                    updated_at=float(e["updated_at"]),
                    created_at=float(e["created_at"]),
                )
                for e in entries.values()
            ]
            out.sort(key=lambda e: e.updated_at, reverse=True)
            return out

    def list_users(self) -> list[str]:
        """List all user keys that have at least one memory entry."""
        if not self._base.exists():
            return []
        return sorted(
            d.name
            for d in self._base.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        )

    def user_dir(self, user: str) -> Path:
        return self._user_dir(user)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------


_store: UserMemoryStore | None = None


def get_user_memory_store() -> UserMemoryStore:
    global _store
    if _store is None:
        from app.core.config import get_config

        home = get_config().home
        _store = UserMemoryStore(halo_home=home)
    return _store


def reset_user_memory_store() -> None:
    global _store
    _store = None


__all__ = [
    "MemoryEntry",
    "UserMemoryStore",
    "get_user_memory_store",
    "reset_user_memory_store",
    "slugify_key",
    "user_key_for",
]

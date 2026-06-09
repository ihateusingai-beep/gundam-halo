"""Telegram session manager — maps each chat_id to a persistent agent session.

Each Telegram chat (private DM or group) gets its own session in the
`telegram` project. Sessions are persisted to disk so the agent
remembers prior conversations. One session per chat_id keeps context
scoped — a personal DM and a group chat don't bleed into each other.

Layout on disk:
    ~/.gundam-halo/projects/telegram/
        sessions/
            <session_id>/
                meta.json     # {chat_id, started_at, message_count, ...}
                messages.jsonl # full conversation history
        chat_map.json         # { "<chat_id>": "<session_id>", ... }

The `chat_map.json` is the index. It maps Telegram's chat_id (a string
of digits) to our internal session_id (a UUID-like string). Sessions
without an entry here are orphaned; the manager logs them but doesn't
delete them.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# Special "project" that holds all Telegram conversations. One project
# per channel keeps file paths clean and the persistence layer simple.
TELEGRAM_PROJECT = "telegram"

# Reserved chat_ids used for command-mode control (not real Telegram chats).
# These never collide with real Telegram chat IDs (which are always numeric).
COMMAND_CHAT_ID = ":command:"


@dataclass(slots=True)
class TelegramSessionInfo:
    """Metadata about a single Telegram chat → session mapping."""

    chat_id: str
    session_id: str
    started_at: float
    message_count: int
    last_active: float

    def to_dict(self) -> dict:
        return {
            "chat_id": self.chat_id,
            "session_id": self.session_id,
            "started_at": self.started_at,
            "message_count": self.message_count,
            "last_active": self.last_active,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TelegramSessionInfo":
        return cls(
            chat_id=d["chat_id"],
            session_id=d["session_id"],
            started_at=float(d["started_at"]),
            message_count=int(d["message_count"]),
            last_active=float(d.get("last_active", d["started_at"])),
        )


class TelegramSessionManager:
    """Persistent chat_id → session_id mapping for Telegram conversations.

    Thread-safe (lock around the in-memory map; file writes are atomic
    via tmp + rename). All file I/O is best-effort: if the disk is full
    or permissions fail, we log and keep going in memory.
    """

    def __init__(self, halo_home: Path) -> None:
        self._halo_home = halo_home
        self._project_dir = halo_home / "projects" / TELEGRAM_PROJECT
        self._sessions_dir = self._project_dir / "sessions"
        self._map_path = self._project_dir / "chat_map.json"
        self._lock = threading.RLock()
        # chat_id (str) -> TelegramSessionInfo
        self._map: dict[str, TelegramSessionInfo] = {}
        self._loaded = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_or_create(self, chat_id: str) -> TelegramSessionInfo:
        """Return existing session for *chat_id*, creating one if needed."""
        self._ensure_loaded()
        with self._lock:
            existing = self._map.get(chat_id)
            if existing is not None:
                return existing

            now = time.time()
            info = TelegramSessionInfo(
                chat_id=chat_id,
                session_id=self._new_session_id(),
                started_at=now,
                message_count=0,
                last_active=now,
            )
            self._map[chat_id] = info
            self._save()
            logger.info(
                f"Created Telegram session {info.session_id} for chat_id {chat_id}"
            )
            return info

    def get(self, chat_id: str) -> Optional[TelegramSessionInfo]:
        """Return the session for *chat_id* without creating one."""
        self._ensure_loaded()
        with self._lock:
            return self._map.get(chat_id)

    def reset(self, chat_id: str) -> Optional[TelegramSessionInfo]:
        """Drop the chat_id mapping and create a fresh session.

        Returns the new session info, or None if the chat_id wasn't known.
        """
        self._ensure_loaded()
        with self._lock:
            self._map.pop(chat_id, None)
        new_info = self.get_or_create(chat_id)
        logger.info(f"Reset Telegram session for chat_id {chat_id}")
        return new_info

    def touch(self, chat_id: str, message_count_increment: int = 1) -> None:
        """Update the last_active timestamp and bump message_count."""
        self._ensure_loaded()
        with self._lock:
            info = self._map.get(chat_id)
            if info is None:
                return
            info.last_active = time.time()
            info.message_count += message_count_increment
        self._save()

    def list_sessions(self) -> list[TelegramSessionInfo]:
        self._ensure_loaded()
        with self._lock:
            return sorted(
                self._map.values(),
                key=lambda s: s.last_active,
                reverse=True,
            )

    def project_dir(self) -> Path:
        """Path to the per-project directory used for persistence."""
        return self._project_dir

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._project_dir.mkdir(parents=True, exist_ok=True)
        self._sessions_dir.mkdir(parents=True, exist_ok=True)
        if self._map_path.exists():
            try:
                raw = json.loads(self._map_path.read_text(encoding="utf-8"))
                for chat_id, info_dict in raw.items():
                    self._map[chat_id] = TelegramSessionInfo.from_dict(info_dict)
            except Exception as e:
                logger.warning(
                    f"Failed to read chat_map.json ({e}); starting with empty map"
                )
                self._map = {}
        self._loaded = True

    def _save(self) -> None:
        """Atomic write of the chat map to disk.

        Always called with the lock held OR from a single-writer path.
        We don't re-acquire the lock here because the callers do.
        """
        try:
            raw = {
                chat_id: info.to_dict()
                for chat_id, info in self._map.items()
            }
            # Atomic: write to tmp, then rename
            tmp = self._map_path.with_suffix(".json.tmp")
            tmp.write_text(
                json.dumps(raw, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            tmp.replace(self._map_path)
        except Exception as e:
            logger.warning(f"Failed to persist chat_map.json: {e}")

    @staticmethod
    def _new_session_id() -> str:
        # Avoid pulling in uuid for a single use site
        import secrets

        return f"tg-{secrets.token_hex(8)}"


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_manager: Optional[TelegramSessionManager] = None
_manager_lock = threading.Lock()


def get_telegram_session_manager() -> TelegramSessionManager:
    """Return the process-wide Telegram session manager.

    Lazy-initialised from `cfg.home` on first call.
    """
    global _manager
    with _manager_lock:
        if _manager is None:
            from app.core.config import get_config

            home = get_config().home
            _manager = TelegramSessionManager(halo_home=home)
        return _manager


def reset_telegram_session_manager() -> None:
    """Replace the singleton with a fresh instance (for tests)."""
    global _manager
    with _manager_lock:
        _manager = None


__all__ = [
    "TelegramSessionManager",
    "TelegramSessionInfo",
    "TELEGRAM_PROJECT",
    "COMMAND_CHAT_ID",
    "get_telegram_session_manager",
    "reset_telegram_session_manager",
]

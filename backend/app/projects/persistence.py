"""Session persistence — save/load agent message history to disk.

Storage layout:
    ~/.gundam-halo/projects/<project_name>/conversations/<session_id>.json

Each file is a JSON object with:
    {
        "version": 1,
        "session_id": "...",
        "project_name": "...",
        "agent_type": "...",
        "created_at": "...",
        "updated_at": "...",
        "messages": [Message, ...]
    }

Writes are atomic (write to .tmp, then os.replace) so a crash mid-write
doesn't corrupt the conversation.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from app.core.config import expand_home, get_config
from app.core.types import Message, Role, ToolCall

logger = logging.getLogger(__name__)

# Schema version — bump if Message format changes incompatibly
SCHEMA_VERSION = 1


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def _message_to_dict(m: Message) -> dict:
    return {
        "role": m.role.value,
        "content": m.content,
        "tool_calls": [
            {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
            for tc in m.tool_calls
        ],
        "tool_call_id": m.tool_call_id,
        "name": m.name,
        "metadata": m.metadata,
    }


def _dict_to_message(d: dict) -> Message:
    role = Role(d["role"])
    tool_calls = [
        ToolCall(id=tc["id"], name=tc["name"], arguments=tc.get("arguments", {}))
        for tc in d.get("tool_calls", [])
    ]
    return Message(
        role=role,
        content=d.get("content", ""),
        tool_calls=tool_calls,
        tool_call_id=d.get("tool_call_id"),
        name=d.get("name"),
        metadata=d.get("metadata", {}),
    )


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def conversations_dir(project_name: str) -> Path:
    """Return the conversations dir for a project (create if missing)."""
    cfg = get_config()
    p = cfg.home / "projects" / project_name / "conversations"
    p.mkdir(parents=True, exist_ok=True)
    return p


def session_file_path(project_name: str, session_id: str) -> Path:
    """Return the path to a session's JSON file."""
    return conversations_dir(project_name) / f"{session_id}.json"


# ---------------------------------------------------------------------------
# Save / load
# ---------------------------------------------------------------------------


def save_messages(
    project_name: str,
    session_id: str,
    messages: List[Message],
    *,
    agent_type: str = "native_react",
) -> Path:
    """Atomically save a session's message history to disk.

    Returns the path to the saved file.
    """
    if not project_name or not session_id:
        raise ValueError("project_name and session_id are required")

    path = session_file_path(project_name, session_id)
    now = datetime.now(timezone.utc).isoformat()

    payload = {
        "version": SCHEMA_VERSION,
        "session_id": session_id,
        "project_name": project_name,
        "agent_type": agent_type,
        "updated_at": now,
        "message_count": len(messages),
        "messages": [_message_to_dict(m) for m in messages],
    }

    # If file exists, preserve created_at
    if path.exists():
        try:
            with open(path) as f:
                existing = json.load(f)
            payload["created_at"] = existing.get("created_at", now)
        except (json.JSONDecodeError, OSError):
            payload["created_at"] = now
    else:
        payload["created_at"] = now

    # Atomic write: tmp file in same dir, then rename
    fd, tmp_path = tempfile.mkstemp(
        prefix=f".{session_id}-",
        suffix=".json.tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
        logger.debug(f"Saved {len(messages)} messages to {path}")
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    return path


def load_messages(project_name: str, session_id: str) -> Optional[List[Message]]:
    """Load a session's message history from disk.

    Returns None if the file doesn't exist or can't be parsed.
    """
    path = session_file_path(project_name, session_id)
    if not path.exists():
        return None
    try:
        with open(path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Failed to load {path}: {e}")
        return None

    version = data.get("version", 1)
    if version != SCHEMA_VERSION:
        logger.warning(
            f"Session {session_id} has schema version {version}, "
            f"expected {SCHEMA_VERSION}. Migration may be needed."
        )

    return [_dict_to_message(d) for d in data.get("messages", [])]


def session_exists(project_name: str, session_id: str) -> bool:
    return session_file_path(project_name, session_id).exists()


def delete_session(project_name: str, session_id: str) -> bool:
    """Delete a session's file. Returns True if a file was deleted."""
    path = session_file_path(project_name, session_id)
    if path.exists():
        try:
            path.unlink()
            return True
        except OSError as e:
            logger.error(f"Failed to delete {path}: {e}")
            return False
    return False


# ---------------------------------------------------------------------------
# Scan
# ---------------------------------------------------------------------------


@dataclass
class SessionSummary:
    """Lightweight summary of a persisted session (for listing)."""

    session_id: str
    project_name: str
    agent_type: str
    created_at: str
    updated_at: str
    message_count: int


def scan_project_sessions(project_name: str) -> List[SessionSummary]:
    """Return summaries of all sessions persisted for a project."""
    cfg = get_config()
    d = cfg.home / "projects" / project_name / "conversations"
    if not d.exists():
        return []

    out: List[SessionSummary] = []
    for entry in sorted(d.glob("*.json")):
        try:
            with open(entry) as f:
                data = json.load(f)
            out.append(
                SessionSummary(
                    session_id=data.get("session_id", entry.stem),
                    project_name=data.get("project_name", project_name),
                    agent_type=data.get("agent_type", "native_react"),
                    created_at=data.get("created_at", ""),
                    updated_at=data.get("updated_at", ""),
                    message_count=data.get("message_count", 0),
                )
            )
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to read {entry}: {e}")
    return out


__all__ = [
    "SCHEMA_VERSION",
    "SessionSummary",
    "conversations_dir",
    "delete_session",
    "load_messages",
    "save_messages",
    "scan_project_sessions",
    "session_exists",
    "session_file_path",
]

"""Core types — Message, Role, ToolCall, ToolResult, AgentContext, AgentResult.

These are the fundamental data structures that flow through the system.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class Role(str, Enum):
    """Role of a message in a conversation."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass(slots=True)
class ToolCall:
    """A request from the assistant to call a tool."""

    id: str
    name: str
    arguments: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ToolResult:
    """Result of a tool call."""

    tool_call_id: str
    content: str
    success: bool = True
    error: Optional[str] = None


@dataclass(slots=True)
class Message:
    """A single message in a conversation."""

    role: Role
    content: str
    tool_calls: List[ToolCall] = field(default_factory=list)
    tool_call_id: Optional[str] = None  # for tool messages
    name: Optional[str] = None  # for tool messages
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to OpenAI-compatible message dict."""
        # `role` may be a Role enum (preferred) OR a raw str that snuck in
        # via `_parse_assistant_message` (which forwards msg.role as-is
        # from the OpenAI SDK). Normalize both to a plain str.
        role_str = self.role.value if hasattr(self.role, "value") else str(self.role)
        d: Dict[str, Any] = {"role": role_str, "content": self.content}
        if self.tool_calls:
            d["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": _json_dumps(tc.arguments),
                    },
                }
                for tc in self.tool_calls
            ]
        if self.tool_call_id:
            d["tool_call_id"] = self.tool_call_id
        if self.name:
            d["name"] = self.name
        return d


@dataclass(slots=True)
class AgentContext:
    """Context passed to an agent when running a turn."""

    project_id: str
    session_id: str
    user_id: Optional[str] = None
    channel: Optional[str] = None  # "telegram" | "web" | None
    # Human-readable name (M7-Phase-2). Used in the system prompt so the
    # agent knows who it's talking to. For Telegram this comes from
    # `channels.telegram.display_names[chat_id]` if set, else the
    # sender's first_name / chat title. For other channels TBD.
    user_display_name: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AgentResult:
    """Result of an agent's run."""

    success: bool
    output: str
    messages: List[Message] = field(default_factory=list)
    tool_calls_made: int = 0
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


def _json_dumps(obj: Any) -> str:
    """Tiny JSON dump helper (avoid pulling in json import at module level noise)."""
    import json

    return json.dumps(obj, ensure_ascii=False)


__all__ = [
    "AgentContext",
    "AgentResult",
    "Message",
    "Role",
    "ToolCall",
    "ToolResult",
]

"""Engine base class and ABC.

An engine is a thin wrapper around an LLM API. It exposes:
- `chat(messages, tools)` → returns the next assistant message
- `stream_chat(messages, tools)` → yields chunks for streaming
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator, List, Optional

from app.core.types import Message, ToolCall


class InferenceEngine(ABC):
    """Abstract base for all LLM engines."""

    @abstractmethod
    async def chat(
        self,
        messages: List[Message],
        *,
        tools: Optional[List[dict]] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> Message:
        """Send messages, return the assistant's reply."""

    @abstractmethod
    async def stream_chat(
        self,
        messages: List[Message],
        *,
        tools: Optional[List[dict]] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> AsyncIterator[str]:
        """Stream the assistant's reply as text chunks."""


__all__ = ["InferenceEngine"]

"""Agent base classes and ABCs.

An agent is a stateful unit that takes a user message + context and produces
an agent result (which may include tool calls).

For session persistence, agents accept `initial_messages` at construction.
When provided, the agent seeds its internal message list with these, then
appends the new user turn + subsequent tool turns. This lets us resume
a session from disk.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.core.types import AgentContext, AgentResult, Message


class BaseAgent(ABC):
    """Abstract base for all Gundam Halo agents."""

    agent_id: str

    def __init__(
        self,
        engine: Any,  # InferenceEngine — avoid circular import
        model: str,
        *,
        tools: Optional[List[Any]] = None,
        initial_messages: Optional[List[Message]] = None,
    ) -> None:
        self.engine = engine
        self.model = model
        self._tools = tools or []
        self._initial_messages = list(initial_messages) if initial_messages else []
        self._tool_specs = [t.to_spec() for t in self._tools if hasattr(t, "to_spec")]

    @abstractmethod
    async def run(
        self,
        input: str,
        context: Optional[AgentContext] = None,
        **kwargs: Any,
    ) -> AgentResult:
        """Run one turn of the agent. Implementations manage their own loop."""


__all__ = ["BaseAgent"]

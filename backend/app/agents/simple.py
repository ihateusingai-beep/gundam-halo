"""Simple agent — single-turn chat, no tool use.

The most basic agent. Sends the user message + system prompt to the LLM,
returns the response. No loop, no tools, no memory.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from app.agents._stubs import BaseAgent
from app.core.registry import AgentRegistry
from app.core.types import AgentContext, AgentResult, Message, Role

logger = logging.getLogger(__name__)

SIMPLE_SYSTEM_PROMPT = """You are Gundam Halo, a personal AI agent on the user's Mac.
Be concise, direct, and helpful. No fluff.
If you don't know something, say so. Don't make up file contents or system state.
"""


@AgentRegistry.register("simple")
class SimpleAgent(BaseAgent):
    """Single-turn chat, no tools. The most basic agent."""

    agent_id = "simple"

    async def run(
        self,
        input: str,
        context: Optional[AgentContext] = None,
        **kwargs: Any,
    ) -> AgentResult:
        messages = [
            Message(role=Role.SYSTEM, content=SIMPLE_SYSTEM_PROMPT),
            Message(role=Role.USER, content=input),
        ]

        try:
            response = await self.engine.chat(messages)
        except Exception as e:
            logger.error(f"SimpleAgent error: {e}")
            return AgentResult(
                success=False,
                output="",
                error=str(e),
            )

        return AgentResult(
            success=True,
            output=response.content,
            messages=[response],
            tool_calls_made=0,
        )


__all__ = ["SimpleAgent"]

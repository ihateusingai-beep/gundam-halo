"""NativeReAct agent — OpenAI function-calling loop.

Uses the LLM's native tool_calls field (not text-based Action/Action Input parsing).
Each turn: call LLM with messages + tool specs → LLM returns tool_calls →
execute each tool → append tool results as Tool messages → loop.
"""

from __future__ import annotations

import logging
from typing import Any, List, Optional

from app.agents._stubs import BaseAgent
from app.core.registry import AgentRegistry
from app.core.types import (
    AgentContext,
    AgentResult,
    Message,
    Role,
    ToolCall,
    ToolResult,
)
from app.tools._stubs import BaseTool

logger = logging.getLogger(__name__)

REACT_SYSTEM_PROMPT = """You are Gundam Halo, a personal AI agent on the user's Mac.
You help with file operations, shell commands, and app launching on their machine.

You have access to tools. Use them when the user asks for actions you can't do from
text alone (reading a file, running a command, launching an app).

When you've gathered enough information, give a final answer. Don't keep calling
tools if you have what you need.

Be concise. Cite file paths and command outputs. Don't make up file contents —
use file_read to actually read files."""


@AgentRegistry.register("native_react")
class NativeReActAgent(BaseAgent):
    """ReAct-style agent using OpenAI function calling."""

    agent_id = "native_react"
    _default_max_turns = 10

    def __init__(
        self,
        engine: Any,
        model: str,
        *,
        tools: Optional[List[BaseTool]] = None,
        max_turns: Optional[int] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(engine, model, tools=tools)
        self._max_turns = max_turns or self._default_max_turns
        self._tool_by_name = {t.name: t for t in self._tools}

    async def run(
        self,
        input: str,
        context: Optional[AgentContext] = None,
        **kwargs: Any,
    ) -> AgentResult:
        messages: List[Message] = [
            Message(role=Role.SYSTEM, content=REACT_SYSTEM_PROMPT),
            Message(role=Role.USER, content=input),
        ]
        all_messages: List[Message] = list(messages)
        tool_calls_made = 0

        for turn in range(self._max_turns):
            try:
                response = await self.engine.chat(
                    messages,
                    tools=self._tool_specs,
                )
            except Exception as e:
                logger.error(f"native_react LLM error: {e}")
                return AgentResult(
                    success=False,
                    output="",
                    messages=all_messages,
                    tool_calls_made=tool_calls_made,
                    error=f"LLM error: {e}",
                )

            all_messages.append(response)

            # If no tool calls → final answer
            if not response.tool_calls:
                return AgentResult(
                    success=True,
                    output=response.content or "",
                    messages=all_messages,
                    tool_calls_made=tool_calls_made,
                )

            # Execute each tool call
            for tc in response.tool_calls:
                tool_calls_made += 1  # LLM attempted to call this tool
                tool = self._tool_by_name.get(tc.name)
                if not tool:
                    observation = f"Error: tool '{tc.name}' not found"
                else:
                    try:
                        observation = await tool.run(**tc.arguments)
                    except Exception as e:
                        logger.error(f"Tool {tc.name} error: {e}")
                        observation = f"Error executing {tc.name}: {e}"

                # Append as Tool message (OpenAI function-calling format)
                messages.append(
                    Message(
                        role=Role.TOOL,
                        content=observation,
                        tool_call_id=tc.id,
                        name=tc.name,
                    )
                )
                all_messages.append(messages[-1])

        # Hit max turns without final answer
        return AgentResult(
            success=False,
            output="Reached max turns without a final answer.",
            messages=all_messages,
            tool_calls_made=tool_calls_made,
            error="max_turns_exceeded",
        )


__all__ = ["NativeReActAgent"]

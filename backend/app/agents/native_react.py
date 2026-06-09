"""NativeReAct agent — OpenAI function-calling loop.

Uses the LLM's native tool_calls field (not text-based Action/Action Input parsing).
Each turn: call LLM with messages + tool specs → LLM returns tool_calls →
execute each tool → append tool results as Tool messages → loop.
"""

from __future__ import annotations

import logging
import time
from typing import Any, List, Optional

from app.agents._stubs import BaseAgent
from app.core.events import EventType, get_event_bus
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
        initial_messages: Optional[List[Message]] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(engine, model, tools=tools, initial_messages=initial_messages)
        self._max_turns = max_turns or self._default_max_turns
        self._tool_by_name = {t.name: t for t in self._tools}

    async def run(
        self,
        input: str,
        context: Optional[AgentContext] = None,
        **kwargs: Any,
    ) -> AgentResult:
        # Seed message list: if resuming, use initial_messages + new user turn
        # Otherwise, fresh start with system + user
        if self._initial_messages:
            messages: List[Message] = list(self._initial_messages) + [
                Message(role=Role.USER, content=input)
            ]
        else:
            # M7-Phase-2: augment the system prompt with identity + memory
            # recall so the agent knows who it's talking to and what it
            # remembers about them.
            from app.agents.system_prompt import build_system_prompt

            system = build_system_prompt(REACT_SYSTEM_PROMPT, context=context)
            messages: List[Message] = [
                Message(role=Role.SYSTEM, content=system),
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
                call_id = tc.id or f"call-{tool_calls_made}"
                started_at = time.time()

                # Publish TOOL_CALL_START — let the dashboard animate the panel in
                get_event_bus().publish(
                    EventType.TOOL_CALL_START,
                    {
                        "call_id": call_id,
                        "tool": tc.name,
                        "args": tc.arguments,
                        "session_id": context.session_id if context else None,
                        "project": context.project_id if context else None,
                    },
                )

                if not tool:
                    observation = f"Error: tool '{tc.name}' not found"
                    ok = False
                else:
                    try:
                        # M7-Phase-2: thread the user context into the tool
                        # call so tools like memory_read/write can resolve
                        # which user this is. We pass display_name /
                        # transport_id; tools that don't care ignore them.
                        call_kwargs = dict(tc.arguments or {})
                        if context is not None:
                            if context.user_display_name and "display_name" not in call_kwargs:
                                call_kwargs["display_name"] = context.user_display_name
                            if context.user_id and "transport_id" not in call_kwargs:
                                call_kwargs["transport_id"] = context.user_id
                        observation = await tool.run(**call_kwargs)
                        ok = True
                    except Exception as e:
                        logger.error(f"Tool {tc.name} error: {e}")
                        observation = f"Error executing {tc.name}: {e}"
                        ok = False

                duration_ms = int((time.time() - started_at) * 1000)

                # Publish TOOL_CALL_END — match on call_id
                get_event_bus().publish(
                    EventType.TOOL_CALL_END,
                    {
                        "call_id": call_id,
                        "tool": tc.name,
                        "ok": ok,
                        "duration_ms": duration_ms,
                        "result_preview": observation[:200] if observation else "",
                        "session_id": context.session_id if context else None,
                        "project": context.project_id if context else None,
                    },
                )

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

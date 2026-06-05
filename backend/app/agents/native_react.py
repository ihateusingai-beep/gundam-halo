"""NativeReAct agent — Thought → Action → Observation loop.

The default agent for most projects. Iterates: ask LLM, parse response for
thought/action, execute tool if action, append observation, repeat until
LLM gives a final answer or max turns reached.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

from app.agents._stubs import BaseAgent
from app.core.registry import AgentRegistry
from app.core.types import AgentContext, AgentResult, Message, Role, ToolCall, ToolResult

logger = logging.getLogger(__name__)

REACT_SYSTEM_PROMPT = """You are Gundam Halo, a personal AI agent on the user's Mac.
Use the ReAct pattern: Thought → Action → Observation → ... → Final Answer.

For each step, respond with:
Thought: <your reasoning>
Action: <tool_name>
Action Input: <json arguments>

When you have the final answer:
Thought: <your reasoning>
Final Answer: <your answer>

Available tools:
{tools}
"""


@AgentRegistry.register("native_react")
class NativeReActAgent(BaseAgent):
    """ReAct-style loop agent with tool use."""

    agent_id = "native_react"
    _default_max_turns = 10

    def __init__(self, *args: Any, max_turns: Optional[int] = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._max_turns = max_turns or self._default_max_turns

    def _parse_response(self, text: str) -> dict:
        """Parse ReAct structured output."""
        result = {"thought": "", "action": "", "action_input": "", "final_answer": ""}

        thought_match = re.search(
            r"Thought:\s*(.+?)(?=\nAction:|\nFinal Answer:|\Z)",
            text, re.DOTALL | re.IGNORECASE,
        )
        if thought_match:
            result["thought"] = thought_match.group(1).strip()

        final_match = re.search(
            r"Final Answer:\s*(.+)", text, re.DOTALL | re.IGNORECASE
        )
        if final_match:
            result["final_answer"] = final_match.group(1).strip()
            return result

        action_match = re.search(r"Action:\s*(.+)", re.IGNORECASE)
        if action_match:
            result["action"] = action_match.group(1).strip()

        input_match = re.search(
            r"Action Input:\s*(.+?)(?=\n\n|\nThought:|\Z)",
            text, re.DOTALL | re.IGNORECASE,
        )
        if input_match:
            result["action_input"] = input_match.group(1).strip()

        return result

    async def run(
        self,
        input: str,
        context: Optional[AgentContext] = None,
        **kwargs: Any,
    ) -> AgentResult:
        # Build tool descriptions
        tool_desc = "\n".join(
            f"- {t['name']}: {t.get('description', 'no description')}"
            for t in self._tool_specs
        )
        system_prompt = REACT_SYSTEM_PROMPT.format(tools=tool_desc or "(no tools available)")

        messages = [
            Message(role=Role.SYSTEM, content=system_prompt),
            Message(role=Role.USER, content=input),
        ]
        all_messages: list[Message] = list(messages)
        tool_calls_made = 0
        tool_by_name = {t.name: t for t in self._tools if hasattr(t, "name")}

        for turn in range(self._max_turns):
            response = await self.engine.chat(messages)
            all_messages.append(response)

            parsed = self._parse_response(response.content)

            if parsed["final_answer"]:
                return AgentResult(
                    success=True,
                    output=parsed["final_answer"],
                    messages=all_messages,
                    tool_calls_made=tool_calls_made,
                )

            if not parsed["action"]:
                # No action, no final answer — treat the response as the final answer
                return AgentResult(
                    success=True,
                    output=response.content,
                    messages=all_messages,
                    tool_calls_made=tool_calls_made,
                )

            # Execute tool
            action = parsed["action"].strip()
            tool = tool_by_name.get(action)
            if not tool:
                observation = f"Error: tool '{action}' not found."
            else:
                import json
                try:
                    action_input = json.loads(parsed["action_input"]) if parsed["action_input"] else {}
                except json.JSONDecodeError:
                    action_input = {"raw": parsed["action_input"]}

                try:
                    result = await tool.run(**action_input) if hasattr(tool, "run") else tool(**action_input)
                    observation = str(result)
                except Exception as e:
                    observation = f"Error executing tool: {e}"

                tool_calls_made += 1

            # Append observation as a tool message (using the chat format)
            messages.append(
                Message(
                    role=Role.TOOL,
                    content=f"Observation: {observation}",
                    tool_call_id=f"tool_call_{turn}",
                    name=action,
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

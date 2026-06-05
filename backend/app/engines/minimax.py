"""MiniMax LLM engine — OpenAI-compatible API.

Uses the official `openai` Python SDK with a custom `base_url` to talk to
MiniMax. No MiniMax-specific code needed beyond the URL + model name.
"""

from __future__ import annotations

import logging
from typing import AsyncIterator, List, Optional

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletion, ChatCompletionChunk

from app.core.types import Message, ToolCall
from app.engines._stubs import InferenceEngine

logger = logging.getLogger(__name__)


def _parse_assistant_message(response: ChatCompletion) -> Message:
    """Convert OpenAI ChatCompletion → app Message."""
    if not response.choices:
        return Message(role=response.choices[0].message.role, content="")

    choice = response.choices[0]
    msg = choice.message

    tool_calls: List[ToolCall] = []
    if msg.tool_calls:
        for tc in msg.tool_calls:
            # tc.function.arguments is a JSON string — parse to dict
            import json

            try:
                args = json.loads(tc.function.arguments) if tc.function.arguments else {}
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse tool call arguments: {tc.function.arguments}")
                args = {}

            tool_calls.append(
                ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=args,
                )
            )

    return Message(
        role=msg.role,
        content=msg.content or "",
        tool_calls=tool_calls,
    )


class MiniMaxEngine(InferenceEngine):
    """MiniMax LLM engine via OpenAI-compatible API."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.MiniMax.chat/v1",
        model: str = "MiniMax-M3",
    ) -> None:
        if not api_key:
            raise ValueError("MiniMax API key is required")

        self.model = model
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        logger.info(f"MiniMax engine initialized (model={model}, base_url={base_url})")

    async def chat(
        self,
        messages: List[Message],
        *,
        tools: Optional[List[dict]] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> Message:
        """Send messages, get back a single assistant reply."""
        payload = {
            "model": self.model,
            "messages": [m.to_dict() for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = tools

        try:
            response: ChatCompletion = await self.client.chat.completions.create(**payload)
        except Exception as e:
            logger.error(f"MiniMax API error: {e}")
            raise

        return _parse_assistant_message(response)

    async def stream_chat(
        self,
        messages: List[Message],
        *,
        tools: Optional[List[dict]] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> AsyncIterator[str]:
        """Stream the assistant's reply as text chunks."""
        payload = {
            "model": self.model,
            "messages": [m.to_dict() for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        if tools:
            payload["tools"] = tools

        try:
            stream = await self.client.chat.completions.create(**payload)
            async for chunk in stream:  # type: ChatCompletionChunk
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            logger.error(f"MiniMax stream error: {e}")
            raise


__all__ = ["MiniMaxEngine"]

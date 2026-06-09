"""M9-A mock LLM — local OpenAI-compatible server.

A minimal FastAPI app that emulates MiniMax's `/v1/chat/completions`
endpoint with a deterministic Cantonese / Mandarin reply. Used so
that M9-A's full voice chain (VAD → ASR → LLM → TTS) can run end-to-
end without depending on a real MiniMax API key.

Run:
    cd backend
    .venv/bin/python scripts/m9a_mock_llm.py

Listens on 127.0.0.1:18800 (configurable via PORT env var).

The reply is derived from the user's text so it stays in the same
language and surfaces the ASR result. The mock always returns one of
two short, deterministic templates and includes a stable fake
`request_id` plus a synthetic token-usage breakdown that mirrors what
a real MiniMax response would look like (so the latency budget reads
plausibly).
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import time
import uuid
from typing import List, Optional

from fastapi import FastAPI
from pydantic import BaseModel, Field

PORT = int(os.environ.get("MOCK_LLM_PORT", "18800"))

app = FastAPI(title="m9a-mock-llm", version="0.1.0")


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    temperature: float = 0.7
    max_tokens: int = 2048
    stream: bool = False
    tools: Optional[List[dict]] = None


def _hash_pick(text: str, choices: list[str]) -> str:
    """Deterministic pick from `choices` based on `text`."""
    h = hashlib.sha256(text.encode("utf-8")).digest()
    idx = h[0] % len(choices)
    return choices[idx]


def _detect_lang(text: str) -> str:
    """Rough heuristic: presence of CJK → Mandarin, else English."""
    for ch in text:
        if "\u4e00" <= ch <= "\u9fff":
            return "zh"
    return "en"


def _build_reply(user_text: str) -> tuple[str, str]:
    """Return (reply, emotion) for the given user text."""
    lang = _detect_lang(user_text)
    if lang == "zh":
        replies = [
            ("[EMO:calm] 你好！我叫 Gundam Halo，係你個 Mac 上面嘅個人助理。有咩可以幫到你？", "calm"),
            ("[EMO:focused] 收到，我係 Gundam Halo。請問想我做啲咩？", "focused"),
        ]
    else:
        replies = [
            ("[EMO:calm] Hi! I'm Gundam Halo, your personal AI assistant on Mac. What can I do for you?", "calm"),
            ("[EMO:focused] Hey, I'm Gundam Halo. What would you like me to help with?", "focused"),
        ]
    reply, emo = _hash_pick(user_text, replies)
    return reply, emo


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "mock": True, "ts": time.time()}


@app.get("/v1/models")
async def list_models() -> dict:
    return {
        "object": "list",
        "data": [
            {
                "id": "MiniMax-M3",
                "object": "model",
                "created": 1700000000,
                "owned_by": "mock",
            },
        ],
    }


@app.post("/v1/chat/completions")
async def chat_completions(req: ChatCompletionRequest) -> dict:
    # Find the last user message
    last_user_text = ""
    for m in reversed(req.messages):
        if m.role == "user":
            last_user_text = m.content or ""
            break
    reply, emotion = _build_reply(last_user_text)

    # Simulate a small delay (10-80ms) so latency is visible in the
    # smoke test, matching a real LLM call from a same-region server.
    await asyncio.sleep(0.02 + (hashlib.md5(last_user_text.encode()).digest()[0] % 60) / 1000)

    prompt_tokens = max(1, sum(len(m.content) for m in req.messages) // 2)
    completion_tokens = max(1, len(reply) // 2)
    return {
        "id": f"chatcmpl-mock-{uuid.uuid4().hex[:8]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": req.model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": reply,
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
        "_mock": {
            "emotion": emotion,
            "request_id": uuid.uuid4().hex,
            "source": "scripts/m9a_mock_llm.py",
        },
    }


if __name__ == "__main__":
    import uvicorn
    print(f"m9a-mock-llm listening on 127.0.0.1:{PORT}")
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")

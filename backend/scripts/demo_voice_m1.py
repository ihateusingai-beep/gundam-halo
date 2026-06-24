"""M1 live demo: voice.text → ASR (fake) → Agent → text reply.

This script proves the M1 happy path:
1. Boot the FastAPI app (in-process, no uvicorn)
2. Set a fake agent callback that calls the real MiniMax LLM
3. Connect to /ws/voice via TestClient (no real VAD/ASR)
4. Send `voice.text` frame with a question
5. Verify an `agent.message` reply comes back

Requires: MINIMAX_API_KEY env var
"""

from __future__ import annotations

import asyncio
import json
import os
import sys


async def main() -> int:
    if not os.environ.get("MINIMAX_API_KEY"):
        print("ERROR: MINIMAX_API_KEY env var not set", file=sys.stderr)
        return 1

    # Configure voice to use fakes
    from app.core import config as _config_module
    from app.voice.asr import asr_factory
    from app.voice.vad import vad_factory
    from tests.voice.fakes import FakeASR, FakeVAD

    cfg = _config_module.get_config()
    cfg.voice.enabled = True
    cfg.voice.asr.model_size = "tiny"
    fake_vad = FakeVAD()
    fake_asr = FakeASR(default_text="open Safari please")
    vad_factory.create_vad = lambda config=None: fake_vad
    asr_factory.create_asr = lambda config=None: fake_asr

    # Set up a real-LLM agent callback
    from app.api import voice_ws

    async def real_agent(sid: str, text: str) -> str:
        """Route voice text through the real LLM (no tool calls, simple chat)."""
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            api_key=os.environ["MINIMAX_API_KEY"],
            base_url=cfg.llm.base_url,
        )
        resp = await client.chat.completions.create(
            model=cfg.llm.default_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are Gundam Halo, a personal AI assistant on the "
                        "user's Mac. Reply in one short sentence, in the "
                        "same language the user used. Do NOT call any tools."
                    ),
                },
                {"role": "user", "content": text},
            ],
            max_tokens=128,
        )
        return (resp.choices[0].message.content or "").strip()

    voice_ws.set_agent_callback(real_agent)

    # Boot the app + open a WS connection
    from app.main import create_app
    from fastapi.testclient import TestClient

    app = create_app()
    print("App created. Opening WS to /ws/voice ...")

    with TestClient(app) as client:
        with client.websocket_connect("/ws/voice") as ws:
            hello = ws.receive_json()
            asr_info = (
                f"{hello['data']['asr_backend']}/"
                f"{hello['data']['asr_model']}"
            )
            print(
                f"<- {hello['type']}: "
                f"vad={hello['data']['vad_backend']}, asr={asr_info}"
            )

            prompt = "What is 2 + 2? Reply in English only."
            print(f"-> voice.text: {prompt!r}")
            ws.send_text(json.dumps({
                "type": "voice.text",
                "session_id": "smoke-1",
                "text": prompt,
            }))

            print("Waiting for agent reply ...")
            while True:
                msg = ws.receive_json()
                mtype = msg.get("type")
                if mtype == "agent.message":
                    print(f"<- agent.message: {msg['data']['text']!r}")
                    return 0
                elif mtype == "asr.result":
                    print(f"<- asr.result: {msg['data']['text']!r}")
                else:
                    print(f"<- {mtype}: {msg}")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

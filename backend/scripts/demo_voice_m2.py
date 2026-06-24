"""M2 live demo: voice.text → ASR (fake) → Agent → TTS streaming (real Edge).

Requires:
- MINIMAX_API_KEY env var
- Network access to api.minimax.chat + tts.edge.microsoft.com
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path


async def main() -> int:
    if not os.environ.get("MINIMAX_API_KEY"):
        print("ERROR: MINIMAX_API_KEY env var not set", file=sys.stderr)
        return 1

    from app.core import config as _config_module
    from app.voice.asr import asr_factory
    from app.voice.vad import vad_factory
    from app.voice.halo_responder import HaloResponder
    from tests.voice.fakes import FakeASR, FakeVAD

    # Fakes for input pipeline
    cfg = _config_module.get_config()
    cfg.voice.enabled = True
    fake_vad = FakeVAD()
    fake_asr = FakeASR()
    vad_factory.create_vad = lambda config=None: fake_vad
    asr_factory.create_asr = lambda config=None: fake_asr

    # Real Edge TTS for output
    from app.voice.tts.tts_factory import create_tts

    tts = create_tts(cfg.voice.tts)
    responder = HaloResponder(tts=tts, live2d=None)
    print(
        f"TTS backend: {type(tts).__name__} "
        f"(voice={cfg.voice.tts.voice}, rate={cfg.voice.tts.rate})"
    )

    # Real-LLM agent callback
    from openai import AsyncOpenAI
    from app.api import voice_ws

    async def real_agent(sid: str, text: str) -> str:
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
                        "user's Mac. Reply in one or two short sentences. "
                        "Optionally prefix with [EMO:calm] [EMO:focused] "
                        "[EMO:awakening] [EMO:alert] to set your tone. "
                        "Reply in the same language the user used."
                    ),
                },
                {"role": "user", "content": text},
            ],
            max_tokens=128,
        )
        return (resp.choices[0].message.content or "").strip()

    voice_ws.set_agent_callback(real_agent)
    voice_ws.set_responder(responder)

    from app.main import create_app
    from fastapi.testclient import TestClient

    app = create_app()

    with TestClient(app) as client:
        with client.websocket_connect("/ws/voice") as ws:
            hello = ws.receive_json()
            print(
                f"<- {hello['type']}: "
                f"tts_enabled={hello['data']['tts_enabled']}, "
                f"live2d_enabled={hello['data']['live2d_enabled']}"
            )

            prompts = [
                "你好嗎？",
                "Say hi in English.",
                "[force-test] Just confirm you can speak.",
            ]
            for prompt in prompts:
                print(f"\n-> voice.text: {prompt!r}", flush=True)
                ws.send_text(json.dumps({
                    "type": "voice.text",
                    "session_id": f"m2-demo-{prompt[:10]}",
                    "text": prompt,
                }))
                print(f"   sent, waiting for reply...", flush=True)

                # Drain messages, skip binary
                import concurrent.futures
                chunks = 0
                text_frames = 0
                total_audio_bytes = 0
                agent_text = None
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                    while True:
                        try:
                            f = ex.submit(ws.receive)
                            raw = f.result(timeout=8.0)
                        except concurrent.futures.TimeoutError:
                            print("  (stream timeout)", flush=True)
                            break
                        if not isinstance(raw, dict):
                            continue
                        if raw.get("type") == "websocket.disconnect":
                            break
                        if raw.get("type") == "websocket.send":
                            if "text" in raw and raw["text"]:
                                try:
                                    msg = json.loads(raw["text"])
                                except json.JSONDecodeError:
                                    continue
                                mtype = msg.get("type")
                                if mtype == "agent.message":
                                    agent_text = msg["data"]["text"]
                                    emotion = msg["data"].get("emotion")
                                    print(
                                        f"<- agent.message: "
                                        f"emotion={emotion}, "
                                        f"text={agent_text!r}",
                                        flush=True,
                                    )
                                elif mtype == "tts.start":
                                    print(
                                        f"<- tts.start: {msg['data']}",
                                        flush=True,
                                    )
                                elif mtype == "tts.end":
                                    print(
                                        f"<- tts.end: {msg['data']}, "
                                        f"total_audio={total_audio_bytes} bytes",
                                        flush=True,
                                    )
                                    text_frames += 1
                                    break  # Done with this turn
                                elif mtype == "voice.error":
                                    print(
                                        f"<- voice.error: {msg['data']}",
                                        flush=True,
                                    )
                                else:
                                    text_frames += 1
                            elif "bytes" in raw and raw["bytes"]:
                                chunks += 1
                                total_audio_bytes += len(raw["bytes"])
                        else:
                            text_frames += 1

                print(
                    f"  (turn: {text_frames} text frames, "
                    f"{chunks} audio chunks, "
                    f"{total_audio_bytes} bytes total)",
                    flush=True,
                )

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

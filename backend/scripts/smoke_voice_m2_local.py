"""M2 local smoke: voice.text → fake agent → real Edge TTS streaming.

This bypasses the LLM (which would need a real API key) and just
verifies the TTS streaming pipeline end-to-end.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path


async def main() -> int:
    from app.core import config as _config_module
    from app.voice.asr import asr_factory
    from app.voice.vad import vad_factory
    from app.voice.halo_responder import HaloResponder
    from tests.voice.fakes import FakeASR, FakeVAD

    cfg = _config_module.get_config()
    cfg.voice.enabled = True
    fake_vad = FakeVAD()
    fake_asr = FakeASR()
    vad_factory.create_vad = lambda config=None: fake_vad
    asr_factory.create_asr = lambda config=None: fake_asr

    from app.voice.tts.tts_factory import create_tts
    tts = create_tts(cfg.voice.tts)
    responder = HaloResponder(tts=tts, live2d=None)
    print(
        f"TTS backend: {type(tts).__name__} "
        f"(voice={cfg.voice.tts.voice}, rate={cfg.voice.tts.rate})"
    )

    from app.api import voice_ws

    async def fake_agent(sid: str, text: str) -> str:
        # Real Edge TTS response (not from LLM)
        return (
            "[EMO:awakening] Psychoframe online. "
            "Gundam Halo ready. "
            "All systems nominal."
        )

    voice_ws.set_agent_callback(fake_agent)
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
                "halo",  # Cantonese: should respond with HK voice
                "halo status",
            ]
            for prompt in prompts:
                print(f"\n-> voice.text: {prompt!r}", flush=True)
                ws.send_text(json.dumps({
                    "type": "voice.text",
                    "session_id": f"m2smoke-{prompt[:10]}",
                    "text": prompt,
                }))

                import concurrent.futures
                chunks = 0
                total_audio_bytes = 0
                saved_path = None
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                    while True:
                        try:
                            f = ex.submit(ws.receive)
                            raw = f.result(timeout=15.0)
                        except concurrent.futures.TimeoutError:
                            print("  (timeout)", flush=True)
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
                                    print(
                                        f"<- agent.message: "
                                        f"emotion={msg['data'].get('emotion')}, "
                                        f"text={msg['data']['text']!r}",
                                        flush=True,
                                    )
                                elif mtype == "tts.start":
                                    print(
                                        f"<- tts.start: {msg['data']}",
                                        flush=True,
                                    )
                                    # Start saving audio to a new file
                                    if saved_path is None:
                                        saved_path = (
                                            Path(f"/tmp/halo_m2_{prompt[:5]}.mp3")
                                        )
                                        saved_path.write_bytes(b"")
                                elif mtype == "tts.end":
                                    print(
                                        f"<- tts.end: chunks={chunks}, "
                                        f"total_audio={total_audio_bytes} bytes",
                                        flush=True,
                                    )
                                    if saved_path:
                                        print(
                                            f"   (audio saved to {saved_path})",
                                            flush=True,
                                        )
                                    break
                                elif mtype == "voice.error":
                                    print(
                                        f"<- voice.error: {msg['data']}",
                                        flush=True,
                                    )
                            elif "bytes" in raw and raw["bytes"]:
                                chunks += 1
                                total_audio_bytes += len(raw["bytes"])
                                if saved_path is not None:
                                    with open(saved_path, "ab") as f:
                                        f.write(raw["bytes"])

    # Save the audio bytes for inspection
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

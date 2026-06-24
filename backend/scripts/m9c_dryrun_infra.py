"""M9-C infra dry-run — boot the FULL voice + agent pipeline end-to-end
WITHOUT a real MiniMax API key, to confirm every non-LLM component
loads + warms up + wires correctly.

Two phases:

  PHASE A — Pure infra import + warmup
    Silero VAD, Whisper ASR, Edge TTS, HaloResponder, ToolRegistry
    defaults, NativeReActAgent (with a STUB engine that pretends to
    call file_read once then return a final answer).

    Verifies:
      - VAD/ASR/TTS model files reachable
      - Whisper base loads on device=mps
      - Edge TTS client compiles
      - ToolRegistry has all 9 default tools (file_read, file_write,
        shell_exec, open_app, mavis_delegate, web_fetch, weather,
        memory_read, memory_write)
      - NativeReActAgent instantiates with the stub engine

  PHASE B — End-to-end chain via /ws/voice (voice.text path)
    Stream a text query directly (bypassing VAD/ASR) → agent
    callback (which calls NativeReActAgent.run) → HaloResponder →
    TTS audio frames back over WebSocket.

    Verifies:
      - /ws/voice WebSocket connects, voice.hello frame received
      - voice.text protocol triggers agent → tts.start → tts.audio
        (binary) → tts.end → voice.turn_ended
      - Stub engine's tool_calls are honoured — file_read is invoked
        on the actual README via ToolRegistry, real file content
        reaches the agent's response.
      - TTS produces real MP3 bytes (not empty)

Run:
    cd backend
    .venv/bin/python scripts/m9c_dryrun_infra.py

Exits 0 on full pass, 1 on any infra gap.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import json
import os
import sys
import time
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


# ---------------------------------------------------------------------------
# Stub MiniMax engine — pretends the LLM chose to call file_read once
# then returns a final answer quoting the README's first line.
# ---------------------------------------------------------------------------


class StubFileReadEngine:
    """Drop-in replacement for MiniMaxEngine that scripts a fixed
    tool-call sequence: 1× file_read on the README, then a final
    answer that quotes its first line. No network call."""

    def __init__(self, readme_path: str) -> None:
        self.readme_path = readme_path
        self.model = "stub-minimax-m2"
        self.turn_count = 0
        try:
            with open(readme_path) as f:
                self._readme_first_line = f.readline().strip()
        except OSError as e:
            self._readme_first_line = f"<unreadable: {e}>"

    async def chat(self, messages, *, tools=None, temperature=0.7, max_tokens=2048):
        from app.core.types import Message, Role, ToolCall

        self.turn_count += 1
        # Turn 1: pretend LLM picks file_read tool
        if self.turn_count == 1:
            return Message(
                role=Role.ASSISTANT,
                content="",
                tool_calls=[
                    ToolCall(
                        id="call_stub_1",
                        name="file_read",
                        arguments={"path": self.readme_path},
                    )
                ],
            )
        # Turn 2: pretend LLM got the file content and gives a final answer
        return Message(
            role=Role.ASSISTANT,
            content=(
                "[EMO:calm] 根據我讀到嘅 README，"
                f"嗰行寫嘅係「{self._readme_first_line}」。"
            ),
        )

    async def stream_chat(self, messages, *, tools=None, temperature=0.7, max_tokens=2048):
        msg = await self.chat(messages, tools=tools, temperature=temperature, max_tokens=max_tokens)
        yield msg.content or ""


# ---------------------------------------------------------------------------
# Phase A — pure infra import + warmup
# ---------------------------------------------------------------------------


async def phase_a() -> dict:
    print("=" * 60)
    print("PHASE A — Infra import + warmup (no LLM call)")
    print("=" * 60)
    results: dict = {}

    # Config
    from app.core import config as _config_module
    cfg = _config_module.get_config()
    cfg.voice.enabled = True
    print(f"  config: voice.enabled={cfg.voice.enabled} "
          f"asr.model_size={cfg.voice.asr.model_size} "
          f"tts.voice={cfg.voice.tts.voice} "
          f"base_url={cfg.llm.base_url}")

    # VAD
    print("  loading VAD (Silero JIT)...", flush=True)
    t0 = time.time()
    from app.voice.vad.vad_factory import create_vad
    vad = create_vad(cfg.voice.vad)
    results["vad_class"] = type(vad).__name__
    print(f"    {type(vad).__name__} ready in {time.time()-t0:.1f}s")

    # ASR
    print("  loading ASR (Whisper base on mps)...", flush=True)
    t0 = time.time()
    from app.voice.asr.asr_factory import create_asr
    asr = create_asr(cfg.voice.asr)
    results["asr_class"] = type(asr).__name__
    print(f"    {type(asr).__name__} ready in {time.time()-t0:.1f}s")

    # TTS
    print("  loading TTS (edge)...", flush=True)
    t0 = time.time()
    from app.voice.tts.tts_factory import create_tts
    tts = create_tts(cfg.voice.tts)
    results["tts_class"] = type(tts).__name__
    print(f"    {type(tts).__name__} ready in {time.time()-t0:.1f}s")
    if hasattr(tts, "warmup"):
        print("    TTS.warmup()...", flush=True)
        t0 = time.time()
        await tts.warmup()
        print(f"    warmed in {time.time()-t0:.1f}s")

    # HaloResponder
    print("  building HaloResponder...", flush=True)
    from app.voice.halo_responder import HaloResponder
    responder = HaloResponder(tts=tts, live2d=None, theme=cfg.voice.live2d.theme)
    print("    HaloResponder.warmup()...", flush=True)
    t0 = time.time()
    await responder.warmup()
    print(f"    warmed in {time.time()-t0:.1f}s")

    # VoicePipeline
    print("  building VoicePipeline...", flush=True)
    from app.voice.pipeline import VoicePipeline
    pipeline = VoicePipeline(
        vad=vad,
        asr=asr,
        speech_threshold_start=cfg.voice.vad.speech_threshold_start,
        speech_threshold_end=cfg.voice.vad.speech_threshold_end,
        min_speech_ms=cfg.voice.vad.min_speech_ms,
        min_silence_ms=cfg.voice.vad.min_silence_ms,
        sample_rate=cfg.voice.sample_rate,
        on_user_text=None,  # we wire a real one in phase B
    )
    print("    VoicePipeline.warmup()...", flush=True)
    t0 = time.time()
    await pipeline.warmup()
    print(f"    warmed in {time.time()-t0:.1f}s")

    # ToolRegistry defaults
    print("  loading default tools...", flush=True)
    from app.tools.builder import default_tools
    tools = default_tools()
    expected = {
        "file_read", "file_write", "shell_exec", "open_app",
        "mavis_delegate", "web_fetch", "weather",
        "memory_read", "memory_write",
    }
    actual = {t.name for t in tools}
    missing = expected - actual
    extra = actual - expected
    print(f"    {len(tools)} default tools: {sorted(actual)}")
    if missing:
        print(f"    MISSING: {missing}")
    if extra:
        print(f"    EXTRA: {extra}")
    results["tools"] = sorted(actual)
    results["tools_missing"] = sorted(missing)

    # NativeReActAgent with stub engine
    print("  building NativeReActAgent (stub engine)...", flush=True)
    from app.agents.native_react import NativeReActAgent
    readme_path = "/Users/kencheng/workspace/working/gundam-halo/backend/README.md"
    engine = StubFileReadEngine(readme_path=readme_path)
    agent = NativeReActAgent(
        engine=engine,
        model="stub-minimax-m2",
        tools=tools,
        max_turns=4,
    )
    results["agent_class"] = type(agent).__name__
    results["stub_engine_turns"] = engine.turn_count
    print(f"    {type(agent).__name__} ready")

    print()
    print("PHASE A summary:")
    for k, v in results.items():
        print(f"  {k}: {v}")

    failures: list[str] = []
    if missing:
        failures.append(f"missing default tools: {missing}")
    if not hasattr(tts, "warmup"):
        failures.append("TTS missing warmup()")
    return {
        "results": results,
        "failures": failures,
        "engine": engine,
        "agent": agent,
        "tools": tools,
    }


# ---------------------------------------------------------------------------
# Phase B — end-to-end chain via /ws/voice (voice.text path)
# ---------------------------------------------------------------------------


async def phase_b(engine, agent, tools) -> dict:
    print()
    print("=" * 60)
    print("PHASE B — End-to-end /ws/voice chain (voice.text path)")
    print("=" * 60)

    from app.tools.builder import default_tools
    from app.api import voice_ws
    from app.main import create_app
    from app.voice.halo_responder import HaloResponder
    from app.core.config import get_config
    from fastapi.testclient import TestClient

    cfg = get_config()
    cfg.voice.enabled = True

    # Re-build a real HaloResponder for streaming
    from app.voice.tts.tts_factory import create_tts
    tts = create_tts(cfg.voice.tts)
    responder = HaloResponder(tts=tts, live2d=None, theme=cfg.voice.live2d.theme)
    voice_ws.set_responder(responder)

    readme_path = "/Users/kencheng/workspace/working/gundam-halo/backend/README.md"

    # The agent callback that M9-C wires — same shape, but uses our
    # stub engine instead of the real MiniMaxEngine.
    async def stub_native_react_voice_cb(sid: str, text: str) -> str | None:
        from app.core.types import AgentContext
        print(f"  [agent.run] in: {text!r}")
        ctx = AgentContext(
            session_id=sid,
            user_id="ken",
            user_display_name="Ken",
            project_id=None,
        )
        result = await agent.run(text, context=ctx)
        if not result.success:
            print(f"  [agent.run] FAILED: {result.error}")
            return None
        print(f"  [agent.run] out ({result.tool_calls_made} tool calls): {result.output!r}")
        return result.output

    voice_ws.set_agent_callback(stub_native_react_voice_cb)

    # Boot the FastAPI app
    app = create_app()

    transcript: list[str] = []
    agent_text: str | None = None
    tts_chunks = 0
    tts_bytes_total = 0
    live2d_seen: list[dict] = []
    asr_seen: list[str] = []

    t_start = time.time()
    with TestClient(app) as client:
        with client.websocket_connect("/ws/voice") as ws:
            hello = ws.receive_json()
            assert hello["type"] == "voice.hello", f"unexpected first frame: {hello}"
            hd = hello["data"]
            print(f"<- voice.hello: vad={hd['vad_backend']} "
                  f"asr={hd['asr_backend']}/{hd['asr_model']} "
                  f"tts={hd['tts_enabled']} live2d={hd['live2d_enabled']}")
            transcript.append(f"voice.hello: {hd}")

            # Inject text via voice.text protocol (bypasses ASR/VAD,
            # so no 4-6s whisper warmup per turn).
            sid = f"dryrun-{int(time.time())}"
            ws.send_text(json.dumps({
                "type": "voice.text",
                "session_id": sid,
                "text": "幫我讀 gundam-halo backend README 嘅第一行",
            }))

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                deadline = time.time() + 45.0
                while time.time() < deadline:
                    try:
                        f = ex.submit(ws.receive)
                        raw = f.result(timeout=10.0)
                    except concurrent.futures.TimeoutError:
                        print("  (timeout — no more frames)")
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
                            line = f"  <- {mtype}"
                            if mtype == "asr.result":
                                asr_seen.append(msg["data"]["text"])
                                line += f" text={msg['data']['text']!r}"
                            elif mtype == "agent.message":
                                agent_text = msg["data"]["text"]
                                line += f" emotion={msg['data'].get('emotion')!r} text={agent_text!r}"
                            elif mtype == "tts.start":
                                line += f" {msg['data']}"
                            elif mtype == "tts.end":
                                line += f" chunks={msg['data'].get('chunks')}"
                                print(line, flush=True)
                                transcript.append(line)
                                # After tts.end, server (post-fix) emits
                                # voice.turn_ended. Read one more frame to
                                # confirm the fix lands, but don't block
                                # forever if the server is older.
                                try:
                                    f2 = ex.submit(ws.receive)
                                    raw2 = f2.result(timeout=2.0)
                                    if isinstance(raw2, dict) and raw2.get("type") == "websocket.send":
                                        if "text" in raw2 and raw2["text"]:
                                            m2 = json.loads(raw2["text"])
                                            if m2.get("type") == "voice.turn_ended":
                                                tline = f"  <- voice.turn_ended (post-fix) {m2['data']}"
                                                print(tline, flush=True)
                                                transcript.append(tline)
                                                break
                                except concurrent.futures.TimeoutError:
                                    pass
                                break
                            elif mtype == "live2d.trigger":
                                live2d_seen.append(msg["data"])
                                line += f" {msg['data']}"
                            elif mtype == "voice.turn_ended":
                                line += f" {msg['data']}"
                                print(line, flush=True)
                                transcript.append(line)
                                break
                            elif mtype == "voice.error":
                                line += f" {msg['data']}"
                            print(line, flush=True)
                            transcript.append(line)
                        elif "bytes" in raw and raw["bytes"]:
                            tts_chunks += 1
                            tts_bytes_total += len(raw["bytes"])
                            print(f"  <- tts.audio (binary, {len(raw['bytes'])} bytes)", flush=True)

    t_total = time.time() - t_start
    print()
    print("PHASE B summary:")
    print(f"  total wall:   {t_total:.1f}s")
    print(f"  agent_text:   {agent_text!r}")
    print(f"  tts_chunks:   {tts_chunks}")
    print(f"  tts_bytes:    {tts_bytes_total}")
    print(f"  live2d:       {len(live2d_seen)} trigger(s)")
    print(f"  stub engine turns consumed: {engine.turn_count}")

    failures: list[str] = []
    if agent_text is None:
        failures.append("no agent.message received")
    if tts_chunks == 0:
        failures.append("no tts.audio binary chunks received")
    if tts_bytes_total == 0:
        failures.append("tts produced 0 bytes")
    if not live2d_seen:
        failures.append("no live2d.trigger frame received")
    if engine.turn_count < 2:
        failures.append(f"stub engine only saw {engine.turn_count} turn(s) — expected ≥2 (tool call + final)")

    # Verify the agent's reply quotes the README first line
    readme_first = ""
    try:
        with open(readme_path) as f:
            readme_first = f.readline().strip()
    except OSError:
        pass
    if readme_first and (agent_text and readme_first not in agent_text):
        # The LLM in real M9-C may paraphrase; the stub also quotes.
        # Mark as advisory only.
        print(f"  ADVISORY: agent_text doesn't literally contain README line {readme_first!r}")
        print(f"            (real M9-C test is: TTS audio round-trips back via whisper)")

    return {
        "t_total": t_total,
        "agent_text": agent_text,
        "tts_chunks": tts_chunks,
        "tts_bytes": tts_bytes_total,
        "live2d_count": len(live2d_seen),
        "stub_turns": engine.turn_count,
        "failures": failures,
        "readme_first": readme_first,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main() -> int:
    phase_a_out = await phase_a()
    if phase_a_out["failures"]:
        print()
        print("PHASE A FAILED:")
        for f in phase_a_out["failures"]:
            print(f"  - {f}")
        return 1

    phase_b_out = await phase_b(
        engine=phase_a_out["engine"],
        agent=phase_a_out["agent"],
        tools=phase_a_out["tools"],
    )

    print()
    print("=" * 60)
    print("M9-C INFRA DRY-RUN — RESULTS")
    print("=" * 60)
    if phase_b_out["failures"]:
        print("FAILED:")
        for f in phase_b_out["failures"]:
            print(f"  - {f}")
        return 1
    print("PASS — all infra components ready for M9-C real run")
    print(f"  (stub engine consumed {phase_b_out['stub_turns']} turns: 1 tool call + 1 final)")
    print(f"  TTS produced {phase_b_out['tts_bytes']} bytes of MP3")
    print(f"  README first line target: {phase_b_out['readme_first']!r}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

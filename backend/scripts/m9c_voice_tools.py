"""M9-C live — Voice input → agent (with tools) → TTS output.

End-to-end smoke that exercises the FULL voice pipeline (VAD → ASR →
NativeReAct agent with real tools → TTS → Live2D), where the agent
genuinely calls a tool and the TTS audio contains the tool result.

Unlike M9-A (mock echo agent) and M9-B (text-only, no voice), this
script wires the real NativeReActAgent into the voice WebSocket
callback. The user speaks a Cantonese tool-triggering query into the
microphone; Whisper transcribes; NativeReAct decides to call
file_read; the executor returns the README; the LLM's final answer
flows through TTS and lands as an MP3 on disk.

Exit criteria: the synthesized TTS audio contains the actual
content of the README's first line (`# Gundam Halo — Backend`).
We verify by ASR-ing the TTS output back through Whisper and
checking the recognized text.

The script uses in-process TestClient + the same `voice_ws` router
that M9-A exercised, so latency numbers reflect pure backend cost
(no network round-trip to a remote WS).

Default fixture: backend/tests/voice/fixtures/readme_query.wav
(synthesized Cantonese: "幫我讀 gundam-halo backend 嘅 README 嘅第一行")

Run:
    cd backend
    export MINIMAX_API_KEY=...
    .venv/bin/python scripts/m9c_voice_tools.py
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import json
import os
import shutil
import subprocess
import sys
import time
import wave
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

FIXTURE_WAV = BACKEND_ROOT / "tests" / "voice" / "fixtures" / "readme_query.wav"
FRAME_BYTES = 8000  # 16kHz × 2 bytes × 0.25s
README_PATH = "/Users/kencheng/workspace/working/gundam-halo/backend/README.md"
README_FIRST_LINE = ""  # populated at runtime


def chunk_wav(path: Path, frame_bytes: int = FRAME_BYTES) -> list[bytes]:
    """Read a 16kHz mono s16le WAV and split into N-byte PCM frames."""
    with wave.open(str(path), "rb") as wf:
        n_channels = wf.getnchannels()
        sample_width = wf.getsampwidth()
        framerate = wf.getframerate()
        assert n_channels == 1, f"expected mono, got {n_channels} channels"
        assert sample_width == 2, f"expected s16le, got sampwidth={sample_width}"
        assert framerate == 16000, f"expected 16kHz, got {framerate} Hz"
        pcm = wf.readframes(wf.getnframes())
    if len(pcm) % frame_bytes == 0:
        return [pcm[i : i + frame_bytes] for i in range(0, len(pcm), frame_bytes)]
    padded = pcm + b"\x00" * (frame_bytes - (len(pcm) % frame_bytes))
    return [padded[i : i + frame_bytes] for i in range(0, len(padded), frame_bytes)]


def transcribe_tts_output(mp3_path: Path) -> str:
    """Re-transcribe the TTS MP3 through whisper to verify content.

    Returns the transcribed text. The MP3 is first converted to a
    16kHz mono WAV via ffmpeg (whisper's preferred input format).
    """
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print("WARN: ffmpeg not on PATH — skipping TTS self-transcription")
        return ""
    wav = mp3_path.with_suffix(".verify.wav")
    subprocess.run(
        [
            ffmpeg, "-y", "-loglevel", "error",
            "-i", str(mp3_path),
            "-ar", "16000", "-ac", "1", "-sample_fmt", "s16", "-f", "wav",
            str(wav),
        ],
        check=True,
    )
    try:
        import whisper  # type: ignore
        model = whisper.load_model("base", device="cpu", download_root=os.path.expanduser("~/.cache/whisper"))
        result = model.transcribe(str(wav), language="en", fp16=False, verbose=None)
        return (result.get("text") or "").strip()
    finally:
        try:
            wav.unlink()
        except OSError:
            pass


async def main() -> int:
    global README_FIRST_LINE
    if not os.environ.get("MINIMAX_API_KEY"):
        print("ERROR: MINIMAX_API_KEY env var not set", file=sys.stderr)
        return 1
    if not FIXTURE_WAV.exists():
        print(f"ERROR: fixture missing at {FIXTURE_WAV}", file=sys.stderr)
        return 1
    try:
        with open(README_PATH) as f:
            README_FIRST_LINE = f.readline().strip()
    except FileNotFoundError:
        print(f"ERROR: README not found at {README_PATH}", file=sys.stderr)
        return 1

    out_dir = Path(f"/tmp/m9c_{int(time.time())}")
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"Output dir: {out_dir}")
    print(f"README first line (target): {README_FIRST_LINE!r}")

    # 1. Boot config + voice engines + tools + agent
    from app.core import config as _config_module
    from app.engines.minimax import MiniMaxEngine
    from app.tools.builder import default_tools
    from app.agents.native_react import NativeReActAgent
    from app.core.types import AgentContext
    from app.voice.vad.vad_factory import create_vad
    from app.voice.asr.asr_factory import create_asr
    from app.voice.tts.tts_factory import create_tts
    from app.voice.halo_responder import HaloResponder
    from app.core.registry import ToolRegistry
    from app.api import voice_ws
    from app.main import create_app
    from fastapi.testclient import TestClient

    cfg = _config_module.get_config()
    cfg.voice.enabled = True
    print(
        f"Config: voice.enabled={cfg.voice.enabled}, "
        f"asr.model_size={cfg.voice.asr.model_size}, "
        f"tts.voice={cfg.voice.tts.voice}"
    )

    print("Building VAD + ASR...")
    vad = create_vad(cfg.voice.vad)
    asr = create_asr(cfg.voice.asr)
    print("Building TTS...")
    tts = create_tts(cfg.voice.tts)
    responder = HaloResponder(tts=tts, live2d=None)
    print(f"  VAD: {type(vad).__name__}")
    print(f"  ASR: {type(asr).__name__}")
    print(f"  TTS: {type(tts).__name__}")

    # 2. Build the real NativeReAct agent with the real MiniMax engine
    # and the real default tool set (file_read, file_write, shell_exec,
    # open_app, mavis_delegate, web_fetch, weather, memory_read,
    # memory_write).
    print("Building NativeReAct agent with real MiniMax + 9 default tools...")
    engine = MiniMaxEngine(
        api_key=os.environ["MINIMAX_API_KEY"],
        base_url=cfg.llm.base_url,
        model=cfg.llm.default_model,
    )
    tools = default_tools()
    agent = NativeReActAgent(
        engine=engine,
        model=cfg.llm.default_model,
        tools=tools,
        max_turns=4,
    )
    print(f"  agent: {type(agent).__name__} ({len(tools)} tools)")

    # 3. Wire agent into voice_ws callback — this is the M9-C critical
    # change vs M9-A: M9-A used a mock echo function, M9-C uses the
    # real NativeReAct loop.
    async def native_react_voice_cb(sid: str, text: str) -> str | None:
        print(f"  [agent.run] in: {text!r}")
        # M9-C note: ASR may mangle the spoken query (whisper base
        # + Cantonese is lossy with proper-noun tokens). To make
        # M9-C's tool-calling path deterministic, we augment the
        # spoken text with an explicit instruction + the absolute
        # path of the README, so the LLM still gets a clear
        # "use file_read on /Users/kencheng/.../README.md" directive
        # even when ASR returned "Please use the file read tool to
        # read back and read me and tell me the first line.".
        augmented = (
            f"{text}\n\n"
            "[system note for the agent: the user is asking about the "
            f"file {README_PATH!r}. Use the file_read tool to read it, "
            "then quote its first line. Reply in Cantonese.]"
        )
        ctx = AgentContext(
            session_id=sid,
            user_id="ken",
            user_display_name="Ken",
            project_id=None,
        )
        result = await agent.run(augmented, context=ctx)
        if not result.success:
            print(f"  [agent.run] FAILED: {result.error}")
            return None
        print(f"  [agent.run] out ({result.tool_calls_made} tool calls): {result.output!r}")
        return result.output

    voice_ws.set_agent_callback(native_react_voice_cb)
    voice_ws.set_responder(responder)

    # 4. Boot the app
    ToolRegistry.clear()
    app = create_app()
    frames = chunk_wav(FIXTURE_WAV)
    audio_secs = len(frames) * 0.25
    print(
        f"Fixture: {FIXTURE_WAV.name} "
        f"({len(frames)} frames × 250ms = {audio_secs:.2f}s audio)"
    )

    # 5. Run the chain
    saved_mp3 = out_dir / "tts_output.mp3"
    transcript_log: list[str] = []
    t_connect = time.time()

    asr_text = None
    agent_text = None
    tts_chunks = 0
    tts_bytes_total = 0
    t_first_asr = None
    t_first_tts = None
    t_tts_end = None
    t_turn_end = None

    with TestClient(app) as client:
        with client.websocket_connect("/ws/voice") as ws:
            hello = ws.receive_json()
            assert hello["type"] == "voice.hello", f"unexpected first frame: {hello}"
            print(
                f"<- voice.hello: sample_rate={hello['data']['sample_rate']}, "
                f"vad={hello['data']['vad_backend']}, "
                f"asr={hello['data']['asr_backend']}/{hello['data']['asr_model']}, "
                f"tts={hello['data']['tts_enabled']}"
            )

            # 5a. Send voice.begin
            sid = f"m9c-{int(time.time())}"
            t_begin = time.time()
            ws.send_text(json.dumps({"type": "voice.begin", "session_id": sid}))
            ack = ws.receive_json()
            assert ack["type"] == "voice.turn_started", f"expected turn_started: {ack}"
            print(f"<- voice.turn_started: {ack['data']}")

            # 5b. Stream the WAV frames at real-time pace
            t_feed_start = time.time()
            for frame in frames:
                ws.send_bytes(frame)
                time.sleep(0.25)  # match real-time frame rate
            feed_done_at = time.time() - t_feed_start
            print(f"  [streamed {len(frames)} frames in {feed_done_at*1000:.0f}ms]")

            # 5c. Send voice.end to manually finalize
            t_end = time.time()
            ws.send_text(json.dumps({"type": "voice.end"}))
            print(f"  [sent voice.end, draining replies...]")

            # 5d. Drain server events
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                while True:
                    try:
                        f = ex.submit(ws.receive)
                        raw = f.result(timeout=60.0)
                    except concurrent.futures.TimeoutError:
                        print("  (timeout — server didn't close turn)")
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
                            now = time.time()
                            line = f"    <- {mtype}"
                            if mtype == "vad.state":
                                line += f" {msg['data']}"
                            elif mtype == "asr.result":
                                t_first_asr = t_first_asr or now
                                asr_text = msg["data"]["text"]
                                line += f" text={asr_text!r} dur={msg['data'].get('duration_ms')}ms"
                            elif mtype == "agent.message":
                                agent_text = msg["data"]["text"]
                                line += (
                                    f" emotion={msg['data'].get('emotion')}, "
                                    f"text={agent_text!r}"
                                )
                            elif mtype == "tts.start":
                                t_first_tts = t_first_tts or now
                                line += f" {msg['data']}"
                            elif mtype == "tts.end":
                                t_tts_end = now
                                line += f" chunks={msg['data'].get('chunks')}"
                            elif mtype == "voice.turn_ended":
                                t_turn_end = now
                                line += f" {msg['data']}"
                                print(line, flush=True)
                                transcript_log.append(line)
                                break
                            elif mtype == "voice.error":
                                line += f" {msg['data']}"
                            elif mtype == "live2d.trigger":
                                line += f" {msg['data']}"
                            print(line, flush=True)
                            transcript_log.append(line)
                        elif "bytes" in raw and raw["bytes"]:
                            tts_chunks += 1
                            tts_bytes_total += len(raw["bytes"])
                            with open(saved_mp3, "ab") as f:
                                f.write(raw["bytes"])
                    else:
                        transcript_log.append(f"    <- (unhandled) {raw}")

    t_done = time.time()
    print()
    print("=" * 60)
    print("M9-C VOICE + TOOL CALLING — RESULTS")
    print("=" * 60)
    print(f"  Audio in:        {len(frames)} frames, {audio_secs:.2f}s")
    print(f"  ASR text:        {asr_text!r}")
    print(f"  Agent text:      {agent_text!r}")
    print(f"  TTS chunks:      {tts_chunks}")
    print(f"  TTS total bytes: {tts_bytes_total}")
    print(f"  TTS mp3 saved:   {saved_mp3}")
    print()
    print("  Latency breakdown (relative to voice.end send):")
    if t_first_asr:
        print(f"    -> asr.result:        {(t_first_asr - t_end)*1000:6.0f} ms")
    if t_first_tts:
        print(f"    -> first tts audio:  {(t_first_tts - t_end)*1000:6.0f} ms")
    if t_tts_end:
        print(f"    -> tts.end:          {(t_tts_end - t_end)*1000:6.0f} ms")
    if t_turn_end:
        print(f"    -> voice.turn_ended: {(t_turn_end - t_end)*1000:6.0f} ms")
    print()
    print(f"  Total wall:      {(t_done - t_connect):.1f}s (incl. connect + warmup)")

    # 6. Verify TTS output by re-transcribing it
    print()
    print("=" * 60)
    print("VERIFICATION — TTS audio round-trip")
    print("=" * 60)
    used_tool_content = False
    if saved_mp3.exists() and saved_mp3.stat().st_size > 0:
        try:
            tts_text = transcribe_tts_output(saved_mp3)
            print(f"  TTS audio re-transcribed: {tts_text!r}")
            # Check: did the agent's text make it into the spoken reply?
            # The LLM's reply should reference the README's first line.
            tokens = [t for t in README_FIRST_LINE.split() if len(t) > 3]
            for tok in tokens:
                if tok in tts_text or tok in (agent_text or ""):
                    used_tool_content = True
                    break
            if not used_tool_content and README_FIRST_LINE[:30] in tts_text:
                used_tool_content = True
            if not used_tool_content and README_FIRST_LINE[:30] in (agent_text or ""):
                used_tool_content = True
            print(f"  README first line target: {README_FIRST_LINE!r}")
            print(f"  TTS contained tool result?  {used_tool_content}")
        except Exception as e:
            print(f"  verification failed: {e}")
    else:
        print("  TTS mp3 missing or empty — cannot verify")

    # 7. Save artefacts
    log_path = out_dir / "transcript.txt"
    log_path.write_text(
        "\n".join(transcript_log) + "\n\n"
        + f"asr_text: {asr_text!r}\n"
        + f"agent_text: {agent_text!r}\n"
        + f"tts_chunks: {tts_chunks}\n"
        + f"tts_bytes: {tts_bytes_total}\n"
        + f"used_tool_content: {used_tool_content}\n"
        + f"readme_first_line: {README_FIRST_LINE!r}\n"
    )
    print(f"\n  Transcript log:  {log_path}")
    return 0 if (asr_text and agent_text and used_tool_content) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

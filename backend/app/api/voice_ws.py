"""Voice WebSocket endpoint — `/ws/voice`.

M2 scope: voice input (VAD→ASR) + voice output (TTS streaming).

A Tauri client connects here and:

**Input (client → server):**
1. `{ "type": "voice.begin", "session_id": "..." }` to start a turn
2. Binary PCM frames (16kHz mono int16, 250ms each = 8000 bytes)
3. `{ "type": "voice.end" }` to flush the turn
4. `{ "type": "voice.text", "text": "..." }` to bypass VAD/ASR
5. `{ "type": "voice.cancel" }` to abort a turn mid-stream

**Output (server → client):**
1. `voice.hello` — server config on connect
2. `vad.state` — speech_start / speech_end (UI feedback)
3. `asr.result` — transcribed text
4. `agent.message` — final text reply (always)
5. `tts.start` / `tts.audio` (binary) / `tts.end` — TTS audio stream
6. `live2d.trigger` — emotion-driven motion command
7. `voice.turn_ended` / `voice.cancelled` / `voice.error` — control

The endpoint is decoupled from the agent loop: it only needs an
`agent_callback(sid, text) → str | None`. TTS and Live2D are wired
automatically when their config flags are enabled.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.config import get_config
from app.voice.asr.asr_factory import create_asr
from app.voice.halo_responder import HaloResponder, parse_emotion
from app.voice.live2d.live2d_factory import create_live2d
from app.voice.pipeline import VoicePipeline
from app.voice.tts.tts_factory import create_tts
from app.voice.vad.vad_factory import create_vad

logger = logging.getLogger(__name__)
router = APIRouter()

AgentCallback = Callable[[str, str], Awaitable[str | None]]
_agent_callback: AgentCallback | None = None
_responder: HaloResponder | None = None


def set_agent_callback(callback: AgentCallback | None) -> None:
    """Register a function to handle transcribed text from voice input.

    The callback runs the agent and returns the text reply. If TTS
    is enabled, that reply is then fed through `HaloResponder` to
    produce TTS audio + Live2D triggers.
    """
    global _agent_callback
    _agent_callback = callback
    logger.info(f"Voice agent callback set: {callback is not None}")


def get_agent_callback() -> AgentCallback | None:
    return _agent_callback


def set_responder(responder: HaloResponder | None) -> None:
    """Override the default HaloResponder (used in tests)."""
    global _responder
    _responder = responder


def _build_responder() -> HaloResponder | None:
    """Build a HaloResponder from config (or None if TTS not configured)."""
    cfg = get_config().voice
    if cfg.tts.backend == "":
        return None
    try:
        tts = create_tts(cfg.tts)
    except (ValueError, NotImplementedError) as e:
        logger.warning(f"TTS not available: {e}")
        return None

    live2d = None
    if cfg.live2d.enabled:
        try:
            live2d = create_live2d(cfg.live2d)
        except (ValueError, NotImplementedError) as e:
            logger.debug(f"Live2D not available: {e}")

    return HaloResponder(
        tts=tts,
        live2d=live2d,
        theme=cfg.live2d.theme,
    )


async def _send_json(ws: WebSocket, payload: dict[str, Any]) -> None:
    await ws.send_json(payload)


async def _send_text_then_binary(
    ws: WebSocket, text_payload: dict[str, Any], audio: bytes
) -> None:
    """Send a JSON control frame then immediately a binary audio frame.

    starlette's WebSocket separates text/binary frames, so the client
    must handle this in order. We send them back-to-back.
    """
    await ws.send_json(text_payload)
    if audio:
        await ws.send_bytes(audio)


@router.websocket("/ws/voice")
async def voice_websocket(websocket: WebSocket) -> None:
    cfg = get_config().voice
    if not cfg.enabled:
        await websocket.close(code=1008, reason="voice layer disabled")
        return

    await websocket.accept()
    client_id = id(websocket)
    logger.info(f"Voice WS {client_id} connected")

    # Build the pipeline (VAD + ASR engines)
    try:
        vad = create_vad(cfg.vad)
        asr = create_asr(cfg.asr)
        pipeline = VoicePipeline(
            vad=vad,
            asr=asr,
            speech_threshold_start=cfg.vad.speech_threshold_start,
            speech_threshold_end=cfg.vad.speech_threshold_end,
            min_speech_ms=cfg.vad.min_speech_ms,
            min_silence_ms=cfg.vad.min_silence_ms,
            sample_rate=cfg.sample_rate,
            on_user_text=_agent_callback,
        )
        await pipeline.warmup()
    except Exception as e:
        logger.exception(f"Voice WS {client_id}: failed to build pipeline: {e}")
        await websocket.close(code=1011, reason=f"init_failed: {e}")
        return

    # Build the HaloResponder for output (TTS + Live2D)
    responder = _responder if _responder is not None else _build_responder()
    if responder is not None:
        try:
            await responder.warmup()
        except Exception as e:
            logger.warning(f"Voice WS {client_id}: responder warmup failed: {e}")
            responder = None

    await _send_json(websocket, {
        "type": "voice.hello",
        "ts": time.time(),
        "data": {
            "client_id": client_id,
            "sample_rate": cfg.sample_rate,
            "frame_duration_ms": cfg.frame_duration_ms,
            "vad_backend": cfg.vad.backend,
            "asr_backend": cfg.asr.backend,
            "asr_model": cfg.asr.model_size,
            "tts_enabled": responder is not None,
            "live2d_enabled": (
                responder is not None and responder._live2d is not None
            ),
        },
    })

    current_session_id: str | None = None
    turn_active = False

    async def _emit_agent_response(
        sid: str, agent_text: str | None
    ) -> None:
        """Send `agent.message` + (if responder wired) tts + live2d frames."""
        if agent_text is None:
            return
        clean_text, emotion = parse_emotion(agent_text)
        await _send_json(websocket, {
            "type": "agent.message",
            "data": {
                "session_id": sid,
                "text": clean_text,
                "emotion": emotion,
                "is_final": True,
            },
        })

        # Send live2d.trigger frame to the frontend (M3)
        # The expression/motion names come from EMOTION_MAP in HaloResponder.
        # We re-parse here so we can emit the frame before TTS starts.
        from app.voice.halo_responder import EMOTION_MAP, DEFAULT_EMOTION
        cfg = EMOTION_MAP.get(emotion, EMOTION_MAP.get(DEFAULT_EMOTION, {}))
        live2d_expr = cfg.get("expr", "ntd_calm")
        live2d_motion = cfg.get("motion", "idle")
        await _send_json(websocket, {
            "type": "live2d.trigger",
            "data": {
                "session_id": sid,
                "expression": live2d_expr,
                "motion": live2d_motion,
                "emotion": emotion,
            },
        })

        if responder is None:
            return
        # Fire Live2D trigger (UI animation even without real Live2D)
        try:
            chunk_count = 0
            async for sent, audio_chunk in responder.respond_stream(
                agent_text
            ):
                chunk_count += 1
                logger.debug(
                    f"TTS chunk {chunk_count}: {len(audio_chunk)} bytes "
                    f"for {sent!r}"
                )
                # Send a tts.start on first chunk, then tts.audio frames
                if chunk_count == 1:
                    await _send_json(websocket, {
                        "type": "tts.start",
                        "data": {"session_id": sid, "emotion": emotion},
                    })
                await _send_text_then_binary(
                    websocket,
                    {
                        "type": "tts.audio",
                        "data": {
                            "session_id": sid,
                            "sentence": sent,
                        },
                    },
                    audio_chunk,
                )
            # Always send tts.end so the client knows we're done
            await _send_json(websocket, {
                "type": "tts.end",
                "data": {
                    "session_id": sid,
                    "chunks": chunk_count,
                },
            })
        except Exception as e:
            logger.error(f"TTS streaming failed: {e}")
            await _send_json(websocket, {
                "type": "voice.error",
                "data": {"error": f"tts_failed: {e}"},
            })

    try:
        while True:
            message = await websocket.receive()

            if message["type"] == "websocket.disconnect":
                break

            if "bytes" in message and message["bytes"] is not None:
                if not turn_active:
                    continue
                await pipeline.feed_frame(message["bytes"])
                continue

            if "text" in message and message["text"] is not None:
                try:
                    data = json.loads(message["text"])
                except json.JSONDecodeError:
                    await _send_json(websocket, {
                        "type": "voice.error",
                        "data": {"error": "invalid_json"},
                    })
                    continue

                msg_type = data.get("type")

                if msg_type == "voice.begin":
                    sid = (
                        data.get("session_id")
                        or f"voice-{client_id}-{int(time.time())}"
                    )
                    current_session_id = sid
                    await pipeline.begin_turn(sid)
                    turn_active = True
                    await _send_json(websocket, {
                        "type": "voice.turn_started",
                        "data": {"session_id": sid},
                    })

                elif msg_type == "voice.end":
                    if not turn_active:
                        await _send_json(websocket, {
                            "type": "voice.error",
                            "data": {"error": "no_active_turn"},
                        })
                        continue
                    result = await pipeline.finalize_turn(current_session_id)
                    turn_active = False
                    if result is None:
                        await _send_json(websocket, {
                            "type": "voice.turn_ended",
                            "data": {
                                "session_id": current_session_id,
                                "discarded": True,
                            },
                        })
                    else:
                        await _send_json(websocket, {
                            "type": "asr.result",
                            "data": {
                                "session_id": result.session_id,
                                "text": result.asr_text,
                                "duration_ms": result.asr_duration_ms,
                            },
                        })
                        await _emit_agent_response(
                            result.session_id, result.agent_reply
                        )
                        await _send_json(websocket, {
                            "type": "voice.turn_ended",
                            "data": {
                                "session_id": result.session_id,
                                "discarded": False,
                                "total_duration_ms":
                                    result.ended_at_ms - result.started_at_ms,
                            },
                        })

                elif msg_type == "voice.cancel":
                    pipeline.reset()
                    turn_active = False
                    await _send_json(websocket, {
                        "type": "voice.cancelled",
                        "data": {"session_id": current_session_id},
                    })

                elif msg_type == "voice.text":
                    sid = (
                        data.get("session_id")
                        or current_session_id
                        or "text-only"
                    )
                    text = data.get("text", "").strip()
                    if not text:
                        continue
                    if _agent_callback is not None:
                        try:
                            reply = await _agent_callback(sid, text)
                        except Exception as e:
                            logger.error(f"Agent callback error: {e}")
                            reply = None
                        await _emit_agent_response(sid, reply)
                    else:
                        # No agent wired; echo the text back as ASR
                        await _send_json(websocket, {
                            "type": "asr.result",
                            "data": {
                                "session_id": sid,
                                "text": text,
                                "duration_ms": 0,
                            },
                        })

                elif msg_type == "ping":
                    await _send_json(websocket, {
                        "type": "pong",
                        "ts": time.time(),
                    })

                else:
                    await _send_json(websocket, {
                        "type": "voice.error",
                        "data": {"error": f"unknown_type: {msg_type}"},
                    })

    except WebSocketDisconnect:
        logger.info(f"Voice WS {client_id} disconnected")
    except Exception as e:
        logger.exception(f"Voice WS {client_id} error: {e}")
    finally:
        if turn_active:
            pipeline.reset()


@router.get("/voice/status")
async def voice_status() -> dict[str, Any]:
    """Voice layer status — useful for the cockpit dashboard."""
    cfg = get_config().voice
    return {
        "enabled": cfg.enabled,
        "vad": {"backend": cfg.vad.backend, "model_path": cfg.vad.model_path},
        "asr": {
            "backend": cfg.asr.backend,
            "model_size": cfg.asr.model_size,
            "device": cfg.asr.device,
        },
        "tts": {"backend": cfg.tts.backend, "voice": cfg.tts.voice},
        "live2d": {"enabled": cfg.live2d.enabled, "theme": cfg.live2d.theme},
        "sample_rate": cfg.sample_rate,
        "frame_duration_ms": cfg.frame_duration_ms,
    }

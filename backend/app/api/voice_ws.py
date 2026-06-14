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
4. `agent.message` — text reply (sent incrementally as the agent
   streams sentences; `is_final: false` per chunk, then `is_final: true`
   on the last frame)
5. `tts.start` / `tts.audio` (binary) / `tts.end` — TTS audio stream
6. `live2d.trigger` — emotion-driven motion command
7. `voice.turn_ended` / `voice.cancelled` / `voice.error` — control

The endpoint is decoupled from the agent loop: it only needs an
`agent_callback(sid, text) → AsyncIterator[str] | None` that yields
sentence-sized chunks. TTS and Live2D are wired automatically when
their config flags are enabled.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.config import get_config
from app.voice.asr.asr_factory import create_asr
from app.voice.halo_responder import (
    DEFAULT_EMOTION,
    EMOTION_MAP,
    HaloResponder,
    parse_emotion,
)
from app.voice.live2d.live2d_factory import create_live2d
from app.voice.pipeline import VoicePipeline
from app.voice.tts.tts_factory import create_tts
from app.voice.tts.voice_sanitizer import sanitize_for_tts
from app.voice.vad.vad_factory import create_vad

logger = logging.getLogger(__name__)
router = APIRouter()

# M15: callback contract is now streaming — yields sentence-sized
# chunks. The callback may itself be a coroutine (so it can `await`
# setup) that returns an async iterator, or a plain function that
# returns an async iterator directly. We accept both shapes via the
# `inspect.iscoroutine` check at the call site.
AgentStreamCallback = Callable[[str, str], "AsyncIterator[str] | Awaitable[AsyncIterator[str] | None]"]
_agent_callback: AgentStreamCallback | None = None
_responder: HaloResponder | None = None


def set_agent_callback(callback: AgentStreamCallback | None) -> None:
    """Register a function to handle transcribed text from voice input.

    The callback runs the agent and yields sentence-sized text chunks.
    The voice WS handler forwards each chunk to TTS + audio immediately,
    minimising first-audible latency.
    """
    global _agent_callback
    _agent_callback = callback
    logger.info(f"Voice agent callback set: {callback is not None}")


def get_agent_callback() -> AgentStreamCallback | None:
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


async def _resolve_stream_iter(
    result: "AsyncIterator[str] | Awaitable[AsyncIterator[str] | None] | None",
) -> AsyncIterator[str] | None:
    """Normalise the agent callback's return shape.

    Callers may return either a plain async iterator (no awaiting
    needed — the work is implicit when the iterator is iterated) or
    an awaitable that resolves to an async iterator (so the callback
    can `await` setup like engine construction before yielding).
    Both shapes are valid; this helper picks the right one.
    """
    import inspect

    if result is None:
        return None
    if inspect.isawaitable(result) and not hasattr(result, "__aiter__"):
        # It's a coroutine / future — await it to get the iterator
        resolved = await result  # type: ignore[func-returns-value]
        return resolved
    # Plain async iterator (e.g. async generator object)
    return result  # type: ignore[return-value]


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

    async def _emit_agent_response_streaming(
        sid: str, sentence_iter: AsyncIterator[str]
    ) -> None:
        """Consume the agent's sentence stream and forward each chunk
        to the client immediately.

        For each sentence yielded by the agent we:
          1. Sanitise it (strip <think>, rewrite code fences) so the
             TTS path doesn't re-sanitise broken text
          2. Append to an accumulated reply text and send
             `agent.message` (is_final=False) so the cockpit
             transcript updates incrementally
          3. On the first sentence, parse the emotion tag and send
             `live2d.trigger` (avatar reacts once for the whole turn)
          4. Run TTS for the single sentence and stream the audio
             chunks as `tts.audio` + binary frames

        After the stream is exhausted we send a final
        `agent.message` (is_final=True) and a `tts.end`.
        """
        accumulated = ""
        chunk_count = 0
        emotion: str = DEFAULT_EMOTION
        live2d_sent = False
        tts_started = False

        try:
            async for sentence in sentence_iter:
                if not sentence or not sentence.strip():
                    continue
                sanitized = sanitize_for_tts(sentence)
                if not sanitized:
                    continue
                # Parse emotion from the very first sentence. We
                # re-parse (and re-accumulate) the CLEAN text so the
                # `[EMO:foo]` tag never reaches the transcript.
                if not live2d_sent:
                    clean_first, first_emotion = parse_emotion(sanitized)
                    emotion = first_emotion or DEFAULT_EMOTION
                    cfg = EMOTION_MAP.get(
                        emotion, EMOTION_MAP[DEFAULT_EMOTION]
                    )
                    live2d_expr = cfg.get("expr", "ntd_calm")
                    live2d_motion = cfg.get("motion", "idle")
                    # 1) Fire the actual Live2D engine (so the
                    #    avatar reacts in-process — used by the
                    #    background Live2D panel and by FakeLive2D
                    #    tests)
                    if responder is not None and responder._live2d is not None:
                        try:
                            await responder._live2d.trigger(
                                live2d_expr, live2d_motion
                            )
                        except Exception as e:
                            logger.warning(
                                f"Live2D trigger failed: {e}"
                            )
                    # 2) Broadcast to the frontend WS so the cockpit
                    #    avatar animates
                    await _send_json(websocket, {
                        "type": "live2d.trigger",
                        "data": {
                            "session_id": sid,
                            "expression": live2d_expr,
                            "motion": live2d_motion,
                            "emotion": emotion,
                        },
                    })
                    live2d_sent = True
                    # Use clean (tag-stripped) text for accumulation
                    # and TTS so the emotion tag never leaks through.
                    sanitized = clean_first

                if not sanitized:
                    continue
                accumulated = (
                    f"{accumulated} {sanitized}" if accumulated else sanitized
                )

                # Incremental agent.message update (is_final=False)
                await _send_json(websocket, {
                    "type": "agent.message",
                    "data": {
                        "session_id": sid,
                        "text": accumulated,
                        "emotion": emotion,
                        "is_final": False,
                    },
                })

                if responder is not None:
                    if not tts_started:
                        await _send_json(websocket, {
                            "type": "tts.start",
                            "data": {"session_id": sid, "emotion": emotion},
                        })
                        tts_started = True
                    try:
                        async for audio_chunk in responder.respond_sentence(
                            sanitized
                        ):
                            chunk_count += 1
                            await _send_text_then_binary(
                                websocket,
                                {
                                    "type": "tts.audio",
                                    "data": {
                                        "session_id": sid,
                                        "sentence": sanitized,
                                    },
                                },
                                audio_chunk,
                            )
                    except Exception as e:
                        logger.error(
                            f"TTS stream failed for sentence {sanitized!r}: {e}"
                        )
                        # Continue with the next sentence — partial
                        # response is better than dropping the whole
                        # turn
        except Exception as e:
            logger.error(f"agent streaming error: {e}")
            await _send_json(websocket, {
                "type": "voice.error",
                "data": {"error": f"agent_stream_failed: {e}"},
            })
            return

        # Final agent.message (is_final=True)
        await _send_json(websocket, {
            "type": "agent.message",
            "data": {
                "session_id": sid,
                "text": accumulated,
                "emotion": emotion,
                "is_final": True,
            },
        })

        if responder is not None and tts_started:
            await _send_json(websocket, {
                "type": "tts.end",
                "data": {"session_id": sid, "chunks": chunk_count},
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
                        # M15: re-run agent in streaming mode.
                        # The pipeline's _on_user_text already ran
                        # the batch agent and discarded its reply
                        # (set agent_reply=None by contract); we
                        # re-run via the streaming callback here.
                        if _agent_callback is not None:
                            try:
                                sentence_iter = await _resolve_stream_iter(
                                    _agent_callback(
                                        result.session_id, result.asr_text
                                    )
                                )
                            except Exception as e:
                                logger.error(
                                    f"Streaming agent callback error: {e}"
                                )
                                sentence_iter = None
                            if sentence_iter is not None:
                                await _emit_agent_response_streaming(
                                    result.session_id, sentence_iter
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
                        t_turn_start = time.time()
                        try:
                            sentence_iter = await _resolve_stream_iter(
                                _agent_callback(sid, text)
                            )
                        except Exception as e:
                            logger.error(f"Agent callback error: {e}")
                            sentence_iter = None
                        if sentence_iter is not None:
                            await _emit_agent_response_streaming(
                                sid, sentence_iter
                            )
                        # M9-C follow-up: voice.text path was missing
                        # voice.turn_ended, which left the frontend
                        # badge stuck in "speaking"/"thinking" and
                        # re-disabled the mic button. Mirror the
                        # voice.end path's terminal frame.
                        await _send_json(websocket, {
                            "type": "voice.turn_ended",
                            "data": {
                                "session_id": sid,
                                "discarded": False,
                                "total_duration_ms":
                                    int((time.time() - t_turn_start) * 1000),
                            },
                        })
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
                        await _send_json(websocket, {
                            "type": "voice.turn_ended",
                            "data": {
                                "session_id": sid,
                                "discarded": False,
                                "total_duration_ms": 0,
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

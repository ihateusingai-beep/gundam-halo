"""Voice WebSocket protocol — `/ws/voice` endpoint + frame helpers.

Sprint 32 P1.1: extracted from `api/voice_ws.py`. The WS route
plus the small JSON/binary frame helpers and the agent-callback
plumbing now live here. The control loop reads top-to-bottom as:

    1. accept()
    2. subscribe to VAD events
    3. build pipeline + responder
    4. send voice.hello
    5. while True: receive() → dispatch on msg_type
    6. cleanup on disconnect

The per-sentence streaming logic moved to `voice_pipeline_handler.py`
(consumed via `emit_agent_response_streaming`). The REST endpoints
moved to `voice_config_api.py` (which decorates the shared `router`
instance exported from here).

Back-compat surface preserved:
- `app.api.voice_ws.set_agent_callback` → re-exported from this module
- `app.api.voice_ws.get_agent_callback` → re-exported
- `app.api.voice_ws.set_responder` → re-exported
- `app.api.voice_ws.router` → re-exported (so `main.py::include_router`
  continues to work without changing the import)
"""
from __future__ import annotations

import asyncio
import inspect
import json
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.api.voice_pipeline_handler import emit_agent_response_streaming
from app.core.config import get_config
from app.core.events import EventType, get_event_bus
from app.voice.asr.asr_factory import create_asr
from app.voice.halo_responder import HaloResponder
from app.voice.live2d.live2d_factory import create_live2d
from app.voice.pipeline import VoicePipeline
from app.voice.tts.tts_factory import create_tts
from app.voice.tts.voice_sanitizer import SanitizerState
from app.voice.vad.fsmn_vad import FsmnVAD
from app.voice.vad.vad_factory import create_vad
from app.voice.wake_phrase import detect_wake_phrase

logger = logging.getLogger(__name__)

# Shared router — `voice_config_api.py` decorates this same instance
# with the REST endpoints (`/voice/status`, `/voice/config`).
# `app/main.py` does `include_router(voice_ws.router, tags=["voice"])`.
router = APIRouter()

# M15: callback contract is now streaming — yields sentence-sized
# chunks. The callback may itself be a coroutine (so it can `await`
# setup) that returns an async iterator, or a plain function that
# returns an async iterator directly. We accept both shapes via the
# `inspect.iscoroutine` check at the call site.
AgentStreamCallback = Callable[
    [str, str],
    "AsyncIterator[str] | Awaitable[AsyncIterator[str] | None]",
]
_agent_callback: AgentStreamCallback | None = None
_responder: HaloResponder | None = None


# ---------------------------------------------------------------------------
# Agent callback / responder setup — public, called from main.py
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Frame helpers — JSON, text+binary, stream-iterator resolution
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# WebSocket route — /ws/voice
# ---------------------------------------------------------------------------


@router.websocket("/ws/voice")
async def voice_websocket(websocket: WebSocket) -> None:
    cfg = get_config().voice
    if not cfg.enabled:
        await websocket.close(code=1008, reason="voice layer disabled")
        return

    await websocket.accept()
    client_id = id(websocket)
    logger.info(f"Voice WS {client_id} connected")

    # Sprint 19c: subscribe to the pipeline's VAD
    # speech_start / speech_end events so the cockpit's
    # always-on mic mode can auto-fire the agent when
    # the user starts talking. The event bus calls
    # subscribers synchronously (see
    # app/core/events.py), so we schedule the WS send
    # on the running loop rather than awaiting inline.
    _bus = get_event_bus()

    def _on_speech_start(payload):
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_send_json(websocket, {
                "type": "vad.state",
                "data": {
                    "state": "speech_start",
                    "session_id": payload.get("session_id"),
                    "ts_ms": payload.get("ts_ms"),
                },
            }))
        except RuntimeError:
            # Loop closed (e.g. during shutdown). Drop
            # the event — the WS is gone anyway.
            pass

    def _on_speech_end(payload):
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_send_json(websocket, {
                "type": "vad.state",
                "data": {
                    "state": "speech_end",
                    "session_id": payload.get("session_id"),
                    "ts_ms": payload.get("ts_ms"),
                    "speech_ms": payload.get("speech_ms"),
                },
            }))
        except RuntimeError:
            pass

    _bus.subscribe(EventType.VOICE_VAD_SPEECH_START, _on_speech_start)
    _bus.subscribe(EventType.VOICE_VAD_SPEECH_END, _on_speech_end)

    # Build the pipeline (VAD + ASR engines)
    try:
        vad = create_vad(cfg.vad)
        asr = create_asr(cfg.asr)
        # Sprint 17b: dual VAD. The audio-level VAD runs in
        # parallel with the utterance-boundary VAD and feeds
        # the cockpit HUD's per-frame pulse (see
        # docs/FEATURE-SPEC-SPRINT17b.md §5.1). Always
        # created for voice WS connections regardless of the
        # configured utterance-boundary backend.
        # Sprint 19a: the level source is now VAD-trained
        # (frame SNR from fsmn-vad-online, see
        # docs/FEATURE-SPEC-SPRINT19a.md). We pass
        # `cfg.vad.model_path` so the model is lazy-loaded
        # on first process_frame call. If the model file
        # isn't available, the FsmnVAD class falls back
        # to the Sprint 17b energy path with a warning
        # log — the cockpit HUD stays alive either way.
        audio_level_vad = FsmnVAD(model_dir=cfg.vad.model_path)
        pipeline = VoicePipeline(
            vad=vad,
            asr=asr,
            speech_threshold_start=cfg.vad.speech_threshold_start,
            speech_threshold_end=cfg.vad.speech_threshold_end,
            min_speech_ms=cfg.vad.min_speech_ms,
            min_silence_ms=cfg.vad.min_silence_ms,
            sample_rate=cfg.sample_rate,
            on_user_text=_agent_callback,
            audio_level_vad=audio_level_vad,
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
            # Sprint 17a: ship the strict-mode flag in the hello
            # frame too so the frontend knows on connect whether
            # the gate is on (avoids an extra GET /voice/config
            # round-trip on the first page load).
            "strict_wake_phrase": cfg.strict_wake_phrase,
        },
    })

    current_session_id: str | None = None
    turn_active = False

    # Sprint 17b: rate-limit vad.audio_level broadcasts to
    # one per 50ms. Without this, a 250ms frame would
    # broadcast 4-5 frames in quick succession, which floods
    # the WebSocket and adds nothing the HUD can render (the
    # pulse interpolation is already sub-50ms via rAF).
    _last_audio_level_ms: int = 0
    _AUDIO_LEVEL_MIN_INTERVAL_MS = 50

    try:
        while True:
            message = await websocket.receive()

            if message["type"] == "websocket.disconnect":
                break

            if "bytes" in message and message["bytes"] is not None:
                if not turn_active:
                    continue
                await pipeline.feed_frame(message["bytes"])
                # Sprint 17b: broadcast vad.audio_level so the
                # cockpit HUD can follow the user's voice in
                # real time. Rate-limited to 50ms (20Hz) so we
                # don't flood the WebSocket; the HUD's rAF
                # interpolation smooths the rest.
                now_ms = int(time.time() * 1000)
                if now_ms - _last_audio_level_ms >= _AUDIO_LEVEL_MIN_INTERVAL_MS:
                    await _send_json(websocket, {
                        "type": "vad.audio_level",
                        "data": {
                            "session_id": current_session_id,
                            "level": pipeline.last_audio_level,
                            "ts_ms": now_ms,
                        },
                    })
                    _last_audio_level_ms = now_ms
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
                        # Sprint 16: detect wake phrase. We run the
                        # detection BEFORE sending `asr.result` so
                        # the text the user sees in the cockpit
                        # already reflects the stripped form. The
                        # `wake_phrase` field is sent alongside
                        # `asr.result` so the frontend can badge it
                        # in MissionLog / transcript immediately.
                        wake = detect_wake_phrase(
                            result.asr_text,
                            get_config().voice.wake_phrases,
                        )
                        display_asr_text = (
                            wake.stripped if wake.matched else result.asr_text
                        )
                        await _send_json(websocket, {
                            "type": "asr.result",
                            "data": {
                                "session_id": result.session_id,
                                "text": display_asr_text,
                                "duration_ms": result.asr_duration_ms,
                                "wake_phrase": wake.phrase,
                                "wake_triggered": wake.matched,
                            },
                        })

                        # Sprint 17a: strict wake-phrase mode. If
                        # the user has strict mode on AND the
                        # transcript did not start with a
                        # recognized wake phrase, drop the turn
                        # here. We still emitted `asr.result` so the
                        # cockpit shows what was heard (with
                        # `wake_triggered: false`), but we skip
                        # the agent invocation + TTS path and
                        # surface a `voice.turn_ended` with
                        # `discarded: true` and `reason: "no_wake_phrase"`
                        # so the frontend can show a brief
                        # "Listening for **Unicorn**…" hint.
                        cfg_voice = get_config().voice
                        if (
                            cfg_voice.strict_wake_phrase
                            and not wake.matched
                        ):
                            await _send_json(websocket, {
                                "type": "voice.turn_ended",
                                "data": {
                                    "session_id": result.session_id,
                                    "discarded": True,
                                    "reason": "no_wake_phrase",
                                    "total_duration_ms":
                                        result.ended_at_ms - result.started_at_ms,
                                },
                            })
                            continue
                        # M15: re-run agent in streaming mode.
                        # The pipeline's _on_user_text already ran
                        # the batch agent and discarded its reply
                        # (set agent_reply=None by contract); we
                        # re-run via the streaming callback here.
                        # We pass the STRIPPED text to the agent
                        # (no wake phrase prefix).
                        if _agent_callback is not None:
                            try:
                                sentence_iter = await _resolve_stream_iter(
                                    _agent_callback(
                                        result.session_id,
                                        display_asr_text,
                                    )
                                )
                            except Exception as e:
                                logger.error(
                                    f"Streaming agent callback error: {e}"
                                )
                                sentence_iter = None
                            if sentence_iter is not None:
                                # Sprint 17a: fresh per-turn
                                # SanitizerState so cross-sentence
                                # `<think>` open/close state never
                                # leaks between voice turns.
                                await emit_agent_response_streaming(
                                    websocket,
                                    responder,
                                    result.session_id,
                                    sentence_iter,
                                    wake_phrase=wake.phrase,
                                    sanitizer_state=SanitizerState(),
                                )
                        await _send_json(websocket, {
                            "type": "voice.turn_ended",
                            "data": {
                                "session_id": result.session_id,
                                "discarded": False,
                                "reason": None,
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
                        # Sprint 16: detect wake phrase in text-bypass
                        # path too. Same logic as the voice.end path.
                        wake = detect_wake_phrase(
                            text, get_config().voice.wake_phrases
                        )
                        display_text = (
                            wake.stripped if wake.matched else text
                        )
                        # Sprint 17a: strict wake-phrase gate also
                        # applies to the text-bypass path. We emit
                        # an `asr.result` frame (so the cockpit
                        # transcript shows the text the user
                        # typed) but skip the agent + TTS path
                        # when strict mode is on and no wake was
                        # matched. The "wake_triggered: false"
                        # chip in the cockpit lets the user see
                        # why their turn was dropped.
                        await _send_json(websocket, {
                            "type": "asr.result",
                            "data": {
                                "session_id": sid,
                                "text": display_text,
                                "duration_ms": 0,
                                "wake_phrase": wake.phrase,
                                "wake_triggered": wake.matched,
                            },
                        })
                        cfg_voice = get_config().voice
                        if (
                            cfg_voice.strict_wake_phrase
                            and not wake.matched
                        ):
                            await _send_json(websocket, {
                                "type": "voice.turn_ended",
                                "data": {
                                    "session_id": sid,
                                    "discarded": True,
                                    "reason": "no_wake_phrase",
                                    "total_duration_ms": 0,
                                },
                            })
                            continue
                        try:
                            sentence_iter = await _resolve_stream_iter(
                                _agent_callback(sid, display_text)
                            )
                        except Exception as e:
                            logger.error(f"Agent callback error: {e}")
                            sentence_iter = None
                        if sentence_iter is not None:
                            # Sprint 17a: fresh per-turn
                            # SanitizerState (see voice.end
                            # path above for rationale).
                            await emit_agent_response_streaming(
                                websocket,
                                responder,
                                sid,
                                sentence_iter,
                                wake_phrase=wake.phrase,
                                sanitizer_state=SanitizerState(),
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
                                "reason": None,
                                "total_duration_ms":
                                    int((time.time() - t_turn_start) * 1000),
                            },
                        })
                    else:
                        # No agent wired; echo the text back as ASR
                        # (also strip the wake phrase if any, so the
                        # echo doesn't repeat "Unicorn" verbatim).
                        wake = detect_wake_phrase(
                            text, get_config().voice.wake_phrases
                        )
                        echo_text = wake.stripped if wake.matched else text
                        await _send_json(websocket, {
                            "type": "asr.result",
                            "data": {
                                "session_id": sid,
                                "text": echo_text,
                                "duration_ms": 0,
                                "wake_phrase": wake.phrase,
                                "wake_triggered": wake.matched,
                            },
                        })
                        # Sprint 17a: strict gate also applies
                        # here. With no agent wired, "discarding"
                        # the turn means sending `voice.turn_ended`
                        # with discarded: true + reason so the
                        # frontend can show the same hint.
                        cfg_voice = get_config().voice
                        if (
                            cfg_voice.strict_wake_phrase
                            and not wake.matched
                        ):
                            await _send_json(websocket, {
                                "type": "voice.turn_ended",
                                "data": {
                                    "session_id": sid,
                                    "discarded": True,
                                    "reason": "no_wake_phrase",
                                    "total_duration_ms": 0,
                                },
                            })
                            continue
                        await _send_json(websocket, {
                            "type": "voice.turn_ended",
                            "data": {
                                "session_id": sid,
                                "discarded": False,
                                "reason": None,
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
        # Sprint 19c: unsubscribe from the VAD event
        # bus so a reconnect doesn't accumulate stale
        # listeners. The pipeline.reset() below runs
        # regardless of whether the connection ended
        # cleanly or crashed.
        try:
            _bus.unsubscribe(EventType.VOICE_VAD_SPEECH_START, _on_speech_start)
            _bus.unsubscribe(EventType.VOICE_VAD_SPEECH_END, _on_speech_end)
        except Exception as e:
            logger.warning(f"Voice WS {client_id} bus unsubscribe error: {e}")
        if turn_active:
            pipeline.reset()


__all__ = [
    "router",
    "AgentStreamCallback",
    "set_agent_callback",
    "get_agent_callback",
    "set_responder",
]
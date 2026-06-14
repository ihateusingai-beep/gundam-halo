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

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

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
from app.voice.tts.voice_sanitizer import SanitizerState, sanitize_for_tts
from app.voice.vad.vad_factory import create_vad
from app.voice.wake_phrase import detect_wake_phrase, first_wake_phrase

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
            # Sprint 17a: ship the strict-mode flag in the hello
            # frame too so the frontend knows on connect whether
            # the gate is on (avoids an extra GET /voice/config
            # round-trip on the first page load).
            "strict_wake_phrase": cfg.strict_wake_phrase,
        },
    })

    current_session_id: str | None = None
    turn_active = False

    async def _emit_agent_response_streaming(
        sid: str,
        sentence_iter: AsyncIterator[str],
        wake_phrase: str = "",
        sanitizer_state: "SanitizerState | None" = None,
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

        Sprint 17a: the optional `sanitizer_state` argument is the
        per-turn `SanitizerState` used to thread cross-sentence
        `<think>` open/close state. If None, a fresh state is
        created (legacy behaviour, also used by tests). The caller
        is responsible for allocating one per turn and discarding
        it afterwards.

        After the stream is exhausted we send a final
        `agent.message` (is_final=True) and a `tts.end`.
        """
        if sanitizer_state is None:
            sanitizer_state = SanitizerState()
        accumulated = ""
        chunk_count = 0
        emotion: str = DEFAULT_EMOTION
        live2d_sent = False
        tts_started = False
        wake_emitted = False

        try:
            async for sentence in sentence_iter:
                if not sentence or not sentence.strip():
                    continue
                sanitized = sanitize_for_tts(sentence, sanitizer_state)
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
                        # Sprint 16: wake phrase confidence marker.
                        # Only the first frame carries the matched
                        # phrase; subsequent frames carry an empty
                        # string so the client can render the badge
                        # once and stop flickering.
                        "wake_phrase": wake_phrase if not wake_emitted else "",
                    },
                })
                wake_emitted = True

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
                "wake_phrase": wake_phrase,
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
                                await _emit_agent_response_streaming(
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
                            await _emit_agent_response_streaming(
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
        # Sprint 16: wake phrases shipped to the dashboard so the
        # Settings → Voice tab can display + edit them.
        "wake_phrases": cfg.wake_phrases,
    }


@router.get("/voice/config")
async def get_voice_config() -> dict[str, Any]:
    """Sprint 16 + 17a: get the voice config (wake_phrases +
    strict_wake_phrase).

    Kept separate from `/voice/status` so the dashboard can fetch
    the full config in one round-trip without paying for the VAD /
    ASR / TTS / Live2D fields it doesn't need to edit.
    """
    cfg = get_config().voice
    return {
        "wake_phrases": list(cfg.wake_phrases),
        "strict_wake_phrase": cfg.strict_wake_phrase,
    }


@router.put("/voice/config")
async def put_voice_config(payload: dict[str, Any]) -> dict[str, Any]:
    """Sprint 16 + 17a: update the voice config in-memory + persist
    to config.toml. Both `wake_phrases` and `strict_wake_phrase`
    are editable. Other [voice] keys are not touched.

    Payload (both fields required; send the current value of
    whichever one you don't want to change):
      - `wake_phrases: list[str]` — non-empty list of non-empty strings.
      - `strict_wake_phrase: bool` — if true, voice turns are
        discarded unless the ASR transcript starts with a
        configured wake phrase.

    Persistence:
      - Edit `~/.gundam-halo/config.toml` [voice] section to add
        the new `wake_phrases` list AND the `strict_wake_phrase`
        line (we don't blow away the user's other [voice] settings
        — we only touch the keys we own).
      - The in-process config is updated immediately so the next
        voice turn picks up the change without a server restart.
    """
    import asyncio
    import re
    from pathlib import Path

    # ---- wake_phrases validation (unchanged from Sprint 16) ----
    new_phrases = payload.get("wake_phrases")
    if not isinstance(new_phrases, list) or not all(
        isinstance(p, str) and p.strip() for p in new_phrases
    ):
        raise HTTPException(
            status_code=400,
            detail="`wake_phrases` must be a non-empty list of non-empty strings",
        )
    # Normalize: strip whitespace, drop empties, dedupe (preserving order)
    seen: set[str] = set()
    normalized: list[str] = []
    for p in new_phrases:
        s = p.strip()
        if s and s not in seen:
            seen.add(s)
            normalized.append(s)
    if not normalized:
        raise HTTPException(
            status_code=400,
            detail="`wake_phrases` must contain at least one non-empty string",
        )

    # ---- Sprint 17a: strict_wake_phrase validation ----
    # The field is required in the payload. We don't accept
    # implicit "use the current value" — the dashboard is the
    # source of truth for the user's intent and should always
    # send the form's current state.
    if "strict_wake_phrase" not in payload:
        raise HTTPException(
            status_code=400,
            detail="`strict_wake_phrase` is required (send the current toggle state)",
        )
    new_strict = payload["strict_wake_phrase"]
    if not isinstance(new_strict, bool):
        raise HTTPException(
            status_code=400,
            detail="`strict_wake_phrase` must be a boolean",
        )

    # Update in-memory config (so the next turn picks it up).
    cfg = get_config()
    cfg.voice.wake_phrases = normalized
    cfg.voice.strict_wake_phrase = new_strict
    # Invalidate the cache so future get_config() reloads from disk.
    from app.core import config as config_mod
    config_mod._config = None

    # Persist to config.toml. We use a simple, targeted edit that
    # only touches the [voice] lines we own. Other [voice]
    # keys are left alone.
    config_path = Path(cfg.home) / "config.toml"
    try:
        if config_path.exists():
            text = config_path.read_text(encoding="utf-8")
        else:
            text = ""

        # ---- wake_phrases line ----
        new_phrases_line = f"wake_phrases = {_toml_list(normalized)}\n"
        text, n = re.subn(
            r"(?m)^wake_phrases\s*=\s*\[.*?\]\s*$",
            new_phrases_line.rstrip(),
            text,
            count=1,
        )
        if n == 0:
            if "[voice]" not in text:
                if not text.endswith("\n"):
                    text += "\n"
                text += "\n[voice]\n" + new_phrases_line
            else:
                if not text.endswith("\n"):
                    text += "\n"
                text += new_phrases_line

        # ---- strict_wake_phrase line (Sprint 17a) ----
        new_strict_line = f"strict_wake_phrase = {str(new_strict).lower()}\n"
        text, n = re.subn(
            r"(?m)^strict_wake_phrase\s*=\s*(?:true|false)\s*$",
            new_strict_line.rstrip(),
            text,
            count=1,
        )
        if n == 0:
            # No existing strict_wake_phrase line — append. If
            # [voice] exists in the file we drop the key right
            # after the wake_phrases line; otherwise we create
            # a [voice] section. For simplicity we just append
            # at end of file; TOML is forgiving about ordering.
            if not text.endswith("\n"):
                text += "\n"
            text += new_strict_line

        config_path.write_text(text, encoding="utf-8")
    except Exception as e:
        logger.error(f"failed to persist voice config: {e}")
        # We've already updated the in-memory config; surface the
        # write error so the dashboard can show a warning.
        return {
            "wake_phrases": normalized,
            "strict_wake_phrase": new_strict,
            "persisted": False,
            "error": str(e),
        }

    return {
        "wake_phrases": normalized,
        "strict_wake_phrase": new_strict,
        "persisted": True,
    }


def _toml_list(items: list[str]) -> str:
    """Render a Python list[str] as a TOML array literal."""
    inner = ", ".join(f'"{s}"' for s in items)
    return f"[{inner}]"

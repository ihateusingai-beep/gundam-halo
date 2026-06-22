"""Voice streaming response handler.

Sprint 32 P1.1: extracted from `api/voice_ws.py` (637-line
`voice_websocket` monolith). The streaming helper
(`emit_agent_response_streaming`) is the meat of the agent
→ TTS → Live2D pipeline: it consumes the agent's sentence
iterator and forwards each chunk to the client as
`agent.message` (incremental) + `tts.audio` (binary) +
`live2d.trigger` (avatar expression).

Splitting it out makes the WS route (`ws_protocol.py`) read
like a control loop (accept → handle events → finalise),
while the per-sentence streaming / sanitisation / emotion
parsing / TTS dispatch logic lives here.

Public surface:
- `emit_agent_response_streaming(websocket, responder, sid,
  sentence_iter, *, wake_phrase, sanitizer_state)` — the
  single async helper that consumes a sentence iterator.

The helper uses `_send_json` / `_send_text_then_binary`
from `ws_protocol.py` — those are tiny JSON / binary frame
dispatchers, not stateful, so cross-importing them keeps
the streaming logic self-contained.
"""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from fastapi import WebSocket

from app.voice.halo_responder import (
    DEFAULT_EMOTION,
    EMOTION_MAP,
    HaloResponder,
    parse_emotion,
)
from app.voice.tts.voice_sanitizer import SanitizerState, sanitize_for_tts

# Imported for type checking only — keeps runtime dependencies
# minimal (the `responder._live2d` duck-typed access in the
# streaming body doesn't require importing Live2D types).
if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


async def emit_agent_response_streaming(
    websocket: WebSocket,
    responder: HaloResponder | None,
    sid: str,
    sentence_iter: AsyncIterator[str],
    *,
    wake_phrase: str = "",
    sanitizer_state: SanitizerState | None = None,
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
    # Local imports keep the cycle `ws_protocol ↔ pipeline_handler`
    # one-way (the streaming body is the only consumer of the
    # send helpers, and only `ws_protocol.py::voice_websocket`
    # calls into here).
    from app.api.ws_protocol import _send_json, _send_text_then_binary

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


__all__ = ["emit_agent_response_streaming"]
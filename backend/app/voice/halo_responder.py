"""HaloResponder — agent output → TTS + Live2D triggers.

The agent never speaks Live2D's language. Instead, it's prompted to
prefix its reply with an emotion tag from a small DSL (see
ARCHITECTURE §15.11). HaloResponder:

1. Parses the emotion tag off the front of the text
2. Maps the emotion to a (Live2D expression, motion) pair
3. Splits the remaining text into sentences
4. For each sentence, calls TTS.synthesize (or stream_synthesize)
5. Returns the audio bytes + the Live2D trigger

This is the v1 NT-D / Unicorn theme. M3 will add SeedFreedomResponder,
CrossboneResponder, etc.

Why a class (not just functions):
- Configurable via dependency injection (TTS + Live2D instances)
- Trivial to swap for a different theme in tests
- Future themes can subclass and override EMOTION_MAP
"""

from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass

from app.core.events import EventType, get_event_bus
from app.voice.live2d.live2d_interface import Live2DInterface, Live2DTrigger
from app.voice.tts.splitter import split_sentences
from app.voice.tts.tts_interface import TTSInterface, TTSResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Emotion DSL
# ---------------------------------------------------------------------------

# Matches `[EMO:awakening]` at the start of a message. Case-insensitive.
# The whole match (including brackets) is consumed.
_EMOTION_RE = re.compile(r"^\s*\[EMO:(\w+)\]\s*", re.IGNORECASE)

# All valid emotions. The LLM is told to pick from this set.
VALID_EMOTIONS: frozenset[str] = frozenset(
    {
        "calm",
        "focused",
        "awakening",
        "alert",
        "damage",
        "resolve",
        "jubilant",
        "stealth",
    }
)

DEFAULT_EMOTION = "calm"


# NT-D / Unicorn theme mapping (v1).
# Each emotion → (Live2D expression, motion, TTS rate adjustment).
EMOTION_MAP: dict[str, dict] = {
    "calm":      {"expr": "ntd_calm",      "motion": "idle",     "tts_rate": 1.0},
    "focused":   {"expr": "ntd_focused",   "motion": "lean_in",  "tts_rate": 0.95},
    "awakening": {"expr": "ntd_psychoframe", "motion": "awaken",  "tts_rate": 1.05},
    "alert":     {"expr": "ntd_alert",     "motion": "scan",     "tts_rate": 1.10},
    "damage":    {"expr": "ntd_damage",    "motion": "flinch",   "tts_rate": 0.90},
    "resolve":   {"expr": "ntd_resolve",   "motion": "stand",    "tts_rate": 1.0},
    "jubilant":  {"expr": "ntd_jubilant",  "motion": "victory",  "tts_rate": 1.10},
    "stealth":   {"expr": "ntd_stealth",   "motion": "vanish",   "tts_rate": 0.85},
}


@dataclass(slots=True)
class HaloResponse:
    """The full set of outputs HaloResponder produces for one agent turn."""

    clean_text: str           # text with emotion tag stripped
    emotion: str              # resolved emotion (always one of VALID_EMOTIONS)
    live2d: Live2DTrigger | None  # emotion → expression/motion
    audio_chunks: list[TTSResult]   # one per sentence


def parse_emotion(text: str) -> tuple[str, str]:
    """Extract the emotion tag from the front of *text*.

    Returns:
        (clean_text, emotion). If no tag found, emotion is DEFAULT_EMOTION.
    """
    if not text:
        return "", DEFAULT_EMOTION
    m = _EMOTION_RE.match(text)
    if not m:
        return text.strip(), DEFAULT_EMOTION
    emo = m.group(1).lower()
    if emo not in VALID_EMOTIONS:
        logger.debug(f"Unknown emotion {emo!r}, falling back to {DEFAULT_EMOTION}")
        emo = DEFAULT_EMOTION
    return text[m.end():].strip(), emo


class HaloResponder:
    """Translate agent text into (Live2D + TTS audio) outputs.

    Usage:
        responder = HaloResponder(tts=tts, live2d=live2d)
        result = await responder.respond(agent_text)
        # result.clean_text — text to display in UI
        # result.live2d     — emotion-driven Live2D trigger
        # result.audio_chunks — TTS results, one per sentence
    """

    def __init__(
        self,
        tts: TTSInterface,
        live2d: Live2DInterface | None = None,
        *,
        theme: str = "ntd",
        max_sentence_chars: int = 80,
    ) -> None:
        self._tts = tts
        self._live2d = live2d
        self._theme = theme
        self._max_sentence_chars = max_sentence_chars
        # NT-D theme is the only one in v1; M3 will switch on `theme`.
        self._emotion_map = EMOTION_MAP

    async def warmup(self) -> None:
        """Warm up dependencies. Idempotent."""
        await self._tts.warmup()
        if self._live2d is not None:
            await self._live2d.warmup()

    async def respond(self, agent_text: str) -> HaloResponse:
        """One-shot respond: parse emotion, trigger Live2D, synth TTS.

        For streaming playback, use `respond_stream` instead.
        """
        clean_text, emotion = parse_emotion(agent_text)
        cfg = self._emotion_map.get(emotion, self._emotion_map[DEFAULT_EMOTION])

        # Fire Live2D trigger (if Live2D wired — M3 ships this for real)
        live2d_trigger: Live2DTrigger | None = None
        if self._live2d is not None:
            try:
                live2d_trigger = await self._live2d.trigger(
                    cfg["expr"], cfg["motion"]
                )
            except Exception as e:
                logger.warning(f"Live2D trigger failed: {e}")

        # Publish events so the dashboard can animate even without Live2D
        bus = get_event_bus()
        bus.publish(
            EventType.VOICE_LIVE2D_TRIGGER,
            {
                "expression": cfg["expr"],
                "motion": cfg["motion"],
                "emotion": emotion,
            },
        )

        # Split + synthesize
        sentences = split_sentences(
            clean_text, max_chars=self._max_sentence_chars
        )
        audio_chunks: list[TTSResult] = []
        for sent in sentences:
            try:
                tts_result = await self._tts.synthesize(sent)
                audio_chunks.append(tts_result)
            except Exception as e:
                logger.error(f"TTS failed for sentence {sent!r}: {e}")
                # Continue with the rest — partial response is better than none

        return HaloResponse(
            clean_text=clean_text,
            emotion=emotion,
            live2d=live2d_trigger,
            audio_chunks=audio_chunks,
        )

    async def respond_stream(
        self, agent_text: str
    ) -> AsyncIterator[tuple[str, bytes]]:
        """Stream TTS audio chunks for one agent reply.

        Yields:
            (sentence, mp3_bytes) tuples, one per sentence. The
            caller (voice_ws handler) forwards each chunk to the
            client as soon as it arrives.

        This minimizes TTFB — the first chunk can be sent to the
        client before later sentences are even synthesized.
        """
        clean_text, emotion = parse_emotion(agent_text)
        cfg = self._emotion_map.get(emotion, self._emotion_map[DEFAULT_EMOTION])

        # Fire Live2D trigger up front
        if self._live2d is not None:
            try:
                await self._live2d.trigger(cfg["expr"], cfg["motion"])
            except Exception as e:
                logger.warning(f"Live2D trigger failed: {e}")

        get_event_bus().publish(
            EventType.VOICE_LIVE2D_TRIGGER,
            {
                "expression": cfg["expr"],
                "motion": cfg["motion"],
                "emotion": emotion,
            },
        )
        get_event_bus().publish(
            EventType.VOICE_TTS_START,
            {"emotion": emotion, "text_length": len(clean_text)},
        )

        sentences = split_sentences(
            clean_text, max_chars=self._max_sentence_chars
        )
        try:
            for sent in sentences:
                if not sent.strip():
                    continue
                try:
                    async for chunk in self._tts.stream_synthesize(sent):
                        if chunk:
                            yield sent, chunk
                except Exception as e:
                    logger.error(f"TTS stream failed for {sent!r}: {e}")
                    # Skip this sentence, continue with the rest
        finally:
            get_event_bus().publish(EventType.VOICE_TTS_END, {"emotion": emotion})


__all__ = [
    "DEFAULT_EMOTION",
    "EMOTION_MAP",
    "HaloResponse",
    "HaloResponder",
    "VALID_EMOTIONS",
    "parse_emotion",
]

"""Voice pipeline — VAD → ASR → Message → Agent → text reply.

M1 scope:
- Per-turn state machine: IDLE → LISTENING → SPEECH_DETECTED → UTTERANCE
- Buffers audio frames from a WebSocket voice channel
- Runs VAD per frame, fires `VOICE_VAD_SPEECH_START/END` events
- On end-of-utterance, calls ASR.transcribe(buffered_audio)
- Emits `VOICE_ASR_RESULT` event with the transcribed text
- Routes the text to the active session's agent
- Emits `VOICE_TURN_END` event with the agent's reply text

The pipeline is decoupled from any specific transport (Tauri WS,
Telegram voice note, file upload) — it accepts an `AudioSource`
(an async iterator of PCM bytes) and yields structured events.

Why not in `agents/`?
- Voice is an INPUT channel, not an agent. The agent just sees
  `Message(role=USER, content=transcribed_text)`.
- The pipeline knows about VAD/ASR/audio bytes. Agents must not.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from app.core.events import EventType, get_event_bus
from app.voice.asr.asr_interface import ASRInterface
from app.voice.vad.vad_interface import VADEvent, VADInterface

logger = logging.getLogger(__name__)


class TurnState(StrEnum):
    """Per-utterance state machine for the voice pipeline."""

    IDLE = "idle"  # no audio arriving
    LISTENING = "listening"  # receiving audio, no speech yet
    SPEECH_DETECTED = "speech_detected"  # speech in progress
    UTTERANCE = "utterance"  # processing the captured audio
    AGENT_THINKING = "agent_thinking"  # waiting for agent reply


@dataclass(slots=True)
class VoiceTurnResult:
    """Final result of one voice turn (utterance + agent reply)."""

    session_id: str
    asr_text: str
    agent_reply: str | None = None
    asr_duration_ms: int = 0
    agent_duration_ms: int = 0
    started_at_ms: int = 0
    ended_at_ms: int = 0


class VoicePipeline:
    """Orchestrates one user turn from audio bytes to agent reply.

    Lifecycle:
        pipeline = VoicePipeline(vad, asr, on_user_text, on_agent_reply)
        await pipeline.warmup()
        async for frame in audio_source:
            await pipeline.feed_frame(frame)
        result = await pipeline.finalize_turn()
    """
    def __init__(
        self,
        vad: VADInterface,
        asr: ASRInterface,
        *,
        speech_threshold_start: float = 0.5,
        speech_threshold_end: float = 0.3,
        min_speech_ms: int = 250,
        min_silence_ms: int = 700,
        sample_rate: int = 16000,
        on_user_text: Callable[[str, str], asyncio.Future] | None = None,
        # Sprint 17b: optional second VAD for per-frame audio-level
        # broadcasting. When set, the pipeline calls
        # audio_level_vad.process_frame() for every audio frame
        # (in addition to vad.process_frame()) and surfaces the
        # resulting probability via last_audio_level. The
        # utterance-boundary logic still uses vad exclusively.
        audio_level_vad: VADInterface | None = None,
    ) -> None:
        """Build a pipeline.

        Args:
            vad: VAD engine (silero in v1, used for utterance boundary)
            asr: ASR engine
            speech_threshold_start: VAD prob >= this -> speech start
            speech_threshold_end: VAD prob < this -> silence (end)
            min_speech_ms: ignore utterances shorter than this
            min_silence_ms: continuous silence >= this triggers end-of-utterance
            sample_rate: audio sample rate (Hz)
            on_user_text: async callback (session_id, text) -> agent_reply.
                If None, the pipeline just emits the ASR event and
                doesn't call any agent. Useful for tests.
            audio_level_vad: Sprint 17b -- optional second VAD whose
                probability is broadcast on every frame as a
                vad.audio_level event. Default None (no audio-level
                frames; existing callers see no change).
        """
        self._vad = vad
        self._asr = asr
        self._speech_threshold_start = speech_threshold_start
        self._speech_threshold_end = speech_threshold_end
        self._min_speech_ms = min_speech_ms
        self._min_silence_ms = min_silence_ms
        self._sample_rate = sample_rate
        self._on_user_text = on_user_text
        # Sprint 17b: dual-VAD wiring. The audio-level VAD doesn't
        # drive utterance boundaries -- it's a passive level source
        # for the cockpit HUD.
        self._audio_level_vad = audio_level_vad
        # The last per-frame audio level (0.0-1.0). voice_ws reads
        # this after each feed_frame call to broadcast a
        # vad.audio_level WS frame.
        self.last_audio_level: float = 0.0

        # Per-turn state (reset on each turn)
        self._state = TurnState.IDLE
        self._buffer: bytearray = bytearray()
        self._silence_frames: int = 0  # consecutive silence frames since last speech
        self._speech_start_ms: int | None = None
        self._turn_started_at_ms: int = 0
        self._last_session_id: str = ""
        self._frames_processed = 0
        self._frames_speech = 0
        # Convert min_silence_ms to frame count. Default frame is 250ms
        # (= sample_rate * 2 bytes * 0.25 / 1000); user config supplies
        # frame_duration_ms. We pre-compute the threshold here.
        frame_ms = 1000.0 * (sample_rate * 2 * 0.25) / sample_rate / 1000
        # sample_rate cancels; the "frame is 250ms" assumption is baked
        # into our spec (see ARCHITECTURE §15.4).
        frame_ms = 250.0
        self._silence_frames_threshold = max(
            1, int(round(self._min_silence_ms / frame_ms))
        )


        # Per-turn state (reset on each turn)
        self._state = TurnState.IDLE
        self._buffer: bytearray = bytearray()
        self._silence_frames: int = 0  # consecutive silence frames since last speech
        self._speech_start_ms: int | None = None
        self._turn_started_at_ms: int = 0
        self._last_session_id: str = ""
        self._frames_processed = 0
        self._frames_speech = 0
        # Convert min_silence_ms to frame count. Default frame is 250ms
        # (= sample_rate * 2 bytes * 0.25 / 1000); user config supplies
        # frame_duration_ms. We pre-compute the threshold here.
        frame_ms = 1000.0 * (sample_rate * 2 * 0.25) / sample_rate / 1000
        # sample_rate cancels; the "frame is 250ms" assumption is baked
        # into our spec (see ARCHITECTURE §15.4).
        frame_ms = 250.0
        self._silence_frames_threshold = max(
            1, int(round(self._min_silence_ms / frame_ms))
        )

    async def warmup(self) -> None:
        """Load VAD + ASR models."""
        await self._vad.warmup()
        await self._asr.warmup()
        # Sprint 17b: dual-VAD. Warm up the audio-level VAD
        # too (no-op for the energy-based FsmnVAD; will load
        # the fsmn-vad ONNX bundle once we swap the level
        # source in a follow-up sprint).
        if self._audio_level_vad is not None:
            await self._audio_level_vad.warmup()

    def reset(self) -> None:
        """Reset all per-turn state. Called between turns or on cancel."""
        self._state = TurnState.IDLE
        self._buffer = bytearray()
        self._silence_frames = 0
        self._speech_start_ms = None
        self._turn_started_at_ms = 0
        self._vad.reset()
        # Sprint 17b: also reset the audio-level VAD (clears
        # any streaming cache state). The energy-based FsmnVAD
        # has no state to reset; the follow-up fsmn-vad path
        # will clear its param_dict cache here.
        if self._audio_level_vad is not None:
            self._audio_level_vad.reset()

    async def begin_turn(self, session_id: str) -> None:
        """Mark a new turn starting. Idempotent."""
        self.reset()
        self._last_session_id = session_id
        self._turn_started_at_ms = int(time.time() * 1000)
        self._state = TurnState.LISTENING
        get_event_bus().publish(
            EventType.VOICE_TURN_START,
            {"session_id": session_id, "ts_ms": self._turn_started_at_ms},
        )
        logger.debug(f"Voice turn started: session={session_id}")

    async def feed_frame(self, audio_frame: bytes) -> None:
        """Feed one PCM frame to the pipeline.

        If this frame is the first after silence, VAD will detect
        speech_start. If speech has been ongoing and silence crosses
        `min_silence_ms`, the pipeline will end the utterance.

        The actual ASR + agent call happens in `finalize_turn` —
        we keep streaming and let the caller decide when to finalize.
        """
        if self._state == TurnState.IDLE or self._state == TurnState.AGENT_THINKING:
            # Ignore frames outside an active turn. But still
            # update the audio-level field for HUD if a level
            # VAD is configured (so the cockpit "sees" ambient
            # sound even outside a turn). This is a passive
            # tap, not a turn-state mutation.
            if self._audio_level_vad is not None:
                level_event = self._audio_level_vad.process_frame(
                    audio_frame, sample_rate=self._sample_rate
                )
                self.last_audio_level = level_event.probability
            return

        self._frames_processed += 1
        event: VADEvent = self._vad.process_frame(
            audio_frame, sample_rate=self._sample_rate
        )

        # Sprint 17b: also run the audio-level VAD (if configured)
        # and update last_audio_level. voice_ws reads this after
        # the feed_frame call to broadcast a vad.audio_level
        # WS frame (rate-limited to 50ms on the WS side).
        if self._audio_level_vad is not None:
            level_event = self._audio_level_vad.process_frame(
                audio_frame, sample_rate=self._sample_rate
            )
            self.last_audio_level = level_event.probability

        if self._state == TurnState.LISTENING:
            if event.probability >= self._speech_threshold_start:
                # Speech start!
                self._on_speech_start()
                self._buffer.extend(audio_frame)
                self._frames_speech += 1
            # else: keep listening, drop the frame
            return

        if self._state == TurnState.SPEECH_DETECTED:
            self._buffer.extend(audio_frame)
            if event.is_speech:
                self._frames_speech += 1
                self._silence_frames = 0
            else:
                self._silence_frames += 1
                # End utterance after N consecutive silence frames
                if self._silence_frames >= self._silence_frames_threshold:
                    await self._on_speech_end()
            return

    async def finalize_turn(
        self, session_id: str | None = None
    ) -> VoiceTurnResult | None:
        """End the current turn: run ASR + call agent (if any text).

        Returns:
            VoiceTurnResult if the turn produced text, None if the
            turn was empty (no speech detected).
        """
        if self._state not in (TurnState.LISTENING, TurnState.SPEECH_DETECTED):
            logger.debug(f"finalize_turn: nothing to finalize (state={self._state})")
            return None

        # If we're still in speech, force end
        if self._state == TurnState.SPEECH_DETECTED:
            await self._on_speech_end()

        self._state = TurnState.UTTERANCE
        sid = session_id or self._last_session_id
        turn_started = self._turn_started_at_ms or int(time.time() * 1000)

        # Quality gate: did the user actually speak for long enough?
        speech_ms = 0
        if self._speech_start_ms is not None:
            speech_ms = int(time.time() * 1000) - self._speech_start_ms
        if speech_ms < self._min_speech_ms:
            logger.info(
                f"finalize_turn: too short ({speech_ms}ms < "
                f"{self._min_speech_ms}ms), dropping"
            )
            self.reset()
            get_event_bus().publish(
                EventType.VOICE_TURN_END,
                {
                    "session_id": sid,
                    "discarded": "too_short",
                    "speech_ms": speech_ms,
                },
            )
            return None

        # Run ASR
        asr_start = int(time.time() * 1000)
        try:
            text = await self._asr.transcribe(
                bytes(self._buffer), sample_rate=self._sample_rate
            )
        except Exception as e:
            logger.error(f"ASR failed: {e}")
            get_event_bus().publish(
                EventType.VOICE_TURN_END,
                {
                    "session_id": sid,
                    "discarded": "asr_error",
                    "error": str(e),
                },
            )
            self.reset()
            return None
        asr_duration = int(time.time() * 1000) - asr_start

        if not text or not text.strip():
            logger.info("ASR returned empty text, dropping turn")
            self.reset()
            get_event_bus().publish(
                EventType.VOICE_TURN_END,
                {"session_id": sid, "discarded": "empty_asr"},
            )
            return None

        get_event_bus().publish(
            EventType.VOICE_ASR_RESULT,
            {
                "session_id": sid,
                "text": text,
                "duration_ms": asr_duration,
                "audio_bytes": len(self._buffer),
            },
        )

        # Hand off to agent
        result = VoiceTurnResult(
            session_id=sid,
            asr_text=text,
            asr_duration_ms=asr_duration,
            started_at_ms=turn_started,
            ended_at_ms=int(time.time() * 1000),
        )

        if self._on_user_text is not None:
            self._state = TurnState.AGENT_THINKING
            agent_start = int(time.time() * 1000)
            try:
                reply = await self._on_user_text(sid, text)
            except Exception as e:
                logger.error(f"Agent callback error: {e}")
                reply = None
            result.agent_duration_ms = int(time.time() * 1000) - agent_start
            result.agent_reply = reply
        else:
            logger.debug("No on_user_text callback, skipping agent call")

        get_event_bus().publish(
            EventType.VOICE_TURN_END,
            {
                "session_id": sid,
                "asr_text": result.asr_text,
                "agent_reply": result.agent_reply,
                "asr_duration_ms": result.asr_duration_ms,
                "agent_duration_ms": result.agent_duration_ms,
                "total_duration_ms": result.ended_at_ms - result.started_at_ms,
            },
        )
        self.reset()
        return result

    def _on_speech_start(self) -> None:
        """Mark speech start in the current turn."""
        now = int(time.time() * 1000)
        self._state = TurnState.SPEECH_DETECTED
        self._speech_start_ms = now
        self._silence_frames = 0
        get_event_bus().publish(
            EventType.VOICE_VAD_SPEECH_START,
            {"session_id": self._last_session_id, "ts_ms": now},
        )
        logger.debug("VAD: speech_start")

    async def _on_speech_end(self) -> None:
        """Mark speech end. Buffer holds the captured utterance."""
        now = int(time.time() * 1000)
        speech_ms = now - (self._speech_start_ms or now)
        get_event_bus().publish(
            EventType.VOICE_VAD_SPEECH_END,
            {
                "session_id": self._last_session_id,
                "ts_ms": now,
                "speech_ms": speech_ms,
                "audio_bytes": len(self._buffer),
            },
        )
        logger.debug(
            f"VAD: speech_end (speech_ms={speech_ms}, "
            f"frames_total={self._frames_processed}, "
            f"frames_speech={self._frames_speech})"
        )

    # ---- diagnostics ----

    @property
    def state(self) -> TurnState:
        return self._state

    @property
    def buffered_audio_bytes(self) -> int:
        return len(self._buffer)


__all__ = [
    "TurnState",
    "VoicePipeline",
    "VoiceTurnResult",
]

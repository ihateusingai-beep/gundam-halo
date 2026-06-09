"""Fake VAD and ASR engines for unit tests.

These allow testing the voice pipeline without loading Silero or
Whisper. Use the `fake_vad` and `fake_asr` fixtures from conftest.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator

from app.voice.asr.asr_interface import ASRInterface
from app.voice.live2d.live2d_interface import Live2DInterface, Live2DTrigger
from app.voice.tts.tts_interface import TTSInterface, TTSResult
from app.voice.vad.vad_interface import VADEvent, VADInterface


class FakeVAD(VADInterface):
    """A VAD that returns a configurable is_speech / probability."""

    def __init__(
        self,
        default_is_speech: bool = False,
        default_probability: float = 0.1,
    ) -> None:
        self._is_speech = default_is_speech
        self._probability = default_probability
        self.warmup_called = False
        self.reset_called = 0
        self.frames_processed = 0

    def set_speech(self, is_speech: bool, probability: float | None = None) -> None:
        self._is_speech = is_speech
        if probability is not None:
            self._probability = probability

    async def warmup(self) -> None:
        self.warmup_called = True

    def reset(self) -> None:
        self.reset_called += 1

    def process_frame(
        self, audio_frame: bytes, sample_rate: int = 16000
    ) -> VADEvent:
        self.frames_processed += 1
        return VADEvent(
            is_speech=self._is_speech,
            probability=self._probability,
            timestamp_ms=int(time.time() * 1000),
        )


class FakeASR(ASRInterface):
    """An ASR that returns a configured string after a configurable delay."""

    def __init__(
        self,
        default_text: str = "hello world",
        delay_s: float = 0.0,
    ) -> None:
        self._text = default_text
        self._delay = delay_s
        self.warmup_called = False
        self.transcribe_calls: list[bytes] = []

    def set_text(self, text: str) -> None:
        self._text = text

    async def warmup(self) -> None:
        self.warmup_called = True

    async def transcribe(
        self, audio: bytes, sample_rate: int = 16000
    ) -> str:
        self.transcribe_calls.append(audio)
        if self._delay > 0:
            import asyncio

            await asyncio.sleep(self._delay)
        return self._text


class FakeTTS(TTSInterface):
    """A TTS that returns a fixed MP3 byte string for each sentence.

    Records the list of sentences synthesized for assertion in tests.
    """

    def __init__(self, default_audio: bytes = b"\xff\xfb\x90\x00FAKE_MP3") -> None:
        self._audio = default_audio
        self.warmup_called = False
        self.synthesize_calls: list[str] = []
        self.stream_calls: list[str] = []

    async def warmup(self) -> None:
        self.warmup_called = True

    async def synthesize(
        self, text: str, voice: str | None = None
    ) -> TTSResult:
        self.synthesize_calls.append(text)
        return TTSResult(
            audio_bytes=self._audio,
            format="mp3",
            sample_rate=24000,
            duration_ms=int(len(self._audio) * 8 / 16),
        )

    async def stream_synthesize(
        self, text: str, voice: str | None = None
    ) -> AsyncIterator[bytes]:
        self.stream_calls.append(text)
        # Split the fake audio into 2 chunks to exercise streaming
        mid = len(self._audio) // 2
        if mid > 0:
            yield self._audio[:mid]
        yield self._audio[mid:]


class FakeLive2D(Live2DInterface):
    """A Live2D trigger that records what it was asked to play."""

    def __init__(self) -> None:
        self.warmup_called = False
        self.triggers: list[tuple[str, str]] = []

    async def warmup(self) -> None:
        self.warmup_called = True

    async def trigger(
        self, expression: str, motion: str
    ) -> Live2DTrigger:
        self.triggers.append((expression, motion))
        return Live2DTrigger(expression=expression, motion=motion)


__all__ = ["FakeASR", "FakeLive2D", "FakeTTS", "FakeVAD"]

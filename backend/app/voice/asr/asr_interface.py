"""ASR engine interface.

An ASR engine takes a complete audio utterance (the bytes buffered
between VAD speech_start and speech_end events) and returns the
transcribed text.

Implementations:
- `WhisperLocalASR` (v1) — local `openai-whisper` Python package
- `WhisperCppASR` (future) — faster, GPU accelerated
- `GroqWhisperASR` (future) — cloud fallback
- `FakeASR` (testing) — returns a hardcoded string
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class ASRError(RuntimeError):
    """Raised when ASR fails (model missing, audio format wrong, etc.)."""


class ASRInterface(ABC):
    """Automatic speech recognition engine."""

    @abstractmethod
    async def transcribe(
        self, audio: bytes, sample_rate: int = 16000
    ) -> str:
        """Transcribe a complete audio buffer to text.

        Args:
            audio: PCM 16-bit signed little-endian mono audio bytes
            sample_rate: 16000 expected for v1

        Returns:
            Transcribed text (whitespace-trimmed)

        Raises:
            ASRError: on backend failure
        """
        ...

    @abstractmethod
    async def warmup(self) -> None:
        """Load model into memory. Called once at startup."""
        ...


__all__ = ["ASRInterface", "ASRError"]

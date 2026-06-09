"""TTS engine interface — M2.

In M1 we ship the interface only. M2 will add the EdgeTTS implementation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(slots=True)
class TTSResult:
    """Output of TTS synthesis."""

    audio_bytes: bytes
    format: str  # "mp3" | "wav" | "opus"
    sample_rate: int
    duration_ms: int


class TTSInterface(ABC):
    """Text-to-speech engine (M2)."""

    @abstractmethod
    async def synthesize(self, text: str, voice: str | None = None) -> TTSResult:
        """Synthesize one chunk of text to audio."""
        ...

    @abstractmethod
    async def warmup(self) -> None:
        """Initialize any required clients/models."""
        ...


__all__ = ["TTSInterface", "TTSResult"]

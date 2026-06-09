"""VAD engine interface.

A VAD engine processes one frame of PCM audio (default 250ms = 8000
samples at 16kHz) and returns whether speech is present in that frame,
plus a probability score (0.0 - 1.0).

Implementations:
- `SileroVAD` (v1) — uses the silero-vad ONNX model
- `WebRTCVAD` (future) — Google's WebRTC VAD
- `AlwaysSpeechVAD` (testing) — always reports speech=True

M1 ships Silero + a deterministic FakeVAD for tests.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(slots=True)
class VADEvent:
    """Result of processing one audio frame."""

    is_speech: bool
    probability: float  # 0.0 - 1.0
    timestamp_ms: int


class VADInterface(ABC):
    """Voice activity detection engine."""

    @abstractmethod
    def process_frame(
        self, audio_frame: bytes, sample_rate: int = 16000
    ) -> VADEvent:
        """Process one frame of PCM 16-bit signed little-endian mono audio.

        Args:
            audio_frame: raw PCM bytes (default 250ms at 16kHz = 8000 bytes)
            sample_rate: 16000 expected for v1

        Returns:
            VADEvent with is_speech boolean and probability score
        """
        ...

    @abstractmethod
    async def warmup(self) -> None:
        """Load model into memory. Called once at startup."""
        ...

    @abstractmethod
    def reset(self) -> None:
        """Reset internal state (e.g., between turns or after a long silence).

        Silero's internal LSTM state should be cleared here.
        """
        ...


__all__ = ["VADInterface", "VADEvent"]

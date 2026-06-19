"""Edge TTS — Microsoft Edge's free online TTS service.

The `edge-tts` package talks to the same endpoint that powers
Microsoft Edge's "Read Aloud" feature. **No API key required** —
just pass a voice short name like `zh-HK-HiuMaanNeural` and the
service streams back MP3 audio.

Why Edge TTS for v1:
- Zero setup, zero auth, zero cost
- Wide language coverage (zh-HK, zh-CN, en, ja, ko, ...)
- Cantonese voice: `zh-HK-HiuMaanNeural` is genuinely good
- "Neural" voices sound natural enough to pass for a real assistant
- Audio format is MP3 (small, hardware-decoded by every browser)

Privacy caveat: this *does* send text to Microsoft's servers.
For paranoid users we ship an offline fallback (`pyttsx3`) in v2 —
see ARCHITECTURE §15.12.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from app.core.registry import register_tts
from app.voice.tts.tts_interface import TTSInterface, TTSResult

logger = logging.getLogger(__name__)


class EdgeTTSError(RuntimeError):
    """Raised when Edge TTS synthesis fails (network, voice not found)."""


@register_tts("edge")
class EdgeTTS(TTSInterface):
    """Microsoft Edge TTS via the `edge-tts` Python package."""

    def __init__(
        self,
        voice: str = "zh-HK-HiuMaanNeural",
        rate: str = "+0%",
        pitch: str = "+0Hz",
        volume: str = "+0%",
        default_format: str = "mp3",
    ) -> None:
        self._voice = voice
        self._rate = rate
        self._pitch = pitch
        self._volume = volume
        self._default_format = default_format
        self._warmed_up = False

    async def warmup(self) -> None:
        """edge-tts is a stateless HTTP client — nothing to load.

        We do verify the package is importable; if not, raise a clean
        error so callers don't see a cryptic ImportError later.
        """
        try:
            import edge_tts  # noqa: F401
        except ImportError as e:  # pragma: no cover
            raise EdgeTTSError(
                "edge-tts is required for EdgeTTS. "
                "Install with: uv add edge-tts"
            ) from e
        self._warmed_up = True
        logger.info(f"EdgeTTS ready (voice={self._voice})")

    def _communicate(self, text: str, voice: str | None = None):
        """Build an `edge_tts.Communicate` with our rate/pitch/volume."""
        import edge_tts

        return edge_tts.Communicate(
            text,
            voice=voice or self._voice,
            rate=self._rate,
            pitch=self._pitch,
            volume=self._volume,
        )

    async def synthesize(
        self, text: str, voice: str | None = None
    ) -> TTSResult:
        """Synthesize one chunk of text to MP3 audio.

        Edge-tts streams chunks; we collect them all into a single
        `TTSResult` for callers that want one-shot audio. Use
        `stream_synthesize` for sentence-level streaming (lower TTFB).
        """
        if not self._warmed_up:
            await self.warmup()

        text = (text or "").strip()
        if not text:
            raise EdgeTTSError("Cannot synthesize empty text")

        chunks: list[bytes] = []
        try:
            async for chunk in self._stream_chunks(text, voice):
                chunks.append(chunk)
        except Exception as e:
            logger.error(f"Edge TTS failed for text {text!r}: {e}")
            raise EdgeTTSError(f"Edge TTS failed: {e}") from e

        if not chunks:
            raise EdgeTTSError(
                f"Edge TTS returned no audio for text {text!r} "
                "(check voice name / network)"
            )

        audio_bytes = b"".join(chunks)
        # Edge-tts emits MP3 at 24kHz mono for neural voices. We don't
        # parse the actual bitstream to extract duration; the consumer
        # (HTMLAudioElement on the client) plays it as MP3 directly.
        # Duration is best-effort: ~16 kbps per second for neural MP3.
        # For an accurate figure, parse the MP3 frame headers — out of
        # scope for M2.
        duration_ms = int(len(audio_bytes) * 8 / 16)  # rough estimate

        return TTSResult(
            audio_bytes=audio_bytes,
            format=self._default_format,
            sample_rate=24000,
            duration_ms=duration_ms,
        )

    async def stream_synthesize(
        self, text: str, voice: str | None = None
    ) -> AsyncIterator[bytes]:
        """Yield MP3 chunks as they arrive from edge-tts.

        Use this for sentence-level streaming to minimize TTFB:
        the first chunk typically arrives <300ms after the request.
        """
        if not self._warmed_up:
            await self.warmup()
        text = (text or "").strip()
        if not text:
            return

        async for chunk in self._stream_chunks(text, voice):
            if chunk:
                yield chunk

    async def _stream_chunks(
        self, text: str, voice: str | None
    ) -> AsyncIterator[bytes]:
        """Internal helper — yield raw audio bytes from edge-tts."""
        comm = self._communicate(text, voice)
        async for event in comm.stream():
            # edge-tts yields dicts: {"type": "audio", "data": bytes}
            # or {"type": "WordBoundary", ...} which we skip.
            if event.get("type") == "audio":
                data = event.get("data")
                if data:
                    yield bytes(data)


__all__ = ["EdgeTTS", "EdgeTTSError"]

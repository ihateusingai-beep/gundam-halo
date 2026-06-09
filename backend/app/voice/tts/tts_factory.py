"""TTS engine factory.

Picks a TTS backend from `voice.tts.backend` in config.toml.
v1: only `edge` (Microsoft Edge TTS — free, no API key). Future:
`pyttsx3` (offline), `azure` (cloud with key).
"""

from __future__ import annotations

import logging

from app.core.config import VoiceTTSConfig
from app.voice.tts.tts_interface import TTSInterface

logger = logging.getLogger(__name__)


def create_tts(
    config: VoiceTTSConfig | None = None,
) -> TTSInterface:
    """Build a TTS engine from config.

    Args:
        config: TTS section of `~/.gundam-halo/config.toml`. If None, the
                factory looks up `get_config().voice.tts`.

    Returns:
        A ready-to-warmup TTS engine instance.

    Raises:
        ValueError: on unknown backend name
    """
    if config is None:
        from app.core.config import get_config

        config = get_config().voice.tts

    backend = config.backend.lower()
    logger.info(f"Creating TTS engine: backend={backend}")

    if backend == "edge":
        from app.voice.tts.edge_tts import EdgeTTS

        return EdgeTTS(
            voice=config.voice,
            rate=config.rate,
            pitch=config.pitch,
            volume=config.volume,
        )

    raise ValueError(
        f"Unknown TTS backend: {backend!r}. "
        f"v1 supports only 'edge'."
    )


__all__ = ["create_tts"]

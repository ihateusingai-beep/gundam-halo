"""TTS engine factory.

Picks a TTS backend from `voice.tts.backend` in config.toml.
v1: only `edge` (Microsoft Edge TTS — free, no API key). Future:
`pyttsx3` (offline), `azure` (cloud with key).

Sprint 32 P0-1: registry-based dispatch via `TtsRegistry`.
The if-elif branch is replaced with a single
`TtsRegistry.get(backend)` lookup plus a per-backend
kwargs adapter.
"""

from __future__ import annotations

import logging
from typing import Callable, Dict

from app.core.config import VoiceTTSConfig
from app.core.registry import TtsRegistry
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

    if not TtsRegistry.contains(backend):
        available = sorted(n for n, _ in TtsRegistry.items())
        raise ValueError(
            f"Unknown TTS backend: {backend!r}. "
            f"Available: {available}. "
            f"v1 supports only 'edge'."
        )

    return _TTS_KWARGS_ADAPTERS[backend](config)


def _build_edge_tts(config: VoiceTTSConfig) -> TTSInterface:
    from app.voice.tts.edge_tts import EdgeTTS

    return EdgeTTS(
        voice=config.voice,
        rate=config.rate,
        pitch=config.pitch,
        volume=config.volume,
    )


# Sprint 32 P0-1: registry dispatch table. Each entry maps the
# backend key to a kwargs adapter (VoiceTTSConfig → TTS instance).
_TTS_KWARGS_ADAPTERS: Dict[str, Callable[[VoiceTTSConfig], TTSInterface]] = {
    "edge": _build_edge_tts,
}


__all__ = ["create_tts"]

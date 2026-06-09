"""VAD engine factory.

Picks a VAD backend from `voice.vad.backend` in config.toml.
v1: only `silero`. Future: `webrtc`, `pyannote`.
"""

from __future__ import annotations

import logging

from app.core.config import VoiceVADConfig
from app.voice.vad.silero_vad import SileroVAD
from app.voice.vad.vad_interface import VADInterface

logger = logging.getLogger(__name__)


def create_vad(
    config: VoiceVADConfig | None = None,
) -> VADInterface:
    """Build a VAD engine from config.

    Args:
        config: VAD section of `~/.gundam-halo/config.toml`. If None, the
                factory looks up `get_config().voice.vad`.

    Returns:
        A ready-to-warmup VAD engine instance.

    Raises:
        ValueError: on unknown backend name
    """
    if config is None:
        from app.core.config import get_config

        config = get_config().voice.vad

    backend = config.backend.lower()
    logger.info(f"Creating VAD engine: backend={backend}")

    if backend == "silero":
        return SileroVAD(model_path=config.model_path)

    raise ValueError(
        f"Unknown VAD backend: {backend!r}. "
        f"v1 supports only 'silero'."
    )


__all__ = ["create_vad"]

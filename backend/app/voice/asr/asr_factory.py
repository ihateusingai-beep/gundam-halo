"""ASR engine factory.

Picks an ASR backend from `voice.asr.backend` in config.toml.
v1: only `whisper_local`. Future: `whisper_cpp`, `groq`, `funasr`.
"""

from __future__ import annotations

import logging

from app.core.config import VoiceASRConfig
from app.voice.asr.asr_interface import ASRInterface
from app.voice.asr.whisper_local import WhisperLocalASR

logger = logging.getLogger(__name__)


def create_asr(
    config: VoiceASRConfig | None = None,
) -> ASRInterface:
    """Build an ASR engine from config.

    Args:
        config: ASR section of `~/.gundam-halo/config.toml`. If None, the
                factory looks up `get_config().voice.asr`.

    Returns:
        A ready-to-warmup ASR engine instance.

    Raises:
        ValueError: on unknown backend name
    """
    if config is None:
        from app.core.config import get_config

        config = get_config().voice.asr

    backend = config.backend.lower()
    logger.info(f"Creating ASR engine: backend={backend}")

    if backend == "whisper_local":
        return WhisperLocalASR(
            model_size=config.model_size,
            language=config.language,
            device=config.device,
            compute_type=config.compute_type,
        )

    raise ValueError(
        f"Unknown ASR backend: {backend!r}. "
        f"v1 supports only 'whisper_local'."
    )


__all__ = ["create_asr"]

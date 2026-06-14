"""ASR engine factory.

Picks an ASR backend from `voice.asr.backend` in config.toml.
v1: `whisper_local` (Sprint 16).
Sprint 17b: `yuesub` (Cantonese, SenseVoice + fsmn-vad + optional
BERT corrector). The yuesub backend is a lazy import so that
whisper_local users don't need to install the voice-yuesub
extras (funasr_onnx, librosa, transformers[onnx], opencc, etc.).
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
            model_path=config.model_path,
            language=config.language,
            device=config.device,
            compute_type=config.compute_type,
        )

    if backend == "yuesub":
        # Lazy import: the yuesub ASR module pulls in funasr_onnx +
        # torchaudio + transformers, all of which are in the
        # voice-yuesub extra. whisper_local users don't need them.
        from app.voice.asr.yuesub import YuesubASR

        corrector = _build_corrector(config.corrector)

        return YuesubASR(
            language=config.language,
            device=config.device,
            corrector=corrector,
        )

    raise ValueError(
        f"Unknown ASR backend: {backend!r}. "
        f"Supported: 'whisper_local' (Sprint 16), 'yuesub' (Sprint 17b)."
    )


def _build_corrector(corrector_name: str):
    """Build a Corrector from a config string.

    Sprint 17b: `corrector = "bert" | "opencc" | "none"`.
    Returns None for "none". The corrector itself is owned by
    Track C; here we just glue the config string to the
    implementation. The corrector is sync (Track C will wrap
    it in `asyncio.to_thread` inside the voice pipeline).

    Returns:
        A `Corrector` instance, or None for "none".

    Raises:
        ValueError: on unknown corrector name.
    """
    name = (corrector_name or "none").lower()
    if name in ("none", "", "off", "false"):
        return None
    if name not in ("bert", "opencc"):
        raise ValueError(
            f"Unknown voice.asr.corrector: {name!r}. "
            f"Expected 'bert' | 'opencc' | 'none'."
        )
    # Track C delivers the corrector module. Lazy-import so
    # whisper_local users don't pull opencc/transformers.
    from app.voice.corrector.corrector import Corrector  # type: ignore

    return Corrector(corrector=name)


__all__ = ["create_asr"]

"""ASR engine factory.

Picks an ASR backend from `voice.asr.backend` in config.toml.
v1: `whisper_local` (Sprint 16).
Sprint 17b: `yuesub` (Cantonese, SenseVoice + fsmn-vad + optional
BERT corrector). The yuesub backend is a lazy import so that
whisper_local users don't need to install the voice-yuesub
extras (funasr_onnx, librosa, transformers[onnx], opencc, etc.).
Sprint 23 (v0.1.4): `whisper_hf` (Hugging Face transformers
pipeline; loads a fine-tuned HF-format checkpoint via
`voice.asr.model_path`). The whisper_hf backend is a lazy
import so that whisper_local / yuesub users don't need to
install the voice-hf extras (transformers, torch, accelerate,
soundfile). See `docs/FEATURE-SPEC-SPRINT22.md` §4.1 "Track 1".
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
        ValueError: on unknown backend name, or on
            `whisper_hf` with empty `model_path`.
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

    if backend == "whisper_hf":
        # Sprint 23 (v0.1.4): HF transformers pipeline for
        # fine-tuned Cantonese models. The voice-hf extra
        # declares `transformers` + `torch` + `accelerate`
        # + `soundfile` (~850MB total). whisper_local /
        # yuesub users don't pay for these.
        from app.voice.asr.whisper_hf import WhisperHFASR

        # model_path is REQUIRED for whisper_hf — the
        # WhisperHFASR class itself raises ASRError on
        # empty model_path, but we fail earlier here with
        # a clearer ValueError so the user sees a startup
        # error rather than a warmup error.
        if not config.model_path:
            raise ValueError(
                "voice.asr.model_path is required when "
                "backend='whisper_hf'. Set it in config.toml "
                "to the fine-tuned checkpoint directory, e.g.\n"
                'model_path = "~/.gundam-halo/models/whisper-yue-base/"'
            )

        return WhisperHFASR(
            model_path=config.model_path,
            language=config.language,
            device=config.device,
            compute_type=config.compute_type,
        )

    raise ValueError(
        f"Unknown ASR backend: {backend!r}. "
        f"Supported: 'whisper_local' (Sprint 16), 'yuesub' (Sprint 17b), "
        f"'whisper_hf' (Sprint 23 / v0.1.4)."
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

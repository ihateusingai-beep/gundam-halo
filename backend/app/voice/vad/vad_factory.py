"""VAD engine factory.

Picks a VAD backend from `voice.vad.backend` in config.toml.
v1: `silero` (utterance boundary). Sprint 17b adds `fsmn`
(per-frame audio level source for the cockpit HUD; runs in
parallel with silero in the dual-VAD pipeline).
"""

from __future__ import annotations

import logging

from app.core.config import VoiceVADConfig
from app.voice.vad.fsmn_vad import FsmnVAD
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

    if backend == "fsmn":
        # Sprint 17b: per-frame audio-level VAD. The FsmnVAD
        # class currently uses RMS energy as the level source;
        # a follow-up sprint will swap to fsmn-vad-online's
        # per-chunk speech probability (see the module
        # docstring on FsmnVAD for the rationale).
        return FsmnVAD()

    raise ValueError(
        f"Unknown VAD backend: {backend!r}. "
        f"Supported: 'silero' (v1), 'fsmn' (Sprint 17b)."
    )


__all__ = ["create_vad"]

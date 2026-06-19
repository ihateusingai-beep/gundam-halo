"""VAD engine factory.

Picks a VAD backend from `voice.vad.backend` in config.toml.
v1: `silero` (utterance boundary). Sprint 17b adds `fsmn`
(per-frame audio level source for the cockpit HUD; runs in
parallel with silero in the dual-VAD pipeline).

Sprint 32 P0-1: registry-based dispatch via `VadRegistry`.
The 2 if-elif branches are replaced with a single
`VadRegistry.get(backend)` lookup plus a per-backend
kwargs adapter.
"""

from __future__ import annotations

import logging
from typing import Callable, Dict

from app.core.config import VoiceVADConfig
from app.core.registry import VadRegistry
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

    if not VadRegistry.contains(backend):
        available = sorted(n for n, _ in VadRegistry.items())
        raise ValueError(
            f"Unknown VAD backend: {backend!r}. "
            f"Available: {available}. "
            f"Supported: 'silero' (v1), 'fsmn' (Sprint 17b)."
        )

    return _VAD_KWARGS_ADAPTERS[backend](config)


def _build_silero(config: VoiceVADConfig) -> VADInterface:
    from app.voice.vad.silero_vad import SileroVAD

    return SileroVAD(model_path=config.model_path)


def _build_fsmn(config: VoiceVADConfig) -> VADInterface:
    from app.voice.vad.fsmn_vad import FsmnVAD

    # Sprint 19a: the level source is VAD-trained
    # (frame SNR from fsmn-vad-online, see
    # docs/FEATURE-SPEC-SPRINT19a.md §4.5). We pass
    # the configured `model_path` so the production
    # deployment uses the real fsmn-vad model. Tests
    # that don't ship the model can pass `model_dir=
    # None` explicitly to stay in energy mode.
    return FsmnVAD(model_dir=config.model_path)


# Sprint 32 P0-1: registry dispatch table. Each entry maps the
# backend key to a kwargs adapter (VoiceVADConfig → VAD instance).
_VAD_KWARGS_ADAPTERS: Dict[str, Callable[[VoiceVADConfig], VADInterface]] = {
    "silero": _build_silero,
    "fsmn": _build_fsmn,
}


__all__ = ["create_vad"]

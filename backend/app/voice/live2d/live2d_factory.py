"""Live2D trigger factory — M3.

M1 raised NotImplementedError. M3 ships NTDResponder (NT-D / Unicorn theme).
"""

from __future__ import annotations

import logging

from app.core.config import VoiceLive2DConfig
from app.voice.live2d.live2d_interface import Live2DInterface
from app.voice.live2d.ntd_responder import NTDResponder

logger = logging.getLogger(__name__)

_THEME_RESPONDERS: dict[str, type[Live2DInterface]] = {
    "ntd": NTDResponder,
    # M4+ will add: "seed": SeedFreedomResponder, "crossbone": ...
}


def create_live2d(
    config: VoiceLive2DConfig | None = None,
) -> Live2DInterface:
    """Build a Live2D trigger engine from config.

    Args:
        config: Live2D config. If None, reads from global config.

    Returns:
        A Live2DInterface implementation for the configured theme.

    Raises:
        ValueError: Unknown theme.
    """
    if config is None:
        from app.core.config import get_config

        config = get_config().voice.live2d

    theme = config.theme.lower()
    responder_cls = _THEME_RESPONDERS.get(theme)

    if responder_cls is None:
        available = list(_THEME_RESPONDERS.keys())
        raise ValueError(
            f"Unknown Live2D theme '{theme}'. Available: {available}. "
            f"See ARCHITECTURE §15.14."
        )

    logger.info(f"[Live2D Factory] Creating {theme!r} responder (model: {config.model_path})")
    return responder_cls(config)


__all__ = ["create_live2d"]
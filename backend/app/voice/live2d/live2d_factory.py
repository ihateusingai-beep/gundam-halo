"""Live2D trigger factory — M3 + M11.

Builds a per-theme `Live2DInterface` implementation from a config.
Each Gundam theme (NT-D, SEED, Crossbone, 00, Destiny, God,
Cartoon, Green) has its own responder subclass with the
fallback expression + motion names that match the model's
emotion vocabulary.

The map is keyed on the *short* theme slug used in
`cfg.voice.live2d.theme` (e.g. "ntd", "seed", "gundam-00").
Frontend theme IDs from `GundamTheme` ("gundam-ntd",
"gundam-seed", …) are accepted too — see `LONG_TO_SHORT`
for the mapping.
"""

from __future__ import annotations

import logging

from app.core.config import VoiceLive2DConfig
from app.voice.live2d.cartoon_responder import CartoonResponder
from app.voice.live2d.crossbone_responder import CrossboneResponder
from app.voice.live2d.destiny_responder import DestinyResponder
from app.voice.live2d.double_o_responder import DoubleOResponder
from app.voice.live2d.god_responder import GodResponder
from app.voice.live2d.green_ntd_responder import GreenNTDResponder
from app.voice.live2d.live2d_interface import Live2DInterface
from app.voice.live2d.ntd_responder import NTDResponder
from app.voice.live2d.seed_responder import SeedFreedomResponder

logger = logging.getLogger(__name__)

# Short theme slugs (the keys in `cfg.voice.live2d.theme` and the
# responder's `THEME_ID`). 8 themes — all that the dashboard exposes.
_THEME_RESPONDERS: dict[str, type[Live2DInterface]] = {
    "ntd": NTDResponder,
    "seed": SeedFreedomResponder,
    "crossbone": CrossboneResponder,
    "gundam-ntd-green": GreenNTDResponder,
    "gundam-00": DoubleOResponder,
    "gundam-destiny": DestinyResponder,
    "gundam-god": GodResponder,
    "gundam-cartoon": CartoonResponder,
}

# Long-form (frontend) → short-form (backend) theme IDs.
# Frontend uses `GundamTheme` values from `types/api.ts`:
#   "gundam-ntd" | "gundam-seed" | "gundam-crossbone" |
#   "gundam-ntd-green" | "gundam-00" | "gundam-destiny" |
#   "gundam-god" | "gundam-cartoon"
#
# Backend prefers the short form so users can write `theme = "ntd"`
# in config.toml without the verbose prefix. The factory accepts
# both forms.
LONG_TO_SHORT: dict[str, str] = {
    "gundam-ntd": "ntd",
    "gundam-seed": "seed",
    "gundam-crossbone": "crossbone",
    "gundam-ntd-green": "gundam-ntd-green",  # already short
    "gundam-00": "gundam-00",  # already short
    "gundam-destiny": "gundam-destiny",
    "gundam-god": "gundam-god",
    "gundam-cartoon": "gundam-cartoon",
}


def _resolve_theme_key(theme: str) -> str:
    """Translate a frontend theme ID to the backend's short key.

    If the input is already a short key (or unknown), returns it
    unchanged so we surface a clear "Unknown theme" error rather
    than a silent miss.
    """
    if not theme:
        return ""
    short = LONG_TO_SHORT.get(theme, theme)
    return short.lower()


def create_live2d(
    config: VoiceLive2DConfig | None = None,
) -> Live2DInterface:
    """Build a Live2D trigger engine from config.

    Args:
        config: Live2D config. If None, reads from global config.

    Returns:
        A `Live2DInterface` implementation for the configured theme.

    Raises:
        ValueError: Unknown theme.
    """
    if config is None:
        from app.core.config import get_config

        config = get_config().voice.live2d

    theme = _resolve_theme_key(config.theme)
    responder_cls = _THEME_RESPONDERS.get(theme)

    if responder_cls is None:
        available = sorted(_THEME_RESPONDERS.keys())
        raise ValueError(
            f"Unknown Live2D theme {config.theme!r} (resolved to "
            f"{theme!r}). Available: {available}. "
            f"See ARCHITECTURE §15.14."
        )

    logger.info(
        f"[Live2D Factory] Creating {theme!r} responder "
        f"(model: {config.model_path})"
    )
    return responder_cls(config)


def available_themes() -> list[str]:
    """Return the list of registered theme keys (short form)."""
    return sorted(_THEME_RESPONDERS.keys())


__all__ = ["create_live2d", "available_themes", "LONG_TO_SHORT"]

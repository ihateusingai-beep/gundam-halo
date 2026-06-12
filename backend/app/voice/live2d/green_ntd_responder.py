"""GreenNTDResponder — Green Frame / Unicorn (Awakened) variant.

The Green Frame is the environmental-test cousin of the NT-D
Unicorn — the same character chassis, but with green psychoframe
activation instead of red. Where NT-D signals destructive
psychoframe blowout, Green signals stable, sustained awakenment.

Emotion vocabulary mirrors NT-D's exactly; the only difference
is the prefix (`gft_*` for "green frame") and one extra
"stable" expression slot. This makes theme switching between
NT-D and Green nearly free for the rest of the system.
"""

from __future__ import annotations

from app.voice.live2d.base_responder import BaseThemeResponder


class GreenNTDResponder(BaseThemeResponder):
    """Green Frame / Unicorn (green psychoframe) Live2D trigger engine."""

    THEME_ID = "gundam-ntd-green"
    FALLBACK_EXPRESSIONS = [
        "gft_calm",
        "gft_focused",
        "gft_psychoframe",
        "gft_alert",
        "gft_damage",
        "gft_resolve",
        "gft_jubilant",
        "gft_stealth",
        # Extra "stable" slot not in the red NT-D responder
        "gft_stable",
    ]
    FALLBACK_MOTION_GROUPS = [
        "idle",
        "lean_in",
        "awaken",
        "scan",
        "flinch",
        "stand",
        "victory",
        "vanish",
    ]


__all__ = ["GreenNTDResponder"]

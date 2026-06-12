"""CartoonResponder — Chibi / KAWAII cartoon theme Live2D trigger.

Cartoon / chibi is the cute, super-deformed theme. Big eyes,
oversized heads, sparkly expressions. The "kawaii" aesthetic
is its own emotional vocabulary — the motions are more
exaggerated, the expressions are more "anime reaction face".

Used as a relaxation/contrast theme — switching from NT-D's
grim psychoframe energy to chibi sparkles is a deliberate
mood reset.

Emotion vocabulary is anime-reaction: "sparkle", "teary",
"shocked", "blush", "pout". Motion vocabulary is the
chibi-flavored: "bounce", "wiggle", "twirl", plus a
"sparkle_burst" flourish for jubilant states.
"""

from __future__ import annotations

from app.voice.live2d.base_responder import BaseThemeResponder


class CartoonResponder(BaseThemeResponder):
    """Chibi / KAWAII cartoon Live2D trigger engine."""

    THEME_ID = "gundam-cartoon"
    FALLBACK_EXPRESSIONS = [
        "chibi_calm",
        "chibi_focused",
        "chibi_sparkle",
        "chibi_shocked",
        "chibi_damage",
        "chibi_resolve",
        "chibi_jubilant",
        "chibi_blush",
    ]
    FALLBACK_MOTION_GROUPS = [
        "idle",
        "bounce",
        "sparkle_burst",
        "wiggle",
        "flinch",
        "twirl",
        "victory_dance",
        "pout",
    ]


__all__ = ["CartoonResponder"]

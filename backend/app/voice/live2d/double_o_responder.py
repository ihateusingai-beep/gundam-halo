"""DoubleOResponder — Gundam 00 / QANT (Trans-Am) theme Live2D trigger.

Gundam 00's signature is Trans-Am — the GN Drive overload that
turns the entire frame red for ~30 seconds. The character is
Setsuna F. Seiei piloting the GN-0000 00 Qan[T]. The visual
signature: black + gold frame, with the GN particle effect on
Trans-Am activation.

Emotion vocabulary uses quantum-state metaphors ("coherent",
"entangled", "decoherent"). Motion vocabulary is the Trans-Am
arc: dormant → engaged → overload → back to dormant.
"""

from __future__ import annotations

from app.voice.live2d.base_responder import BaseThemeResponder


class DoubleOResponder(BaseThemeResponder):
    """Gundam 00 / Qan[T] Live2D trigger engine."""

    THEME_ID = "gundam-00"
    FALLBACK_EXPRESSIONS = [
        "00_calm",
        "00_focused",
        "00_transam",
        "00_alert",
        "00_damage",
        "00_resolve",
        "00_jubilant",
        "00_stealth",
    ]
    FALLBACK_MOTION_GROUPS = [
        "idle",
        "lean_in",
        "transam_engage",
        "scan",
        "flinch",
        "stand",
        "victory",
        "transam_dormant",
    ]


__all__ = ["DoubleOResponder"]

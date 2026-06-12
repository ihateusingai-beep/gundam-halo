"""DestinyResponder — Destiny Gundam / ZGMF-X42S theme Live2D trigger.

Destiny is the SEED Astray successor — Shinn Asuka piloting the
Wings-of-Light-enabled frame. The defining weapon is the beam
sword combo, and the visual signature is the prismatic wings
deploy that scatters light across the frame.

Emotion vocabulary is combat-arc: the closer Shinn gets to
resolve, the more the wings flare. Motion vocabulary centers
on the beam-sword flourish + wings-deploy fan.
"""

from __future__ import annotations

from app.voice.live2d.base_responder import BaseThemeResponder


class DestinyResponder(BaseThemeResponder):
    """Destiny Gundam / Wings of Light Live2D trigger engine."""

    THEME_ID = "gundam-destiny"
    FALLBACK_EXPRESSIONS = [
        "destiny_calm",
        "destiny_focused",
        "destiny_awakening",
        "destiny_alert",
        "destiny_damage",
        "destiny_resolve",
        "destiny_jubilant",
        "destiny_stealth",
    ]
    FALLBACK_MOTION_GROUPS = [
        "idle",
        "lean_in",
        "wings_deploy",
        "scan",
        "flinch",
        "stand",
        "victory",
        "wings_fold",
    ]


__all__ = ["DestinyResponder"]

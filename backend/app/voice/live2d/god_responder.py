"""GodResponder — God Gundam / Burning theme Live2D trigger.

God Gundam (G Gundam) is the martial arts Gundam — Domon Kasshu
piloting the GF13-017NJII. The character is defined by the
"Burning" mode where the frame's martial arts aura is visible
as flames around the user.

Emotion vocabulary is fighting-game + martial arts ("uppercut",
"combo", "flame"). Motion vocabulary maps to martial arts
moves: "jab", "kick", "combo_finisher", plus the iconic
"burning_aura" flourish.
"""

from __future__ import annotations

from app.voice.live2d.base_responder import BaseThemeResponder


class GodResponder(BaseThemeResponder):
    """God Gundam / Burning mode Live2D trigger engine."""

    THEME_ID = "gundam-god"
    FALLBACK_EXPRESSIONS = [
        "god_calm",
        "god_focused",
        "god_burning",
        "god_alert",
        "god_damage",
        "god_resolve",
        "god_jubilant",
        "god_stealth",
    ]
    FALLBACK_MOTION_GROUPS = [
        "idle",
        "jab",
        "burning_aura",
        "scan",
        "flinch",
        "kick",
        "combo_finisher",
        "vanish",
    ]


__all__ = ["GodResponder"]

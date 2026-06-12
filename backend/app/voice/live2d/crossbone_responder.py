"""CrossboneResponder — Crossbone Gundam X-1 theme Live2D trigger.

Crossbone X-1 (Kattobingu) is the pirate Gundam — skull-and-crossbones
motif, peach-red + black, pirate-cape aesthetic. Pilot: Kincade
(or Tobia in X-2). Character: cocky, fast, and lightly menacing.

Emotion vocabulary leans on the skull motif + pirate stance
("scowl", "smirk", "preen"). Motion vocabulary centers on the
X-1's signature chest beam shot — "core_blaster" — plus a
cape billow.
"""

from __future__ import annotations

from app.voice.live2d.base_responder import BaseThemeResponder


class CrossboneResponder(BaseThemeResponder):
    """Crossbone X-1 / pirate Gundam Live2D trigger engine."""

    THEME_ID = "crossbone"
    FALLBACK_EXPRESSIONS = [
        "crossbone_calm",
        "crossbone_focused",
        "crossbone_smirk",
        "crossbone_scowl",
        "crossbone_damage",
        "crossbone_resolve",
        "crossbone_jubilant",
        "crossbone_stealth",
    ]
    FALLBACK_MOTION_GROUPS = [
        "idle",
        "lean_in",
        "core_blaster",
        "scan",
        "flinch",
        "stand",
        "victory",
        "cape_billow",
    ]


__all__ = ["CrossboneResponder"]

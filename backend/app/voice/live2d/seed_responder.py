"""SeedFreedomResponder — SEED / Freedom theme Live2D trigger.

SEED's character: Kira Yamato piloting the ZGMF-X10A Freedom Gundam.
HiMAT (High Maneuver Aerial Tactical) wings spread, Phase Shift
armor. Color palette: red / white / gold with prismatic shine.

Emotion vocabulary uses the Phase Shift armor states as
metaphors (light pack on = focused, gold = jubilant, etc.)
Motion vocabulary tracks the hiMAT deploy / retract arc.
"""

from __future__ import annotations

from app.voice.live2d.base_responder import BaseThemeResponder


class SeedFreedomResponder(BaseThemeResponder):
    """SEED / Freedom Gundam Live2D trigger engine."""

    THEME_ID = "seed"
    FALLBACK_EXPRESSIONS = [
        "seed_calm",
        "seed_focused",
        "seed_phaseshift",
        "seed_alert",
        "seed_damage",
        "seed_resolve",
        "seed_jubilant",
        "seed_stealth",
    ]
    FALLBACK_MOTION_GROUPS = [
        "idle",
        "lean_in",
        "himat_deploy",
        "scan",
        "flinch",
        "stand",
        "victory",
        "himat_retract",
    ]


__all__ = ["SeedFreedomResponder"]

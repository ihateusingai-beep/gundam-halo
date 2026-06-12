"""NTDResponder — NT-D / Unicorn theme Live2D trigger (M3).

Implements `Live2DInterface` for the NT-D / Unicorn Gundam theme.
Thin subclass of `BaseThemeResponder` — declares the per-theme
fallback expression + motion names; everything else (model
loading, validation, trigger emission) is inherited.

The "Unicorn" character is the canonical Gundam Halo theme —
the default. The expression names are psychoframe-themed
(`ntd_calm`, `ntd_psychoframe`, …) and the motion groups are
narrative (`idle`, `awaken`, `victory`, `vanish`).

Usage:
    responder = NTDResponder(config)  # or from live2d_factory
    trigger = await responder.trigger("ntd_psychoframe", "awaken")
"""

from __future__ import annotations

from app.voice.live2d.base_responder import BaseThemeResponder


class NTDResponder(BaseThemeResponder):
    """NT-D / Unicorn Live2D trigger engine.

    Validates emotion → expression/motion against the actual
    `.model3.json` before emitting a trigger. If validation
    fails, falls back to the raw expression/motion names (the
    frontend can still try to play them).
    """

    THEME_ID = "ntd"
    FALLBACK_EXPRESSIONS = [
        "ntd_calm",
        "ntd_focused",
        "ntd_psychoframe",
        "ntd_alert",
        "ntd_damage",
        "ntd_resolve",
        "ntd_jubilant",
        "ntd_stealth",
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


__all__ = ["NTDResponder"]

"""Tests for the per-theme Live2D responders and the factory.

Covers:
- NTDResponder (refactored to use BaseThemeResponder)
- 7 new theme responders (Seed, Crossbone, Green, 00, Destiny, God, Cartoon)
- Each responder's THEME_ID, FALLBACK_EXPRESSIONS, FALLBACK_MOTION_GROUPS
- Each responder's expressions / motion_groups properties (using
  fallback lists when model metadata isn't loaded)
- The factory: registration, error on unknown, long→short mapping
"""

from __future__ import annotations

from unittest.mock import patch

import pytest


def _mock_completed_process(returncode=0, stdout="", stderr=""):
    import unittest.mock as _m
    cp = _m.MagicMock()
    cp.returncode = returncode
    cp.stdout = stdout
    cp.stderr = stderr
    return cp


# All tests use permissive config to enable voice.live2d
pytestmark = pytest.mark.usefixtures("permissive_test_config")


# --- NTDResponder (refactored) ---


def test_ntd_responder_has_expected_themE_id():
    from app.voice.live2d.ntd_responder import NTDResponder
    assert NTDResponder.THEME_ID == "ntd"


def test_ntd_responder_fallback_expressions_include_psychoframe():
    from app.voice.live2d.ntd_responder import NTDResponder
    assert "ntd_psychoframe" in NTDResponder.FALLBACK_EXPRESSIONS
    assert "ntd_calm" in NTDResponder.FALLBACK_EXPRESSIONS


def test_ntd_responder_fallback_motion_groups_include_awaken():
    from app.voice.live2d.ntd_responder import NTDResponder
    assert "awaken" in NTDResponder.FALLBACK_MOTION_GROUPS
    assert "victory" in NTDResponder.FALLBACK_MOTION_GROUPS


def test_ntd_responder_expressions_property_uses_fallback():
    from app.voice.live2d.ntd_responder import NTDResponder
    r = NTDResponder()
    # Without a real model, fallback list is used
    assert "ntd_psychoframe" in r.expressions


# --- SeedFreedomResponder ---


def test_seed_responder_themE_id():
    from app.voice.live2d.seed_responder import SeedFreedomResponder
    assert SeedFreedomResponder.THEME_ID == "seed"


def test_seed_responder_has_phaseshift_expression():
    from app.voice.live2d.seed_responder import SeedFreedomResponder
    assert "seed_phaseshift" in SeedFreedomResponder.FALLBACK_EXPRESSIONS


def test_seed_responder_has_himat_motions():
    from app.voice.live2d.seed_responder import SeedFreedomResponder
    assert "himat_deploy" in SeedFreedomResponder.FALLBACK_MOTION_GROUPS
    assert "himat_retract" in SeedFreedomResponder.FALLBACK_MOTION_GROUPS


# --- CrossboneResponder ---


def test_crossbone_responder_themE_id():
    from app.voice.live2d.crossbone_responder import CrossboneResponder
    assert CrossboneResponder.THEME_ID == "crossbone"


def test_crossbone_responder_has_smirk_and_scowl():
    from app.voice.live2d.crossbone_responder import CrossboneResponder
    exprs = CrossboneResponder.FALLBACK_EXPRESSIONS
    assert "crossbone_smirk" in exprs
    assert "crossbone_scowl" in exprs


def test_crossbone_responder_has_core_blaster_motion():
    from app.voice.live2d.crossbone_responder import CrossboneResponder
    assert "core_blaster" in CrossboneResponder.FALLBACK_MOTION_GROUPS


# --- GreenNTDResponder ---


def test_green_ntd_responder_themE_id():
    from app.voice.live2d.green_ntd_responder import GreenNTDResponder
    assert GreenNTDResponder.THEME_ID == "gundam-ntd-green"


def test_green_ntd_responder_has_stable_extra():
    """Green Frame has an extra `gft_stable` expression not in NT-D."""
    from app.voice.live2d.green_ntd_responder import GreenNTDResponder
    from app.voice.live2d.ntd_responder import NTDResponder
    assert "gft_stable" in GreenNTDResponder.FALLBACK_EXPRESSIONS
    assert "gft_stable" not in NTDResponder.FALLBACK_EXPRESSIONS


# --- DoubleOResponder ---


def test_double_o_responder_themE_id():
    from app.voice.live2d.double_o_responder import DoubleOResponder
    assert DoubleOResponder.THEME_ID == "gundam-00"


def test_double_o_responder_has_transam_motions():
    from app.voice.live2d.double_o_responder import DoubleOResponder
    motions = DoubleOResponder.FALLBACK_MOTION_GROUPS
    assert "transam_engage" in motions
    assert "transam_dormant" in motions


# --- DestinyResponder ---


def test_destiny_responder_themE_id():
    from app.voice.live2d.destiny_responder import DestinyResponder
    assert DestinyResponder.THEME_ID == "gundam-destiny"


def test_destiny_responder_has_wings_motions():
    from app.voice.live2d.destiny_responder import DestinyResponder
    motions = DestinyResponder.FALLBACK_MOTION_GROUPS
    assert "wings_deploy" in motions
    assert "wings_fold" in motions


# --- GodResponder ---


def test_god_responder_themE_id():
    from app.voice.live2d.god_responder import GodResponder
    assert GodResponder.THEME_ID == "gundam-god"


def test_god_responder_has_martial_arts_motions():
    """God's motion vocabulary is martial-arts themed, not generic."""
    from app.voice.live2d.god_responder import GodResponder
    motions = GodResponder.FALLBACK_MOTION_GROUPS
    assert "jab" in motions
    assert "kick" in motions
    assert "burning_aura" in motions
    assert "combo_finisher" in motions


# --- CartoonResponder ---


def test_cartoon_responder_themE_id():
    from app.voice.live2d.cartoon_responder import CartoonResponder
    assert CartoonResponder.THEME_ID == "gundam-cartoon"


def test_cartoon_responder_has_kawaii_expressions():
    from app.voice.live2d.cartoon_responder import CartoonResponder
    exprs = CartoonResponder.FALLBACK_EXPRESSIONS
    assert "chibi_sparkle" in exprs
    assert "chibi_blush" in exprs


def test_cartoon_responder_pout_is_motion_not_expression():
    """Pout is a body language motion, not a facial expression."""
    from app.voice.live2d.cartoon_responder import CartoonResponder
    assert "pout" in CartoonResponder.FALLBACK_MOTION_GROUPS
    assert "chibi_pout" not in CartoonResponder.FALLBACK_EXPRESSIONS


def test_cartoon_responder_has_chibi_motions():
    from app.voice.live2d.cartoon_responder import CartoonResponder
    motions = CartoonResponder.FALLBACK_MOTION_GROUPS
    assert "bounce" in motions
    assert "wiggle" in motions
    assert "twirl" in motions
    assert "sparkle_burst" in motions


# --- Base class contract ---


def test_all_responders_inherit_from_base():
    """Every concrete responder must subclass BaseThemeResponder."""
    from app.voice.live2d.base_responder import BaseThemeResponder
    from app.voice.live2d.cartoon_responder import CartoonResponder
    from app.voice.live2d.crossbone_responder import CrossboneResponder
    from app.voice.live2d.destiny_responder import DestinyResponder
    from app.voice.live2d.double_o_responder import DoubleOResponder
    from app.voice.live2d.god_responder import GodResponder
    from app.voice.live2d.green_ntd_responder import GreenNTDResponder
    from app.voice.live2d.ntd_responder import NTDResponder
    from app.voice.live2d.seed_responder import SeedFreedomResponder

    for cls in (
        NTDResponder,
        SeedFreedomResponder,
        CrossboneResponder,
        GreenNTDResponder,
        DoubleOResponder,
        DestinyResponder,
        GodResponder,
        CartoonResponder,
    ):
        assert issubclass(cls, BaseThemeResponder), f"{cls.__name__} is not a BaseThemeResponder subclass"


def test_each_responder_has_unique_theme_id():
    """No two responders may share a THEME_ID — would break factory lookup."""
    from app.voice.live2d.cartoon_responder import CartoonResponder
    from app.voice.live2d.crossbone_responder import CrossboneResponder
    from app.voice.live2d.destiny_responder import DestinyResponder
    from app.voice.live2d.double_o_responder import DoubleOResponder
    from app.voice.live2d.god_responder import GodResponder
    from app.voice.live2d.green_ntd_responder import GreenNTDResponder
    from app.voice.live2d.ntd_responder import NTDResponder
    from app.voice.live2d.seed_responder import SeedFreedomResponder

    themes = [
        cls.THEME_ID
        for cls in (
            NTDResponder,
            SeedFreedomResponder,
            CrossboneResponder,
            GreenNTDResponder,
            DoubleOResponder,
            DestinyResponder,
            GodResponder,
            CartoonResponder,
        )
    ]
    assert len(themes) == len(set(themes)), f"Duplicate THEME_IDs: {themes}"


def test_each_responder_has_non_empty_fallbacks():
    from app.voice.live2d.cartoon_responder import CartoonResponder
    from app.voice.live2d.crossbone_responder import CrossboneResponder
    from app.voice.live2d.destiny_responder import DestinyResponder
    from app.voice.live2d.double_o_responder import DoubleOResponder
    from app.voice.live2d.god_responder import GodResponder
    from app.voice.live2d.green_ntd_responder import GreenNTDResponder
    from app.voice.live2d.ntd_responder import NTDResponder
    from app.voice.live2d.seed_responder import SeedFreedomResponder

    for cls in (
        NTDResponder,
        SeedFreedomResponder,
        CrossboneResponder,
        GreenNTDResponder,
        DoubleOResponder,
        DestinyResponder,
        GodResponder,
        CartoonResponder,
    ):
        assert len(cls.FALLBACK_EXPRESSIONS) >= 5, f"{cls.__name__} too few expressions"
        assert len(cls.FALLBACK_MOTION_GROUPS) >= 5, f"{cls.__name__} too few motion groups"


# --- Factory tests ---


def test_factory_returns_correct_responder_for_each_short_theme():
    """Factory must return the right responder for each registered short theme."""
    from app.core import config as _config_module
    from app.voice.live2d.cartoon_responder import CartoonResponder
    from app.voice.live2d.crossbone_responder import CrossboneResponder
    from app.voice.live2d.destiny_responder import DestinyResponder
    from app.voice.live2d.double_o_responder import DoubleOResponder
    from app.voice.live2d.god_responder import GodResponder
    from app.voice.live2d.green_ntd_responder import GreenNTDResponder
    from app.voice.live2d.live2d_factory import create_live2d
    from app.voice.live2d.ntd_responder import NTDResponder
    from app.voice.live2d.seed_responder import SeedFreedomResponder

    cfg = _config_module.get_config()
    expected = {
        "ntd": NTDResponder,
        "seed": SeedFreedomResponder,
        "crossbone": CrossboneResponder,
        "gundam-ntd-green": GreenNTDResponder,
        "gundam-00": DoubleOResponder,
        "gundam-destiny": DestinyResponder,
        "gundam-god": GodResponder,
        "gundam-cartoon": CartoonResponder,
    }
    for theme, expected_cls in expected.items():
        cfg.voice.live2d.theme = theme
        responder = create_live2d()
        assert isinstance(responder, expected_cls), (
            f"Theme {theme!r} returned {type(responder).__name__}, "
            f"expected {expected_cls.__name__}"
        )


def test_factory_accepts_frontend_long_theme_ids():
    """Frontend uses 'gundam-ntd' etc. — factory must accept them too."""
    from app.core import config as _config_module
    from app.voice.live2d.double_o_responder import DoubleOResponder
    from app.voice.live2d.live2d_factory import create_live2d
    from app.voice.live2d.ntd_responder import NTDResponder

    cfg = _config_module.get_config()

    # Long form resolves to short
    cfg.voice.live2d.theme = "gundam-ntd"
    assert isinstance(create_live2d(), NTDResponder)

    cfg.voice.live2d.theme = "gundam-00"
    assert isinstance(create_live2d(), DoubleOResponder)

    cfg.voice.live2d.theme = "gundam-cartoon"
    from app.voice.live2d.cartoon_responder import CartoonResponder
    assert isinstance(create_live2d(), CartoonResponder)


def test_factory_raises_on_unknown_theme():
    from app.core import config as _config_module
    from app.voice.live2d.live2d_factory import create_live2d

    cfg = _config_module.get_config()
    cfg.voice.live2d.theme = "no-such-theme"
    with pytest.raises(ValueError, match="Unknown Live2D theme"):
        create_live2d()


def test_factory_raises_on_empty_theme():
    from app.core import config as _config_module
    from app.voice.live2d.live2d_factory import create_live2d

    cfg = _config_module.get_config()
    cfg.voice.live2d.theme = ""
    with pytest.raises(ValueError, match="Unknown Live2D theme"):
        create_live2d()


def test_available_themes_returns_all_eight():
    from app.voice.live2d.live2d_factory import available_themes

    themes = available_themes()
    assert len(themes) == 8
    # The factory has 8 short keys; the LONG_TO_SHORT map handles
    # the long-form frontend IDs (gundam-ntd, gundam-seed,
    # gundam-crossbone) by mapping to the short keys. The other 5
    # frontend IDs (gundam-ntd-green, gundam-00, gundam-destiny,
    # gundam-god, gundam-cartoon) are themselves registered as
    # short keys.
    expected_short = {
        "ntd", "seed", "crossbone", "gundam-ntd-green", "gundam-00",
        "gundam-destiny", "gundam-god", "gundam-cartoon",
    }
    assert set(themes) == expected_short

    # Now exercise the long→short mapping: every frontend theme
    # must resolve to a registered short key.
    frontend_themes = {
        "gundam-ntd", "gundam-seed", "gundam-crossbone",
        "gundam-ntd-green", "gundam-00", "gundam-destiny",
        "gundam-god", "gundam-cartoon",
    }
    from app.voice.live2d.live2d_factory import LONG_TO_SHORT, _resolve_theme_key
    for long_id in frontend_themes:
        short = _resolve_theme_key(long_id)
        assert short in expected_short, (
            f"Frontend theme {long_id!r} resolves to {short!r}, "
            f"which isn't a registered short key"
        )


# --- Trigger behavior ---


def test_ntd_responder_trigger_emits_validated_names():
    """Trigger returns the expression + motion names (validation is
    best-effort — invalid names are still emitted)."""
    import asyncio
    from app.voice.live2d.ntd_responder import NTDResponder

    r = NTDResponder()
    trigger = asyncio.run(r.trigger("ntd_calm", "idle"))
    assert trigger.expression == "ntd_calm"
    assert trigger.motion == "idle"


def test_ntd_responder_trigger_emits_unknown_names_too():
    """Per the contract: validation is best-effort. Unknown names
    are still emitted so the frontend can try to play them or
    fall back to a default."""
    import asyncio
    from app.voice.live2d.ntd_responder import NTDResponder

    r = NTDResponder()
    trigger = asyncio.run(r.trigger("ntd_bogus_expr", "unknown_motion"))
    assert trigger.expression == "ntd_bogus_expr"
    assert trigger.motion == "unknown_motion"


def test_motion_with_colon_is_split_for_validation():
    """Motion strings like 'awaken:slow' should validate against the
    group ('awaken'), not the full string."""
    import asyncio
    from app.voice.live2d.ntd_responder import NTDResponder

    r = NTDResponder()
    # Even with a colon-suffixed motion, the name is preserved
    trigger = asyncio.run(r.trigger("ntd_calm", "awaken:slow"))
    assert trigger.motion == "awaken:slow"


def test_responder_warmup_does_not_raise_without_metadata():
    """Warmup is a no-op when no model metadata is present."""
    import asyncio
    from app.voice.live2d.seed_responder import SeedFreedomResponder

    r = SeedFreedomResponder()
    # Should not raise — it just logs a debug message
    asyncio.run(r.warmup())

"""Tests for Live2D model metadata parser and NTDResponder."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from app.voice.live2d.model_metadata import ModelMetadata, MotionInfo
from app.voice.live2d.ntd_responder import NTDResponder
from app.core.config import VoiceLive2DConfig


class TestModelMetadata:
    """Tests for ModelMetadata parser."""

    def _make_model_json(self, expressions=None, motions=None, hit_areas=None):
        """Helper: build a minimal .model3.json dict."""
        data = {
            "name": "Hiyori",
            "FileReferences": {
                "Expressions": expressions or [],
                "Motions": motions or {},
            },
            "HitAreas": hit_areas or [],
        }
        return json.dumps(data, ensure_ascii=False)

    def test_parses_expressions_as_strings(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "hiyori.model3.json"
            p.write_text(self._make_model_json(expressions=[
                "expressions/angry.exp3.json",
                "expressions/happy.exp3.json",
            ]))
            meta = ModelMetadata.from_path(p)
            assert meta.name == "Hiyori"
            assert "angry" in meta.expressions
            assert "happy" in meta.expressions
            assert len(meta.expression_infos) == 2

    def test_parses_expressions_as_objects(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "hiyori.model3.json"
            p.write_text(self._make_model_json(expressions=[
                {"Name": "Angry", "File": "expressions/angry.exp3.json"},
                {"Name": "Surprised", "File": "expressions/surprised.exp3.json"},
            ]))
            meta = ModelMetadata.from_path(p)
            assert "Angry" in meta.expressions
            assert "Surprised" in meta.expressions

    def test_parses_motion_groups(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "hiyori.model3.json"
            p.write_text(self._make_model_json(motions={
                "Idle": [
                    {"File": "motions/idle_01.motion3.json", "Sound": "motions/idle_01.wav"},
                    {"File": "motions/idle_02.motion3.json"},
                ],
                "TapBody": [
                    {"File": "motions/tap_body_01.motion3.json"},
                ],
            }))
            meta = ModelMetadata.from_path(p)
            assert "Idle" in meta.motion_groups
            assert "TapBody" in meta.motion_groups
            assert len(meta.motion_groups["Idle"]) == 2
            assert meta.motion_groups["Idle"][0].file == "motions/idle_01.motion3.json"
            assert meta.motion_groups["Idle"][0].sound == "motions/idle_01.wav"
            assert meta.motion_groups["TapBody"][0].file == "motions/tap_body_01.motion3.json"

    def test_validate_expression(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "hiyori.model3.json"
            p.write_text(self._make_model_json(expressions=[
                "expressions/angry.exp3.json",
                "expressions/happy.exp3.json",
            ]))
            meta = ModelMetadata.from_path(p)
            assert meta.validate_expression("angry") is True
            assert meta.validate_expression("happy") is True
            assert meta.validate_expression("unknown") is False

    def test_validate_motion_group(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "hiyori.model3.json"
            p.write_text(self._make_model_json(motions={
                "Idle": [{"File": "motions/idle.motion3.json"}],
            }))
            meta = ModelMetadata.from_path(p)
            assert meta.validate_motion("Idle") is True
            assert meta.validate_motion("Talk") is False

    def test_validate_motion_group_and_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "hiyori.model3.json"
            p.write_text(self._make_model_json(motions={
                "Idle": [
                    {"File": "motions/idle_0.motion3.json"},
                    {"File": "motions/idle_1.motion3.json"},
                ],
            }))
            meta = ModelMetadata.from_path(p)
            assert meta.validate_motion("Idle", 0) is True
            assert meta.validate_motion("Idle", 1) is True
            assert meta.validate_motion("Idle", 2) is False  # out of range
            assert meta.validate_motion("Idle", -1) is False

    def test_validate_emotion_map(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "hiyori.model3.json"
            p.write_text(self._make_model_json(
                expressions=["expressions/angry.exp3.json"],
                motions={"Idle": [{"File": "motions/idle.motion3.json"}]},
            ))
            meta = ModelMetadata.from_path(p)

            # All valid
            errors = meta.validate_emotion_map({
                "calm": {"expr": "angry", "motion": "Idle"},
            })
            assert errors == []

            # Invalid expression
            errors = meta.validate_emotion_map({
                "calm": {"expr": "nonexistent", "motion": "Idle"},
            })
            assert len(errors) == 1
            assert "nonexistent" in errors[0]

            # Invalid motion group
            errors = meta.validate_emotion_map({
                "calm": {"expr": "angry", "motion": "NonExistent"},
            })
            assert len(errors) == 1
            assert "NonExistent" in errors[0]

    def test_from_json_string(self):
        meta = ModelMetadata.from_json_string(self._make_model_json(expressions=[
            "expressions/angry.exp3.json",
        ]))
        assert "angry" in meta.expressions
        assert meta.model_dir == Path(".")

    def test_repr(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "hiyori.model3.json"
            p.write_text(self._make_model_json(expressions=[], motions={}))
            meta = ModelMetadata.from_path(p)
            r = repr(meta)
            assert "Hiyori" in r
            assert "expressions" in r


class TestNTDResponder:
    """Tests for NTDResponder."""

    def test_responder_loads_without_model(self, tmp_path):
        """NTDResponder should not raise even if model3.json is missing."""
        cfg = VoiceLive2DConfig(
            enabled=True,
            theme="ntd",
            model_path=str(tmp_path / "nonexistent"),
        )
        responder = NTDResponder(cfg)
        assert responder.model_name  # non-empty
        # Should not raise
        import asyncio
        asyncio.run(responder.warmup())

    def test_responder_validates_and_emits_trigger(self, tmp_path):
        """trigger() should validate and return Live2DTrigger."""
        cfg = VoiceLive2DConfig(
            enabled=True,
            theme="ntd",
            model_path=str(tmp_path),
        )
        responder = NTDResponder(cfg)
        import asyncio
        asyncio.run(responder.warmup())

        trigger = asyncio.run(responder.trigger("ntd_calm", "idle"))
        assert trigger.expression == "ntd_calm"
        assert trigger.motion == "idle"

    def test_responder_emits_raw_names_when_not_in_model(self, tmp_path):
        """trigger() should emit raw names even if not in model metadata."""
        cfg = VoiceLive2DConfig(
            enabled=True,
            theme="ntd",
            model_path=str(tmp_path),
        )
        responder = NTDResponder(cfg)
        import asyncio
        asyncio.run(responder.warmup())

        # Unknown expression — still returns it (frontend can try)
        trigger = asyncio.run(responder.trigger("made_up_expr", "made_up_motion"))
        assert trigger.expression == "made_up_expr"
        assert trigger.motion == "made_up_motion"

    def test_responder_parses_motion_with_index(self, tmp_path):
        cfg = VoiceLive2DConfig(enabled=True, theme="ntd", model_path=str(tmp_path))
        responder = NTDResponder(cfg)
        import asyncio
        asyncio.run(responder.warmup())

        # Motion with index: "Idle:1" → motion="Idle:1", motion_group="Idle"
        trigger = asyncio.run(responder.trigger("ntd_calm", "Idle:1"))
        assert trigger.motion == "Idle:1"

    def test_responder_properties(self, tmp_path):
        cfg = VoiceLive2DConfig(
            enabled=True,
            theme="ntd",
            model_path=str(tmp_path / "models" / "hiyori"),
        )
        responder = NTDResponder(cfg)
        # Fallback expressions when no model loaded
        assert len(responder.expressions) > 0
        assert len(responder.motion_groups) > 0
        assert "ntd_calm" in responder.expressions
        assert "idle" in responder.motion_groups
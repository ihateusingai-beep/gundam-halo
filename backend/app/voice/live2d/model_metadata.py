"""Model metadata parser — M3.

Reads a Live2D `.model3.json` file and extracts the available
expressions and motion groups. Used by NTDResponder to validate
that emotion → expression/motion mappings reference real model assets
before triggering them.

The parser handles:
- FileReferences.Motions (motion groups → file list)
- FileReferences.Expressions (name → file)
- HitAreas (for tap-to-motion)
- Canvas / sizes (for layout)

Example:
    >>> meta = ModelMetadata.from_path(Path("~/models/hiyori/hiyori.model3.json"))
    >>> meta.expressions
    ["Angry", "Happy", "Surprised"]
    >>> meta.motion_groups
    ["Idle", "TapBody", "Talk"]
    >>> meta.validate_expression("Angry")
    True
    >>> meta.validate_motion("Idle", 0)
    True
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class MotionInfo:
    """One motion clip inside a group."""

    index: int
    file: str  # relative path, e.g. "motions/idle_01.motion3.json"
    sound: str | None = None


@dataclass
class ExpressionInfo:
    """One expression (facial expression) available on the model."""

    name: str  # e.g. "Angry", "ntd_calm"
    file: str  # relative path, e.g. "expressions/angry.exp3.json"


@dataclass
class HitArea:
    """One tap hit area on the model."""

    name: str  # e.g. "Head", "Body"
    id: str | None = None


@dataclass
class ModelMetadata:
    """Extracted metadata from a .model3.json file."""

    name: str  # display name (from FileReferences or model name)
    model_dir: Path  # directory containing the .model3.json
    expressions: list[str] = field(default_factory=list)
    expression_infos: list[ExpressionInfo] = field(default_factory=list)
    motion_groups: dict[str, list[MotionInfo]] = field(default_factory=dict)
    hit_areas: list[HitArea] = field(default_factory=list)
    canvas_width: float | None = None
    canvas_height: float | None = None

    # Raw JSON for advanced use (motion settings, etc.)
    raw: dict = field(default_factory=dict)

    @classmethod
    def from_path(cls, path: Path) -> ModelMetadata:
        """Parse a .model3.json file at *path*."""
        path = path.expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"Model file not found: {path}")

        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)

        model_dir = path.parent
        name = raw.get("name", model_dir.name)

        # Expressions
        expr_files = raw.get("FileReferences", {}).get("Expressions", [])
        expression_infos: list[ExpressionInfo] = []
        expression_names: list[str] = []

        for ef in expr_files:
            if isinstance(ef, str):
                # Simple string: "expressions/angry.exp3.json"
                expr_name = Path(ef).stem.replace(".exp3", "").replace(".exp.json", "")
                expression_infos.append(ExpressionInfo(name=expr_name, file=ef))
                expression_names.append(expr_name)
            elif isinstance(ef, dict):
                # Object: {"Name": "Angry", "File": "expressions/angry.exp3.json"}
                expr_name = ef.get("Name", Path(ef.get("File", "")).stem)
                expression_infos.append(ExpressionInfo(name=expr_name, file=ef["File"]))
                expression_names.append(expr_name)

        # Motions
        motion_groups: dict[str, list[MotionInfo]] = {}
        motion_refs = raw.get("FileReferences", {}).get("Motions", {})
        for group_name, motions in motion_refs.items():
            group_motions: list[MotionInfo] = []
            for idx, m in enumerate(motions):
                if isinstance(m, str):
                    group_motions.append(MotionInfo(index=idx, file=m))
                elif isinstance(m, dict):
                    group_motions.append(
                        MotionInfo(
                            index=idx,
                            file=m.get("File", ""),
                            sound=m.get("Sound"),
                        )
                    )
            motion_groups[group_name] = group_motions

        # Hit areas
        hit_areas: list[HitArea] = []
        for ha in raw.get("HitAreas", []):
            hit_areas.append(HitArea(name=ha.get("Name", ""), id=ha.get("Id")))

        # Canvas dimensions
        canvas_width = raw.get("Canvas", {}).get("Width")
        canvas_height = raw.get("Canvas", {}).get("Height")

        return cls(
            name=name,
            model_dir=model_dir,
            expressions=expression_names,
            expression_infos=expression_infos,
            motion_groups=motion_groups,
            hit_areas=hit_areas,
            canvas_width=canvas_width,
            canvas_height=canvas_height,
            raw=raw,
        )

    @classmethod
    def from_json_string(cls, json_str: str, model_dir: Path | None = None) -> ModelMetadata:
        """Parse from a JSON string (useful for testing / embedded models)."""
        raw = json.loads(json_str)
        model_dir = model_dir or Path(".")

        name = raw.get("name", "model")
        expr_files = raw.get("FileReferences", {}).get("Expressions", [])
        expression_infos: list[ExpressionInfo] = []
        expression_names: list[str] = []
        for ef in expr_files:
            if isinstance(ef, str):
                expr_name = Path(ef).stem.replace(".exp3", "").replace(".exp.json", "")
                expression_infos.append(ExpressionInfo(name=expr_name, file=ef))
                expression_names.append(expr_name)
            elif isinstance(ef, dict):
                expr_name = ef.get("Name", Path(ef.get("File", "")).stem)
                expression_infos.append(ExpressionInfo(name=expr_name, file=ef["File"]))
                expression_names.append(expr_name)

        motion_groups: dict[str, list[MotionInfo]] = {}
        motion_refs = raw.get("FileReferences", {}).get("Motions", {})
        for group_name, motions in motion_refs.items():
            group_motions: list[MotionInfo] = []
            for idx, m in enumerate(motions):
                if isinstance(m, str):
                    group_motions.append(MotionInfo(index=idx, file=m))
                elif isinstance(m, dict):
                    group_motions.append(
                        MotionInfo(index=idx, file=m.get("File", ""), sound=m.get("Sound"))
                    )
            motion_groups[group_name] = group_motions

        hit_areas: list[HitArea] = []
        for ha in raw.get("HitAreas", []):
            hit_areas.append(HitArea(name=ha.get("Name", ""), id=ha.get("Id")))

        return cls(
            name=name,
            model_dir=model_dir,
            expressions=expression_names,
            expression_infos=expression_infos,
            motion_groups=motion_groups,
            hit_areas=hit_areas,
            canvas_width=raw.get("Canvas", {}).get("Width"),
            canvas_height=raw.get("Canvas", {}).get("Height"),
            raw=raw,
        )

    def validate_expression(self, expression_name: str) -> bool:
        """Check if *expression_name* exists on this model."""
        return expression_name in self.expressions

    def validate_motion(self, motion_group: str, motion_index: int | None = None) -> bool:
        """Check if a motion group (and optionally index) exists.

        Args:
            motion_group: e.g. "Idle", "Talk"
            motion_index: if None, just checks group exists
        """
        if motion_group not in self.motion_groups:
            return False
        if motion_index is not None:
            group = self.motion_groups[motion_group]
            return 0 <= motion_index < len(group)
        return True

    def validate_emotion_map(
        self, emotion_map: dict[str, dict]
    ) -> list[str]:
        """Validate an emotion → expression/motion mapping dict.

        Returns a list of validation errors (empty = all valid).
        Each error is a human-readable string.
        """
        errors: list[str] = []
        for emotion, cfg in emotion_map.items():
            expr = cfg.get("expr", "")
            motion = cfg.get("motion", "")

            if expr and not self.validate_expression(expr):
                errors.append(
                    f"Emotion '{emotion}': expression '{expr}' not found on model. "
                    f"Available: {self.expressions}"
                )

            # Extract group name from motion (motion can be "Idle" or "Idle:0")
            motion_group = motion.split(":")[0] if motion else ""
            if motion_group and not self.validate_motion(motion_group):
                available_groups = list(self.motion_groups.keys())
                errors.append(
                    f"Emotion '{emotion}': motion group '{motion_group}' not found. "
                    f"Available: {available_groups}"
                )

        return errors

    def __repr__(self) -> str:
        return (
            f"ModelMetadata(name={self.name!r}, "
            f"expressions={self.expressions}, "
            f"motion_groups={list(self.motion_groups.keys())})"
        )
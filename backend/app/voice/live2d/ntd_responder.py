"""NTDResponder — NT-D / Unicorn theme Live2D trigger (M3).

Implements `Live2DInterface` for the NT-D / Unicorn Gundam theme.
Validates expression/motion names against the actual model metadata
before triggering. If the model is not yet loaded, emits the trigger
anyway so the frontend can animate a placeholder or log the intent.

Usage:
    responder = NTDResponder(config)  # or from live2d_factory
    trigger = await responder.trigger("ntd_psychoframe", "awaken")
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.core.config import VoiceLive2DConfig
from app.voice.live2d.live2d_interface import Live2DInterface, Live2DTrigger
from app.voice.live2d.model_metadata import ModelMetadata

logger = logging.getLogger(__name__)

# Fallback expressions/motions when model metadata is not yet loaded.
# Used so the backend still emits WS frames even if the model is absent.
_FALLBACK_EXPRESSIONS = [
    "ntd_calm",
    "ntd_focused",
    "ntd_psychoframe",
    "ntd_alert",
    "ntd_damage",
    "ntd_resolve",
    "ntd_jubilant",
    "ntd_stealth",
]
_FALLBACK_MOTION_GROUPS = ["idle", "lean_in", "awaken", "scan", "flinch", "stand", "victory", "vanish"]


class NTDResponder(Live2DInterface):
    """NT-D / Unicorn Live2D trigger engine.

    Validates emotion → expression/motion against the actual `.model3.json`
    before emitting a trigger. If validation fails, falls back to the
    raw expression/motion names (the frontend can still try to play them).
    """

    def __init__(
        self,
        config: VoiceLive2DConfig | None = None,
        *,
        model_path: str | Path | None = None,
    ) -> None:
        from app.core.config import get_config

        cfg = config or get_config().voice.live2d

        self._theme = cfg.theme
        self._default_emotion = cfg.default_emotion

        # Resolve model path
        raw_model_path = model_path or cfg.model_path
        self._model_dir = Path(raw_model_path).expanduser().resolve()
        self._model3_path = self._find_model3(self._model_dir)

        # Load metadata (None if not found — will use fallbacks)
        self._meta: ModelMetadata | None = None
        if self._model3_path and self._model3_path.exists():
            try:
                self._meta = ModelMetadata.from_path(self._model3_path)
                logger.info(f"[NTDResponder] Loaded model metadata: {self._meta}")
            except Exception as e:
                logger.warning(f"[NTDResponder] Failed to parse model metadata: {e}")

        # If no metadata, report what we would use
        if self._meta is None:
            logger.warning(
                f"[NTDResponder] Model metadata not loaded. "
                f"Model dir: {self._model_dir}, model3_path: {self._model3_path}. "
                f"Triggering with raw expression/motion names (frontend will try)."
            )

    def _find_model3(self, model_dir: Path) -> Path | None:
        """Find the .model3.json file in *model_dir*."""
        if not model_dir.is_dir():
            return None

        candidates = list(model_dir.glob("*.model3.json"))
        if len(candidates) == 1:
            return candidates[0]
        elif len(candidates) > 1:
            logger.warning(
                f"[NTDResponder] Multiple .model3.json files in {model_dir}, "
                f"using first: {candidates[0]}"
            )
            return candidates[0]
        else:
            # No .model3.json found — check one level deeper (model_dir/name/name.model3.json)
            for sub in model_dir.iterdir():
                if sub.is_dir():
                    deeper = list(sub.glob("*.model3.json"))
                    if deeper:
                        return deeper[0]
            return None

    async def warmup(self) -> None:
        """Validate that the model metadata is accessible."""
        if self._meta is None:
            logger.debug(
                f"[NTDResponder] warmup: no model metadata at {self._model3_path}. "
                f"Using fallbacks."
            )
            return

        # Validate that the fallback expressions are present
        missing_expr = [e for e in _FALLBACK_EXPRESSIONS if not self._meta.validate_expression(e)]
        missing_motion = [g for g in _FALLBACK_MOTION_GROUPS if not self._meta.validate_motion(g)]
        if missing_expr:
            logger.warning(
                f"[NTDResponder] Model '{self._meta.name}' missing expressions: {missing_expr}. "
                f"Available: {self._meta.expressions}"
            )
        if missing_motion:
            logger.warning(
                f"[NTDResponder] Model '{self._meta.name}' missing motion groups: {missing_motion}. "
                f"Available: {list(self._meta.motion_groups.keys())}"
            )

    async def trigger(
        self, expression: str, motion: str
    ) -> Live2DTrigger:
        """Validate and emit a Live2D trigger.

        The expression and motion names come from `EMOTION_MAP` in
        `halo_responder.py`. We validate them against the actual model
        metadata (if loaded), then return the trigger.

        If validation fails, we still return the raw names — the frontend
        may have a different model or handle missing assets gracefully.
        """
        # Validate expression
        validated_expr = expression
        if self._meta and not self._meta.validate_expression(expression):
            logger.warning(
                f"[NTDResponder] Expression '{expression}' not in model "
                f"'{self._meta.name}'. Available: {self._meta.expressions}"
            )
            validated_expr = expression  # Still emit the raw name

        # Validate motion group
        motion_group = motion.split(":")[0] if motion else ""
        validated_motion = motion
        if self._meta and motion_group and not self._meta.validate_motion(motion_group):
            logger.warning(
                f"[NTDResponder] Motion group '{motion_group}' not in model "
                f"'{self._meta.name}'. Available: {list(self._meta.motion_groups.keys())}"
            )
            validated_motion = motion  # Still emit the raw name

        logger.debug(
            f"[NTDResponder] trigger: expression={validated_expr}, motion={validated_motion}"
        )

        return Live2DTrigger(expression=validated_expr, motion=validated_motion)

    @property
    def model_name(self) -> str:
        """Human-readable model name (from metadata or path)."""
        if self._meta:
            return self._meta.name
        return self._model_dir.name

    @property
    def model_path(self) -> Path:
        return self._model_dir

    @property
    def model3_path(self) -> Path | None:
        return self._model3_path

    @property
    def expressions(self) -> list[str]:
        """Available expressions (from metadata or fallbacks)."""
        if self._meta:
            return self._meta.expressions
        return _FALLBACK_EXPRESSIONS

    @property
    def motion_groups(self) -> list[str]:
        """Available motion groups (from metadata or fallbacks)."""
        if self._meta:
            return list(self._meta.motion_groups.keys())
        return _FALLBACK_MOTION_GROUPS


__all__ = ["NTDResponder"]
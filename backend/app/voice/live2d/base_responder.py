"""Base class for theme-specific Live2D responders.

`NTDResponder` (M3) was the first concrete responder; as we add
the other 7 themes, the boilerplate becomes identical across
every implementation. This base class:

- Reads config + resolves model_path + finds the .model3.json
- Loads ModelMetadata (or falls back gracefully)
- Provides the validation + emit flow in `trigger()`
- Exposes `expressions` / `motion_groups` / `model_name` properties

Subclasses declare three things and nothing else:

1. `THEME_ID` — the short theme slug (e.g. "seed", "gundam-00").
   This is the value looked up in `live2d_factory._THEME_RESPONDERS`.
2. `FALLBACK_EXPRESSIONS` — the expression-name list to use when
   the model metadata isn't loaded (placeholder behavior, so the
   frontend can still try to play the raw names).
3. `FALLBACK_MOTION_GROUPS` — the motion-group list for the same
   fallback case.

The theme's *character* — what motion should fire on `awaken` vs
`damage` vs `victory` — is owned by the per-theme
`TOOL_MOTION_MAP` override in `tool_motion_mapper.py` and the
LLM-driven emotion DSL in `halo_responder.py`. The responder only
validates and emits.

Why a base class (not a single mega-class with a theme arg):
- Each theme's fallback expression/motion names are stable,
  type-checked class attributes — easy to inspect / test.
- Future per-theme quirks (e.g. SEED needing 4-frame composite
  expressions) can be added in the subclass without touching
  the others.
- The NTDResponder subclass still exists (for backward compat
  with code that imports it by name), but it's now a thin
  subclass of this base.
"""
from __future__ import annotations

import logging
from abc import abstractmethod
from pathlib import Path

from app.core.config import VoiceLive2DConfig
from app.voice.live2d.live2d_interface import Live2DInterface, Live2DTrigger
from app.voice.live2d.model_metadata import ModelMetadata

logger = logging.getLogger(__name__)


class BaseThemeResponder(Live2DInterface):
    """Shared Live2D responder behavior for all Gundam themes.

    Subclasses MUST set:
      - THEME_ID: class attribute (str)
      - FALLBACK_EXPRESSIONS: list[str]
      - FALLBACK_MOTION_GROUPS: list[str]

    They MAY override:
      - validate_expression / validate_motion: per-theme additional
        rules (e.g. SEED's composite expressions)
    """

    THEME_ID: str = ""  # subclasses MUST set
    FALLBACK_EXPRESSIONS: list[str] = []
    FALLBACK_MOTION_GROUPS: list[str] = []

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
                logger.info(
                    f"[{type(self).__name__}] Loaded model metadata: {self._meta}"
                )
            except Exception as e:
                logger.warning(
                    f"[{type(self).__name__}] Failed to parse model metadata: {e}"
                )

        # If no metadata, report what we would use
        if self._meta is None:
            logger.warning(
                f"[{type(self).__name__}] Model metadata not loaded. "
                f"Model dir: {self._model_dir}, model3_path: {self._model3_path}. "
                f"Triggering with raw expression/motion names (frontend will try)."
            )

        # Subclass must declare its identity — refuse to operate without it
        if not self.THEME_ID:
            raise ValueError(
                f"{type(self).__name__} must set THEME_ID class attribute"
            )
        if not self.FALLBACK_EXPRESSIONS:
            raise ValueError(
                f"{type(self).__name__} must declare FALLBACK_EXPRESSIONS"
            )
        if not self.FALLBACK_MOTION_GROUPS:
            raise ValueError(
                f"{type(self).__name__} must declare FALLBACK_MOTION_GROUPS"
            )

    def _find_model3(self, model_dir: Path) -> Path | None:
        """Find the .model3.json file in *model_dir*.

        Looks in `model_dir` directly, and one level deeper
        (`model_dir/<sub>/<sub>.model3.json` is a common layout).
        Returns the first match, or None if not found.
        """
        if not model_dir.is_dir():
            return None

        candidates = list(model_dir.glob("*.model3.json"))
        if len(candidates) == 1:
            return candidates[0]
        elif len(candidates) > 1:
            logger.warning(
                f"[{type(self).__name__}] Multiple .model3.json files in "
                f"{model_dir}, using first: {candidates[0]}"
            )
            return candidates[0]
        else:
            # No .model3.json found — check one level deeper
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
                f"[{type(self).__name__}] warmup: no model metadata at "
                f"{self._model3_path}. Using fallbacks."
            )
            return

        # Validate that the fallback expressions are present
        missing_expr = [
            e for e in self.FALLBACK_EXPRESSIONS if not self._meta.validate_expression(e)
        ]
        missing_motion = [
            g for g in self.FALLBACK_MOTION_GROUPS if not self._meta.validate_motion(g)
        ]
        if missing_expr:
            logger.warning(
                f"[{type(self).__name__}] Model '{self._meta.name}' missing "
                f"expressions: {missing_expr}. Available: {self._meta.expressions}"
            )
        if missing_motion:
            logger.warning(
                f"[{type(self).__name__}] Model '{self._meta.name}' missing "
                f"motion groups: {missing_motion}. "
                f"Available: {list(self._meta.motion_groups.keys())}"
            )

    async def trigger(
        self, expression: str, motion: str
    ) -> Live2DTrigger:
        """Validate and emit a Live2D trigger.

        The expression and motion names come from per-theme
        tables (TOOL_MOTION_MAP for tool calls, EMOTION_MAP in
        halo_responder for LLM-driven emotion). We validate
        against the loaded model metadata; if validation fails
        we still emit the raw names so the frontend can handle
        missing assets gracefully.
        """
        # Validate expression
        validated_expr = expression
        if self._meta and not self._meta.validate_expression(expression):
            logger.warning(
                f"[{type(self).__name__}] Expression '{expression}' not in "
                f"model '{self._meta.name}'. Available: {self._meta.expressions}"
            )
            validated_expr = expression  # Still emit the raw name

        # Validate motion group
        motion_group = motion.split(":")[0] if motion else ""
        validated_motion = motion
        if self._meta and motion_group and not self._meta.validate_motion(motion_group):
            logger.warning(
                f"[{type(self).__name__}] Motion group '{motion_group}' not in "
                f"model '{self._meta.name}'. "
                f"Available: {list(self._meta.motion_groups.keys())}"
            )
            validated_motion = motion  # Still emit the raw name

        logger.debug(
            f"[{type(self).__name__}] trigger: "
            f"expression={validated_expr}, motion={validated_motion}"
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
        return self.FALLBACK_EXPRESSIONS

    @property
    def motion_groups(self) -> list[str]:
        """Available motion groups (from metadata or fallbacks)."""
        if self._meta:
            return list(self._meta.motion_groups.keys())
        return self.FALLBACK_MOTION_GROUPS


__all__ = ["BaseThemeResponder"]

"""Sprint 23 (v0.1.4): tests for WhisperLocalASR's
`model_path` hard-error behavior.

Sprint 23 removes the v0.1.3 forward-compat warning
at `whisper_local.py:80-99` and replaces it with a
hard `ValueError`. If the user sets
`voice.asr.model_path` in config.toml but doesn't
flip `voice.asr.backend = "whisper_hf"`, the
warmup call must fail loudly with a pointer at
the right backend.

Pattern reference: `tests/voice/test_voice_config_asr.py`
for the `whisper_local` config-glue tests, and
`tests/voice/test_whisper_hf.py` for the
heavy-dep-mocking pattern.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_whisper_local_warmup_with_model_path_raises():
    """Sprint 23: `model_path` is a hard `ValueError`,
    not a warning. The error message must reference
    `whisper_hf` so the user knows what backend to switch to.
    """
    from app.voice.asr.whisper_local import WhisperLocalASR

    asr = WhisperLocalASR(
        model_size="base",
        model_path="/some/where",
        language="yue",
    )
    # We don't even reach the `import whisper` line —
    # the model_path check fires first.
    with pytest.raises(ValueError, match="whisper_hf"):
        # Run synchronously via asyncio.run so the
        # warmup() coroutine executes to the first raise.
        import asyncio

        asyncio.run(asr.warmup())


def test_whisper_local_warmup_with_model_path_message_includes_path():
    """The error message includes the offending model_path
    value so the user can spot their config typo at a glance.
    """
    from app.voice.asr.whisper_local import WhisperLocalASR

    asr = WhisperLocalASR(
        model_size="base",
        model_path="/Users/me/.gundam-halo/models/whisper-yue-base/",
    )
    import asyncio

    with pytest.raises(ValueError, match="whisper-yue-base"):
        asyncio.run(asr.warmup())


def test_whisper_local_warmup_without_model_path_loads_whisper():
    """Sprint 23: `model_path=""` (the default) loads
    openai-whisper as before. This is the
    backward-compat path for users who don't want to
    switch to the fine-tuned HF backend.
    """
    from app.voice.asr.whisper_local import WhisperLocalASR

    asr = WhisperLocalASR(
        model_size="base",
        model_path="",  # default — user is on openai-whisper
        language="yue",
    )
    # Mock the `whisper.load_model` call so we don't
    # actually download / load the model. The point
    # of this test is to verify the model_path check
    # is GONE when model_path is empty.
    import asyncio

    with patch.dict(
        "sys.modules",
        {"whisper": MagicMock(load_model=MagicMock())},
    ):
        asyncio.run(asr.warmup())
        # The model was loaded via `whisper.load_model`.
        import sys

        sys.modules["whisper"].load_model.assert_called_once()
        # First positional arg is the model_size string.
        call = sys.modules["whisper"].load_model.call_args
        assert call.args[0] == "base"


def test_whisper_local_default_model_path_is_empty():
    """Constructor default for `model_path` is the empty
    string (backward-compat — no breaking change for
    users who never set the field).
    """
    from app.voice.asr.whisper_local import WhisperLocalASR

    asr = WhisperLocalASR(model_size="base")
    assert asr._model_path == ""

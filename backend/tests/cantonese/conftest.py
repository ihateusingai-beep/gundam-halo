# Cantonese eval set — conftest
# Skip all tests if MiniMax API key not configured
# Per M12.1 spec — baseline run 需要 live LLM call
import os

import pytest


def _has_minimax_key() -> bool:
    key = os.environ.get("MINIMAX_API_KEY") or os.environ.get("MINIMAX_KEY")
    if not key:
        try:
            from app.config import load_config  # type: ignore

            cfg = load_config()
            return bool(cfg.get("llm", {}).get("api_key"))
        except Exception:
            return False
    return True


needs_llm = pytest.mark.skipif(
    not _has_minimax_key(),
    reason="MINIMAX_API_KEY not set — Cantonese baseline scorer needs live LLM",
)

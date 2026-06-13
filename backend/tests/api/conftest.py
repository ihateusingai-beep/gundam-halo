"""API-level fixtures: tear down M12 between tests in this directory.

The API tests in this directory use the in-process FastAPI app,
which means they share the M12 singletons. We default to
``disable_vector_index=True`` so the FAISS native module never
gets loaded — this keeps these tests from breaking sibling test
modules (e.g. voice tests that import torch, where faiss-cpu +
torch together can crash on Apple Silicon).
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _m12_disable_faiss_in_tests():
    from app.core import config as _cfg

    cfg = _cfg.get_config()
    cfg.memory.disable_vector_index = True
    yield
    cfg.memory.disable_vector_index = True


@pytest.fixture(autouse=True)
def _m12_reset_between_tests():
    try:
        from app.memory.lifecycle import reset_all_memory

        reset_all_memory()
    except Exception:
        pass
    yield
    try:
        from app.memory.lifecycle import reset_all_memory

        reset_all_memory()
    except Exception:
        pass

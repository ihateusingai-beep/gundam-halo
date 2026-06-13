"""M12 test fixtures — ensure all M12 singletons are torn down between tests.

The M12 layer has three module-level singletons
(``get_sqlite_index``, ``get_vector_index``, ``get_background_embedder``)
that hold open resources (SQLite connections, FAISS index, a daemon
worker thread). If the background thread leaks into a later test
module (e.g. voice tests that touch ``numpy``/``torch``) it can
crash the FAISS native loader with ``Fatal Python error: Aborted``.

We default to **NullVectorIndex** (no FAISS loaded) for the broad
M12 tests — they don't need the FAISS path to verify SQLite +
lifecycle wiring. The dedicated ``test_vector_index.py`` opts in
to a real FAISS index via its own per-test fixture.

We reset the singletons:

- between every test in this directory (autouse, function scope)
- at session end (defensive)
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _m12_disable_faiss_in_tests(monkeypatch):
    """Default the M12 config to ``disable_vector_index=True``.

    The dedicated ``test_vector_index.py`` overrides this by
    re-creating the vector index with a real FAISS instance.
    """
    from app.core import config as _cfg
    cfg = _cfg.get_config()
    cfg.memory.disable_vector_index = True
    yield
    cfg.memory.disable_vector_index = True


@pytest.fixture(autouse=True)
def _m12_reset_between_tests():
    """Tear down all M12 singletons before AND after each test.

    The ``before`` half matters: if a previous test in another
    module created a singleton we don't know about, this gives us
    a clean slate.
    """
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


def pytest_sessionfinish(session, exitstatus):
    """Final teardown — stop the embedder daemon thread."""
    try:
        from app.memory.lifecycle import reset_all_memory

        reset_all_memory()
    except Exception:
        pass

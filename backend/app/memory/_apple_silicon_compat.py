"""Apple Silicon + torch MPS / faiss-cpu compatibility helpers.

Background
----------

On Apple Silicon (darwin / arm64), the ``faiss-cpu`` wheel ships its
own ``libomp.dylib`` (LLVM OpenMP runtime). When ``torch`` is loaded
*after* ``faiss`` in the same process, torch also tries to initialise
its bundled libomp. The second ``omp_init`` raises::

    OMP: Error #15: Initializing libomp.dylib, but found libomp.dylib
    already initialized.
    ...
    Aborted (signal 6 / SIGABRT)

— which kills the Python process. This is a well-known interaction
with PyTorch's MPS backend; the same crash is seen with other libs
that bundle libomp (e.g. ``lightgbm``, ``xgboost``) when paired with
faiss-cpu on M-series Macs.

Historically the M12 ticket (see ``docs/tickets/M12.md`` "Known
follow-ups" #5) worked around this in tests by:

1. Marking the FAISS-specific test file with ``@pytest.mark.faiss_native``
2. Defaulting ``Config.memory.disable_vector_index = True`` in
   ``tests/memory/conftest.py`` and ``tests/api/conftest.py``
3. Setting ``addopts = "-m 'not faiss_native'"`` in ``pyproject.toml``

That kept CI green but did nothing for the **live app**: if a user
opens the Tauri desktop client on a Mac and the import order ends up
as ``faiss → torch``, the process aborts at first MPS use or first
faiss call. This module exists to give the live app a runtime guard.

The strategy
------------

We never import ``faiss`` or ``torch`` at module load time here (the
``app.memory.vector_index`` module is imported very early, well
before torch is guaranteed to be ready). We use ``sys.modules`` to
*probe* whether torch has already been imported by someone else.

The decision function is :func:`should_use_faiss`. It returns
``False`` on Apple Silicon when torch has been imported AND its MPS
backend is available — i.e. exactly the dangerous combination. It
returns ``True`` otherwise (other platforms are unaffected, or the
host has no torch at all).

Override
--------

The environment variable ``HALO_FAISS_FORCE`` overrides the auto
detection:

* ``HALO_FAISS_FORCE=1`` — always try to use faiss (caller still
  has to handle the actual ``import faiss`` failure or crash).
* ``HALO_FAISS_FORCE=0`` — always use NullVectorIndex.
* unset / ``auto`` — use the platform + torch heuristic.

The decision is memoised after the first call (process-wide
``_DECIDED`` flag) so we don't re-evaluate on every index lookup,
and we log at INFO exactly once. This is deliberate: the fallback
is a permanent behaviour change, not a transient retry.

Crash-mitigation side effect
----------------------------

When we *do* decide to use faiss on a platform where the libomp
duplication is the only known risk, we also export
:func:`prepare_for_safe_faiss_import` which sets
``KMP_DUPLICATE_LIB_OK=TRUE`` if it isn't already set. This is the
documented (Apple + Intel-OpenMP-team) escape hatch: it allows
multiple libomp copies in the process, at the cost of correctness
if both copies' threads touch shared OpenMP state simultaneously.
For our use case (faiss-cpu doing a ``normalize_L2`` while torch
runs a single matmul on MPS) the runtime never overlaps, so the
``TRUE`` flag is safe and matches what the faiss-cpu GitHub
issues recommend.

This module is intentionally tiny and dependency-free (only the
standard library) so it can be imported from anywhere in the
process — including at config-load time — without risk of pulling
faiss / torch into the import graph.
"""
from __future__ import annotations

import logging
import os
import platform
import sys
import threading

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public env var
# ---------------------------------------------------------------------------

#: Environment variable that overrides the auto-detection logic.
#: Accepted values: "1" (force faiss), "0" (force null), "auto" (default).
ENV_FORCE = "HALO_FAISS_FORCE"

#: Environment variable that's the documented (but unsafe-in-general)
#: workaround for the duplicate-libomp crash. We set this in
#: :func:`prepare_for_safe_faiss_import` when we *do* decide to use
#: faiss on Apple Silicon, because the cost of a misconfigured
#: parallel region is zero for our workload (single-threaded faiss
#: ops, MPS offload to GPU).
ENV_KMP_DUPLICATE_LIB_OK = "KMP_DUPLICATE_LIB_OK"


# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------


def is_apple_silicon() -> bool:
    """Return True if running on macOS arm64 (M1/M2/M3/M4).

    This is the *only* platform where the duplicate-libomp issue
    bites — Linux faiss-cpu wheels link against ``libgomp`` (system
    package), and Windows wheels are statically linked. macOS arm64
    wheels are the ones that bundle their own ``libomp.dylib``.
    """
    return sys.platform == "darwin" and platform.machine() == "arm64"


# ---------------------------------------------------------------------------
# torch detection — probe sys.modules only, never import torch ourselves
# ---------------------------------------------------------------------------


def is_torch_imported() -> bool:
    """Return True if ``torch`` has been imported into this process.

    We do **not** import torch here — only inspect ``sys.modules`` to
    see if someone else got there first. This keeps the import graph
    of the memory subsystem clean of heavy ML deps.
    """
    return "torch" in sys.modules


def is_torch_mps_loaded() -> bool:
    """Return True if torch has been imported *and* MPS is built/available.

    Returns False if torch is not imported at all, or if MPS is not
    available (e.g. running on Intel Mac, or a torch build without
    MPS). Both ``is_built()`` and ``is_available()`` are probed so
    we don't trigger a runtime check on hosts where MPS was never
    compiled in.
    """
    if not is_torch_imported():
        return False
    try:
        torch = sys.modules["torch"]
        mps = getattr(torch.backends, "mps", None)
        if mps is None:
            return False
        # is_built() may not exist on very old torch; guard.
        is_built = getattr(mps, "is_built", None)
        if callable(is_built) and not is_built():
            return False
        is_available = getattr(mps, "is_available", None)
        if callable(is_available):
            return bool(is_available())
        # Fall back to "torch imported, mps attr exists"
        return True
    except Exception as e:  # noqa: BLE001
        # Any failure in probing — conservative: assume MPS may be
        # loaded. Better to skip faiss than to crash.
        logger.debug("is_torch_mps_loaded probe failed: %s", e)
        return True


# ---------------------------------------------------------------------------
# Crash-mitigation side effect
# ---------------------------------------------------------------------------


def prepare_for_safe_faiss_import() -> None:
    """Set ``KMP_DUPLICATE_LIB_OK=TRUE`` if not already set.

    Idempotent. Called by the vector index factory right before it
    does ``import faiss`` on Apple Silicon, as a belt-and-braces
    guard for the case where our heuristic decided to go ahead with
    faiss (e.g. user set ``HALO_FAISS_FORCE=1``).

    The flag is process-global and is harmless on hosts where
    libomp is not duplicated, so we set it unconditionally on the
    risky platforms.
    """
    if os.environ.get(ENV_KMP_DUPLICATE_LIB_OK):
        return
    os.environ[ENV_KMP_DUPLICATE_LIB_OK] = "TRUE"
    logger.debug(
        "Set %s=TRUE to suppress duplicate-libomp abort "
        "(see faiss-cpu + torch MPS interaction on Apple Silicon)",
        ENV_KMP_DUPLICATE_LIB_OK,
    )


# ---------------------------------------------------------------------------
# Decision (memoised)
# ---------------------------------------------------------------------------

_DECIDED: bool | None = None
_REASON: str | None = None
_DECISION_LOCK = threading.Lock()


def _decide_once() -> tuple[bool, str]:
    """Evaluate the use-faiss predicate once per process.

    Returns ``(should_use, reason)`` where ``reason`` is a short
    human-readable string suitable for a log line. Cached after the
    first call.
    """
    global _DECIDED, _REASON
    with _DECISION_LOCK:
        if _DECIDED is not None:
            assert _REASON is not None
            return _DECIDED, _REASON

        # 1. Explicit override wins.
        forced = os.environ.get(ENV_FORCE, "").strip().lower()
        if forced in ("1", "true", "yes", "on", "force", "faiss"):
            _DECIDED = True
            _REASON = f"{ENV_FORCE}={os.environ[ENV_FORCE]} forces faiss"
            return _DECIDED, _REASON
        if forced in ("0", "false", "no", "off", "null", "disable"):
            _DECIDED = False
            _REASON = (
                f"{ENV_FORCE}={os.environ[ENV_FORCE]} forces NullVectorIndex"
            )
            return _DECIDED, _REASON

        # 2. Non-Apple-Silicon hosts: no known issue, use faiss if
        #    installed.
        if not is_apple_silicon():
            _DECIDED = True
            _REASON = "non-Apple-Silicon host — no libomp risk"
            return _DECIDED, _REASON

        # 3. Apple Silicon: the dangerous combination is
        #    faiss-loaded + torch-imported-with-MPS-ready. If torch
        #    is not yet imported we can still safely import faiss
        #    first (and the user gets a real FAISS index). If torch
        #    is already imported and MPS is up, fall back.
        if is_torch_mps_loaded():
            _DECIDED = False
            _REASON = (
                "Apple Silicon + torch MPS already loaded — "
                "importing faiss-cpu would duplicate libomp and abort. "
                f"Override with {ENV_FORCE}=1 to force faiss."
            )
            return _DECIDED, _REASON

        # Apple Silicon but torch not loaded (or no MPS): safe to
        # import faiss.
        _DECIDED = True
        if is_torch_imported():
            _REASON = (
                "Apple Silicon, torch imported but MPS not available — "
                "safe to use faiss"
            )
        else:
            _REASON = "Apple Silicon, torch not yet imported — safe to use faiss"
        return _DECIDED, _REASON


def should_use_faiss() -> bool:
    """Return True if it's safe to import + use faiss in this process.

    Memoised. Safe to call from any thread.
    """
    return _decide_once()[0]


def get_fallback_reason() -> str:
    """Return the human-readable reason for the last decision.

    Useful for logging once at startup, e.g.:

        if not should_use_faiss():
            logger.info("FAISS disabled: %s", get_fallback_reason())
    """
    return _decide_once()[1]


def log_decision_once() -> None:
    """Emit a single INFO log line summarising the FAISS decision.

    Callers should invoke this at startup. We log even when faiss
    *is* going to be used, but at DEBUG level — the warning
    happens only on fallback. We guard with a module flag so it's
    truly once per process.
    """
    if getattr(log_decision_once, "_logged", False):
        return
    use, reason = _decide_once()
    if use:
        logger.debug("FAISS index path active (%s)", reason)
    else:
        logger.info(
            "FAISS index disabled — using NullVectorIndex (lexical "
            "search still works). Reason: %s",
            reason,
        )
    log_decision_once._logged = True  # type: ignore[attr-defined]


def reset_for_testing() -> None:
    """Clear the memoised decision. Test-only."""
    global _DECIDED, _REASON
    with _DECISION_LOCK:
        _DECIDED = None
        _REASON = None
    if hasattr(log_decision_once, "_logged"):
        delattr(log_decision_once, "_logged")


__all__ = [
    "ENV_FORCE",
    "ENV_KMP_DUPLICATE_LIB_OK",
    "get_fallback_reason",
    "is_apple_silicon",
    "is_torch_imported",
    "is_torch_mps_loaded",
    "log_decision_once",
    "prepare_for_safe_faiss_import",
    "reset_for_testing",
    "should_use_faiss",
]

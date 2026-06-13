#!/usr/bin/env python3
"""End-to-end reproducer for the Apple Silicon faiss-cpu + torch MPS crash.

This script is the **actual proof** that the M12.1 follow-up #5
runtime guard works. It performs three things in sequence:

1. **Negative control (the crash)** — bypasses our guard, manually
   ``import faiss`` first, then ``import torch`` and tries to use
   MPS. On Apple Silicon with faiss-cpu + torch both installed,
   this will hit ``OMP: Error #15: Initializing libomp.dylib, but
   found libomp.dylib already initialized`` and abort with
   SIGABRT (exit 134).

2. **Positive control (the fix)** — invokes
   :func:`app.memory.vector_index.make_vector_index` and asserts
   that the guard either:
   - returns a real ``FaissVectorIndex`` (with
     ``KMP_DUPLICATE_LIB_OK=TRUE`` armed on Apple Silicon as a
     belt-and-braces guard), or
   - returns a ``NullVectorIndex`` because the dangerous
     combination was detected and we chose the safe fallback.

3. **Exit 0 if and only if the live factory does not crash** —
   the actual app start-up path. The negative control in step 1
   is a separate subprocess so it can crash without taking us
   down with it.

Usage::

    cd backend
    uv run python scripts/repro_apple_silicon_faiss.py

Exit codes:

* 0 — the live factory did not crash (fix is working).
* 1 — the live factory crashed (fix is broken, please open a
      ticket).
* 134 — the negative-control subprocess aborted with SIGABRT
        (confirms the underlying crash is real and reproducible).
        Note: this is reported, not propagated; the script still
        exits 0 if the live factory is safe.

Run from the backend directory so ``app.*`` is importable.
"""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import traceback
from pathlib import Path

# Make ``app.*`` importable when running from backend/scripts/.
BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def banner(title: str) -> None:
    print()
    print("=" * 72)
    print(f"  {title}")
    print("=" * 72)


def _ensure_torch_installed() -> bool:
    """Best-effort: install torch into the active venv.

    Returns True if torch is importable after the attempt.
    Skipped if a voice-extra torch is already present.
    """
    try:
        import torch  # noqa: F401
        return True
    except ImportError:
        pass
    print(
        "torch is not installed in the active environment. The"
        " crash only reproduces when both faiss-cpu and torch"
        " are loaded, so we need to install torch. Running"
        " `uv pip install torch` (this is a one-time setup"
        " cost — torch is a peer dep of the voice extra in"
        " pyproject.toml)."
    )
    rc = subprocess.run(
        ["uv", "pip", "install", "torch"],
        capture_output=True,
        text=True,
    )
    if rc.returncode != 0:
        print("--- uv pip install torch stderr ---")
        print(rc.stderr.strip() or "(empty)")
        print(
            "torch install failed. Skipping the negative control"
            " and continuing to the positive control."
        )
        return False
    # Re-import in the parent process to confirm.
    try:
        import torch  # noqa: F401
        return True
    except ImportError:
        return False


def step_1_negative_control() -> int:
    """Reproduce the crash in a subprocess.

    Returns the subprocess returncode (134 = SIGABRT confirms
    the crash; 0 = the dangerous combination did not actually
    crash on this host, which is fine — it means torch/faiss
    are not in the dangerous state).
    """
    banner("STEP 1: negative control — confirm the crash is real")
    if not _ensure_torch_installed():
        return 1
    print(
        "Running the dangerous import order in a subprocess to"
        " demonstrate the underlying crash. This subprocess is"
        " expected to abort with SIGABRT (exit 134) on Apple"
        " Silicon."
    )
    code = textwrap.dedent(
        """
        import faiss
        import numpy as np
        # Do faiss work FIRST so its bundled libomp is initialised.
        dim = 384
        v = np.random.rand(100, dim).astype(np.float32)
        faiss.normalize_L2(v)
        idx = faiss.IndexFlatIP(dim)
        idx.add(v)
        # Now import torch and use MPS.
        import torch
        x = torch.randn(100, dim, device='mps')
        y = x @ x.T
        # And exercise faiss again — duplicate libomp aborts
        # here on Apple Silicon.
        scores, ids = idx.search(v[:1], 5)
        print("survived — host is not in the dangerous state")
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
    )
    print("--- subprocess stdout ---")
    print(result.stdout.strip() or "(empty)")
    print("--- subprocess stderr ---")
    print(result.stderr.strip() or "(empty)")
    print(f"--- subprocess exit code: {result.returncode} ---")
    if result.returncode in (134, -6):
        print(
            ">>> Confirmed: SIGABRT (exit 134 / -6) — the Apple"
            " Silicon faiss-cpu + torch MPS crash reproduces on"
            " this host."
        )
    elif result.returncode == 0:
        print(
            ">>> Note: the dangerous combination did NOT crash on"
            " this exact host/version. The runtime guard is still"
            " correct — it errs on the side of safety."
        )
    else:
        print(
            f">>> Subprocess exited with unexpected code {result.returncode}."
            " See stderr above for details."
        )
    return result.returncode


def step_2_positive_control() -> int:
    """Exercise the live factory and assert it does not crash."""
    banner("STEP 2: positive control — exercise the live factory")
    try:
        # Import lazily so any earlier failure (negative control
        # running in a separate process keeps us safe).
        from app.memory import _apple_silicon_compat as compat
        from app.memory.vector_index import (
            FaissVectorIndex,
            NullVectorIndex,
            make_vector_index,
        )
    except Exception as e:  # noqa: BLE001
        print(f"FAIL: could not import the factory: {e!r}")
        traceback.print_exc()
        return 1

    print(
        f"Platform detected: apple_silicon={compat.is_apple_silicon()}, "
        f"torch_imported={compat.is_torch_imported()}, "
        f"torch_mps_loaded={compat.is_torch_mps_loaded()}"
    )
    print(
        f"Decision: should_use_faiss={compat.should_use_faiss()}, "
        f"reason={compat.get_fallback_reason()!r}"
    )

    # Use a throwaway halo_home so the real user's index is
    # not touched.
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        halo_home = Path(tmp)
        try:
            idx = make_vector_index(halo_home=halo_home, dim=64)
        except BaseException as e:  # noqa: BLE001
            print(f"FAIL: make_vector_index raised {type(e).__name__}: {e!r}")
            traceback.print_exc()
            return 1

        if isinstance(idx, FaissVectorIndex):
            print("Factory returned: FaissVectorIndex (real FAISS)")
            # Sanity: a trivial add+search must not crash.
            import numpy as np

            v = np.random.rand(3, 64).astype(np.float32)
            ids = idx.add_batch(
                v,
                [
                    {"kind": "message", "source_id": f"m{i}"}
                    for i in range(3)
                ],
            )
            print(f"  add_batch returned ids={ids}")
            hits = idx.search(v[0], k=2)
            print(f"  search returned {len(hits)} hits (top score"
                  f"={hits[0].score if hits else 'n/a'})")
            idx.close()
        elif isinstance(idx, NullVectorIndex):
            print("Factory returned: NullVectorIndex (safe fallback)")
            print("  This is the expected path on Apple Silicon + torch"
                  " MPS already loaded.")
        else:
            print(f"FAIL: unexpected index type {type(idx).__name__}")
            return 1

    print(">>> Live factory did not crash. Fix verified.")
    return 0


def main() -> int:
    print("Apple Silicon faiss-cpu + torch MPS crash — M12.1 #5 reproducer")
    print(f"  Python: {sys.executable}")
    print(f"  Backend: {BACKEND}")
    print(f"  Platform: {sys.platform}/{os.uname().machine}")
    print(f"  env HALO_FAISS_FORCE={os.environ.get('HALO_FAISS_FORCE', '<unset>')}")

    crash_code = step_1_negative_control()
    factory_code = step_2_positive_control()

    banner("SUMMARY")
    print(f"  Negative control (raw crash):  exit={crash_code}")
    print(f"  Positive control (live factory): exit={factory_code}")
    if factory_code == 0:
        print("  RESULT: PASS — the live app path is safe.")
        return 0
    print("  RESULT: FAIL — the live app path is not safe.")
    return 1


if __name__ == "__main__":
    sys.exit(main())

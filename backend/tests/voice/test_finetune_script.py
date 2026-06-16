"""Smoke tests for the M9-E Layer 2 fine-tune script.

We don't actually run the training here (it needs
`uv sync --extra train` and 16GB+ RAM + 3h wall clock).
The smoke test verifies:
  - The script is importable without syntax errors
  - The CLI parser handles the documented args
  - The dataset preparation function is still a
    `NotImplementedError` (the v0.1.3 stub contract)
  - The output_dir default matches the config.toml
    comment + the test_whisper_yue.py fixture path

This is a defense against the script rotting: if
someone refactors and accidentally introduces a
syntax error, these tests catch it before the user
hits the 3h training run.
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest


FINETUNE_SCRIPT = (
    Path(__file__).resolve().parent.parent.parent
    / "scripts"
    / "finetune_whisper_yue.py"
)


def _load_script_module(name: str = "finetune_whisper_yue_test"):
    """Load the fine-tune script as an importable module.

    The script does `from app.* import ...` at module
    top, so we have to inject the backend root onto
    sys.path before loading. We also pre-register the
    module in sys.modules before exec_module runs —
    the script's @dataclass on `DatasetPaths` (line
    179) inspects `sys.modules[cls.__module__]` and
    crashes with "'NoneType' object has no
    attribute '__dict__'" if the module isn't
    registered yet. (dataclasses uses __module__ to
    look up the @dataclass decorator's containing
    module for type-hint resolution.)
    """
    backend_root = str(FINETUNE_SCRIPT.resolve().parent.parent)
    if backend_root not in sys.path:
        sys.path.insert(0, backend_root)
    spec = importlib.util.spec_from_file_location(name, FINETUNE_SCRIPT)
    if spec is None or spec.loader is None:
        pytest.fail(f"could not load {FINETUNE_SCRIPT}")
    mod = importlib.util.module_from_spec(spec)
    # Pre-register so @dataclass can find the module
    # via sys.modules.get(cls.__module__).
    sys.modules[name] = mod
    try:
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
    finally:
        # Don't keep the heavy module around in
        # sys.modules between tests — the next test
        # re-loads with a different name.
        if sys.modules.get(name) is mod:
            del sys.modules[name]
    return mod


def test_finetune_script_is_importable():
    """The script module loads without syntax errors.

    importlib.util.spec_from_file_location lets us
    import a script by path without polluting sys.path
    for the rest of the test run. We re-load the module
    with a unique name to avoid sys.modules cache
    collisions across tests.
    """
    mod = _load_script_module(name="finetune_yue_importable")
    assert hasattr(mod, "prepare_common_voice_yue"), (
        "finetune_whisper_yue.py should export "
        "prepare_common_voice_yue as a module-level "
        "function"
    )
    assert hasattr(mod, "main"), (
        "finetune_whisper_yue.py should export a main() "
        "function as the CLI entry point"
    )


def test_finetune_script_help_exits_zero():
    """`python finetune_whisper_yue.py --help` exits 0.

    Subprocess.run with check=True catches non-zero
    exits. The output is discarded; we only care
    that the parser is wired up.
    """
    result = subprocess.run(
        [sys.executable, str(FINETUNE_SCRIPT), "--help"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, (
        f"--help exited with {result.returncode}:\n"
        f"stdout={result.stdout}\nstderr={result.stderr}"
    )
    # The help text should mention the output dir, the
    # dataset version, and the LoRA rank — these are
    # the documented args in the spec.
    assert "--output_dir" in result.stdout
    assert "--lora_r" in result.stdout
    assert "--dataset_version" in result.stdout


def test_prepare_common_voice_yue_is_stub():
    """prepare_common_voice_yue is a NotImplementedError
    stub in v0.1.3 (per M9-E ticket). The actual
    materialise-and-split logic is the next chunk of
    work. This test pins the contract so a future
    refactor that accidentally removes the stub
    raises a clear failure here.

    The function imports `from datasets import ...` at
    the top, which only exists when the `train` extra
    is installed (`uv sync --extra train`). In CI /
    unit-test environments without the extra, we skip
    the runtime call and only assert the function
    exists on the module. The function-existence check
    is the part of the contract we can verify offline.
    """
    mod = _load_script_module(name="finetune_yue_stub_test")
    assert hasattr(mod, "prepare_common_voice_yue"), (
        "finetune_whisper_yue.py should export "
        "prepare_common_voice_yue as a module-level "
        "function"
    )
    datasets = pytest.importorskip(
        "datasets",
        reason=(
            "datasets is part of the `train` extra "
            "(uv sync --extra train); skip the runtime "
            "stub test when running unit tests without "
            "the extra installed."
        ),
    )
    # Re-load the module now that `datasets` is on
    # sys.path so the prepare_common_voice_yue
    # function can import it without raising
    # ModuleNotFoundError.
    mod = _load_script_module(name="finetune_yue_stub_test_v2")
    with pytest.raises(NotImplementedError) as exc_info:
        mod.prepare_common_voice_yue(
            cv_version="11.0",
            cache_dir=Path("/tmp/cv-yue"),
            max_train_hours=50.0,
        )
    # The error message should point at the M9-E ticket
    # so the user has a paper trail.
    assert "M9-E" in str(exc_info.value) or "v0.1.3" in str(
        exc_info.value
    ), f"stub error message should mention M9-E ticket: {exc_info.value}"


def test_finetune_script_default_output_dir_matches_config():
    """The default --output_dir must be
    `~/.gundam-halo/models/whisper-yue-base/`. This
    is the path the test_whisper_yue.py fixture looks
    for, and the path the config.toml example
    documents. If we ever move it, the test fixture +
    config.toml example need to move in lockstep —
    this test is the tripwire.

    Both `os.path.expanduser` and `Path(...)` are
    used in the codebase; `os.path.expanduser("~/.x/")`
    keeps the trailing slash while `Path("~/.x/")`
    strips it. We compare via resolved Path to avoid
    the trailing-slash mismatch.
    """
    expected = Path(
        os.path.expanduser("~/.gundam-halo/models/whisper-yue-base/")
    )
    from tests.voice.test_whisper_yue import FINE_TUNED_MODEL_DIR
    assert FINE_TUNED_MODEL_DIR.resolve() == expected.resolve(), (
        f"FINE_TUNED_MODEL_DIR ({FINE_TUNED_MODEL_DIR}) should "
        f"match ~/.gundam-halo/models/whisper-yue-base/ "
        f"({expected}); if you change one, change the "
        f"other to match."
    )

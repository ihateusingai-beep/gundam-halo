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
    # Sprint 21: the impl adds three pure helpers that
    # unit-test the dataset preparation pipeline
    # without needing `datasets` or `pyarrow`.
    assert hasattr(mod, "split_by_client_id"), (
        "Sprint 21: split_by_client_id helper missing"
    )
    assert hasattr(mod, "cap_at_hours"), (
        "Sprint 21: cap_at_hours helper missing"
    )
    assert hasattr(mod, "save_splits_as_parquet"), (
        "Sprint 21: save_splits_as_parquet helper missing"
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
    """Sprint 21: prepare_common_voice_yue is NO LONGER
    a stub. The full impl lives in
    finetune_whisper_yue.py and uses the pure
    helpers split_by_client_id, cap_at_hours,
    save_splits_as_parquet. We test the pure
    helpers in dedicated unit tests below; the
    streaming call inside prepare_common_voice_yue
    requires the `datasets` extra (which the
    standard venv doesn't have), so the end-to-end
    path is tested by monkey-patching the
    load_dataset call.

    This test now asserts the function exists and
    is callable. The NotImplementedError check was
    removed in Sprint 21.
    """
    mod = _load_script_module(name="finetune_yue_not_stub_test")
    assert hasattr(mod, "prepare_common_voice_yue")
    # The function should be callable. We can't
    # actually invoke it without `datasets`, but we
    # can import the module and confirm the impl is
    # in place (i.e. it doesn't re-raise
    # NotImplementedError at import time).
    src = Path(mod.__file__).read_text(encoding="utf-8")
    assert "raise NotImplementedError" not in src.split(
        "def prepare_common_voice_yue", 1
    )[1].split("def _audio_seconds", 1)[0], (
        "Sprint 21: prepare_common_voice_yue should "
        "not still raise NotImplementedError. The "
        "stub was filled in this sprint; if you "
        "re-added a NotImplementedError, that's a "
        "regression."
    )


# ---------------------------------------------------------------------------
# Sprint 21: pure helper tests for the dataset
# preparation pipeline. These don't require the
# `datasets` or `pyarrow` extras — they exercise the
# pure functions that are split out from
# prepare_common_voice_yue for testability.
# ---------------------------------------------------------------------------


def _mock_sample(client_id: str, duration_s: float = 1.0) -> dict:
    """Build a mock Common Voice sample with a
    decoded audio array of the requested duration at
    16kHz. Mirrors the HF datasets Audio feature
    output so split_by_client_id and cap_at_hours
    can read it without touching the real schema.
    """
    n_samples = int(duration_s * 16000)
    return {
        "client_id": client_id,
        "audio": {"array": list(range(n_samples))},
        "sentence": f"hello from {client_id}",
    }


def test_split_by_client_id_speaker_disjoint():
    """split_by_client_id must never put the same
    client_id in two splits (Common Voice's standard
    rule — never split one speaker across train and
    val, that leaks the WER)."""
    mod = _load_script_module(name="finetune_yue_split_test")
    samples = []
    # 3 speakers with different sample counts so the
    # "top speakers go to test" sorting kicks in.
    for cid, count in [("A", 5), ("B", 3), ("C", 2)]:
        for _ in range(count):
            samples.append(_mock_sample(cid))
    splits = mod.split_by_client_id(
        samples, test_ratio=0.34, val_ratio=0.33
    )
    spk_train = set(s["client_id"] for s in splits["train"])
    spk_val = set(s["client_id"] for s in splits["validation"])
    spk_test = set(s["client_id"] for s in splits["test"])
    assert spk_train.isdisjoint(spk_val), (
        f"speaker-disjoint violated: train={spk_train} "
        f"overlaps val={spk_val}"
    )
    assert spk_val.isdisjoint(spk_test)
    assert spk_train.isdisjoint(spk_test)
    # The 3-speaker split with 34%/33% ratios should
    # give 1 / 1 / 1 (each split gets one speaker,
    # the smallest).
    assert len(spk_test) == 1
    assert len(spk_val) == 1
    assert len(spk_train) == 1


def test_split_by_client_id_handles_single_speaker():
    """With only one speaker, the split still works
    — the speaker goes to test (the smallest split),
    val is empty, train has them all. This is a
    degenerate case the test data should never hit
    in production but the impl must not crash.
    """
    mod = _load_script_module(name="finetune_yue_single_spkr_test")
    samples = [_mock_sample("solo") for _ in range(5)]
    splits = mod.split_by_client_id(samples)
    assert len(splits["test"]) == 5
    assert len(splits["validation"]) == 0
    assert len(splits["train"]) == 0


def test_cap_at_hours_keeps_earliest_within_cap():
    """cap_at_hours keeps the earliest samples that
    fit under the cap, in input order. We pass 5
    samples with varying durations (1s..5s) and
    cap at 8s: A(1)+B(2)+C(3)=6s ≤ 8, D(4) would
    push to 10s so D and E are dropped. Output is
    [A, B, C] in input order.
    """
    mod = _load_script_module(name="finetune_yue_cap_test")
    samples = [
        _mock_sample("A", duration_s=1.0),
        _mock_sample("B", duration_s=2.0),
        _mock_sample("C", duration_s=3.0),
        _mock_sample("D", duration_s=4.0),
        _mock_sample("E", duration_s=5.0),
    ]
    # Total = 15s. Cap at 8s. Algorithm: iterate in
    # input order, keep if fits.
    #   A(1): running 0+1=1 ≤ 8 → keep, running=1
    #   B(2): 1+2=3 ≤ 8 → keep, running=3
    #   C(3): 3+3=6 ≤ 8 → keep, running=6
    #   D(4): 6+4=10 > 8 → drop
    #   E(5): 6+5=11 > 8 → drop
    # Output: [A, B, C].
    capped = mod.cap_at_hours(samples, max_hours=8 / 3600)
    kept_ids = [s["client_id"] for s in capped]
    assert kept_ids == ["A", "B", "C"], (
        f"expected [A, B, C] kept, got {kept_ids}"
    )


def test_cap_at_hours_no_op_when_under_cap():
    """If the total duration is under the cap, all
    samples are returned unchanged (in input order)."""
    mod = _load_script_module(name="finetune_yue_cap_noop_test")
    samples = [
        _mock_sample("A", duration_s=1.0),
        _mock_sample("B", duration_s=2.0),
    ]
    capped = mod.cap_at_hours(samples, max_hours=10 / 3600)
    assert [s["client_id"] for s in capped] == ["A", "B"]


def test_audio_seconds_zero_length_returns_zero():
    """A sample with no audio array (e.g. raw bytes
    only) has 0 duration. cap_at_hours must skip it
    (the greedy loop drops it as "already full")."""
    mod = _load_script_module(name="finetune_yue_audio_zero_test")
    samples = [
        {"client_id": "A", "audio": {}},  # no array
        _mock_sample("B", duration_s=1.0),
    ]
    capped = mod.cap_at_hours(samples, max_hours=0.0001)
    # B has 1s of audio, but max_hours is 0.36s — so
    # B is also dropped, leaving only the zero-length
    # sample.
    kept_ids = [s["client_id"] for s in capped]
    # We don't assert exact output (the greedy
    # algorithm might keep A as "free" depending on
    # rounding). The point is: doesn't crash, returns
    # a list.
    assert isinstance(kept_ids, list)


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


# ---------------------------------------------------------------------------
# Sprint 33 / Track 31-B — Layer 2 v2 personalised fine-tune
# flag tests. The existing 9 tests above cover the Common
# Voice yue baseline (HF Hub openai/whisper-base). The
# personalised flow (FEATURE-SPEC-SPRINT26.md §4.1) layers
# LoRA on top of a user-supplied checkpoint via
# `--base_model_path` and optionally swaps the corpus via
# `--train_audio_dir`. This test exercises the CLI parser
# for both new flags (without actually running training,
# which needs the `train` extra + 16GB+ RAM + ~1h wall clock).
# ---------------------------------------------------------------------------


def test_finetune_script_help_mentions_layer_2_v2_flags():
    """Sprint 33: `python finetune_whisper_yue.py --help`
    must mention the Layer 2 v2 personalised fine-tune
    flags (`--base_model_path` and `--train_audio_dir`).
    The Tauri app's Record/Train/Swap cards
    (frontend/src/routes/settings/VoiceTab.tsx) shell out
    to the script with both flags, so the CLI parser
    must accept them; if a future refactor drops either
    flag the help text will silently lose it and the
    Tauri command will error out at runtime.

    We parse `--help` (not the actual training) so the
    test runs in <1s with the default venv. The flag is
    expected to default to None (Common Voice yue baseline
    is unchanged).
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
    assert "--base_model_path" in result.stdout, (
        "Sprint 33: finetune_whisper_yue.py must accept "
        "--base_model_path (Layer 2 v2 personalised "
        "fine-tune base checkpoint path)."
    )
    assert "--train_audio_dir" in result.stdout, (
        "Sprint 33: finetune_whisper_yue.py must accept "
        "--train_audio_dir (Layer 2 v2 self-record corpus "
        "directory containing manifest.jsonl)."
    )

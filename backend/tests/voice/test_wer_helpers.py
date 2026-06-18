"""Sprint 32 (Track 31-A): WER helper + threshold-config unit tests.

Companion to `backend/tests/voice/test_held_out_eval.py`:
the held-out test file's spec contract is **3 tests, all
skip when no held-out WAV is present** (per plan.yaml
§"test changes" + Sprint 26 §4.3 acceptance criterion 3).

The WER math + threshold config resolution have their own
unit tests living here, **independent of any user recording**.
These run unconditionally in CI (no recording needed) and
serve as regression guards for:

1. The built-in `word_error_rate` Levenshtein DP — exact
   match, single substitution / insertion / deletion,
   empty / all-wrong / Cantonese Unicode cases.
2. The `~/.gundam-halo/test-config.toml` threshold
   resolution — default (0.15), custom override,
   out-of-range fallback, wrong-type fallback, missing-file
   fallback.

Why a separate file (not a 4th test in
`test_held_out_eval.py`)? The spec's contract on the
held-out test file is "3-4 tests, all skip when no WAV".
Adding WER unit tests there would inflate the count
without satisfying the skip behaviour — they're
**always-run unit tests** for the WER + config
helpers, not **gated integration tests** for the
held-out fixture.

The `word_error_rate` function is the DP-based
Levenshtein edit distance between reference and
hypothesis word sequences, divided by the number of
words in the reference. Standard WER = (S + D + I) / N.
Used by `test_held_out_eval_wer_below_threshold`.

`jiwer` is in `pyproject.toml [train]` extra only — the
default venv lacks it. We could `uv sync --extra train`
in CI, but that pulls in `transformers` + `torch`
(~850MB) which the held-out test doesn't need. The
local DP is identical math, ~25 lines, and zero deps.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_WER_THRESHOLD = 0.15
TEST_CONFIG_FILENAME = "test-config.toml"


# ---------------------------------------------------------------------------
# Helpers (shared with test_held_out_eval.py)
# ---------------------------------------------------------------------------


def _halo_home() -> Path:
    """Resolve the halo home dir (honours HALO_HOME override)."""
    halo_home_env = os.environ.get("HALO_HOME")
    if halo_home_env:
        return Path(halo_home_env).expanduser().resolve()
    return Path.home().resolve() / ".gundam-halo"


def _load_wer_threshold() -> float:
    """Read WER threshold from `~/.gundam-halo/test-config.toml`.

    Looks for `[held_out_eval].wer_threshold` (float in [0, 1]).
    Falls back to `DEFAULT_WER_THRESHOLD` (15%) on any error.

    Mirrors the helper in `test_held_out_eval.py` — kept
    here so the WER + threshold tests can exercise it
    without pulling in the full held-out test scaffolding
    (WAV, transcript, transcribe mocks).
    """
    config_path = _halo_home() / TEST_CONFIG_FILENAME
    if not config_path.is_file():
        return DEFAULT_WER_THRESHOLD
    try:
        try:
            import tomlkit  # type: ignore

            data = tomlkit.loads(config_path.read_text(encoding="utf-8"))
        except ImportError:
            try:
                import tomllib  # type: ignore

                data = tomllib.loads(config_path.read_text(encoding="utf-8"))
            except ImportError:
                try:
                    import tomli as tomllib  # type: ignore

                    data = tomllib.loads(
                        config_path.read_text(encoding="utf-8")
                    )
                except ImportError:
                    return DEFAULT_WER_THRESHOLD
        section = data.get("held_out_eval", {})
        threshold = section.get("wer_threshold", DEFAULT_WER_THRESHOLD)
        if not isinstance(threshold, (int, float)):
            return DEFAULT_WER_THRESHOLD
        if not 0.0 <= threshold <= 1.0:
            return DEFAULT_WER_THRESHOLD
        return float(threshold)
    except Exception:
        return DEFAULT_WER_THRESHOLD


def word_error_rate(reference: str, hypothesis: str) -> float:
    """Standard word-level WER = (S + D + I) / N.

    Computed as the DP edit distance between reference
    and hypothesis word sequences, divided by the number
    of words in the reference.

    Edge cases:
    - Empty reference, empty hypothesis → 0.0
    - Empty reference, non-empty hypothesis → 1.0
      (infinite WER; clamped to 1.0 for sanity)
    - Empty hypothesis, non-empty reference → 1.0
      (every reference word was deleted)
    """
    ref_words = reference.split()
    hyp_words = hypothesis.split()
    n = len(ref_words)
    if n == 0:
        return 0.0 if not hyp_words else 1.0
    # Levenshtein DP — standard WER formula.
    # dp[i][j] = edit distance between ref_words[:i] and hyp_words[:j]
    rows = n + 1
    cols = len(hyp_words) + 1
    dp: list[list[int]] = [[0] * cols for _ in range(rows)]
    for i in range(rows):
        dp[i][0] = i
    for j in range(cols):
        dp[0][j] = j
    for i in range(1, rows):
        for j in range(1, cols):
            cost = 0 if ref_words[i - 1] == hyp_words[j - 1] else 1
            dp[i][j] = min(
                dp[i - 1][j] + 1,        # deletion
                dp[i][j - 1] + 1,        # insertion
                dp[i - 1][j - 1] + cost, # substitution / match
            )
    return dp[n][len(hyp_words)] / n


# ---------------------------------------------------------------------------
# 1. word_error_rate — Levenshtein DP unit tests
# ---------------------------------------------------------------------------


def test_word_error_rate_perfect_match():
    """Exact match → WER = 0.0."""
    assert word_error_rate("你好世界 早晨", "你好世界 早晨") == 0.0
    assert word_error_rate("a b c", "a b c") == 0.0


def test_word_error_rate_one_substitution():
    """One substitution in 4 words → WER = 0.25."""
    assert word_error_rate("a b c d", "a b X d") == 0.25


def test_word_error_rate_one_insertion():
    """One insertion in 3 words → WER = 1/3."""
    assert abs(word_error_rate("a b c", "a b c d") - 1 / 3) < 1e-9


def test_word_error_rate_one_deletion():
    """One deletion in 4 words → WER = 0.25."""
    assert word_error_rate("a b c d", "a b d") == 0.25


def test_word_error_rate_empty_reference():
    """Empty reference, empty hypothesis → WER = 0.0."""
    assert word_error_rate("", "") == 0.0


def test_word_error_rate_empty_reference_with_hypothesis():
    """Empty reference, non-empty hypothesis → WER = 1.0 (clamped)."""
    assert word_error_rate("", "a b c") == 1.0


def test_word_error_rate_completely_wrong():
    """All words wrong (substitutions only, same length) → WER = 1.0."""
    assert word_error_rate("a b c", "x y z") == 1.0


def test_word_error_rate_unicode_cantonese():
    """Cantonese characters work the same as ASCII — split() on whitespace.

    Reference: `你食咗飯未 我食咗` (2 whitespace-separated tokens).
    Hypothesis: `你食咗飯未 我未食` (2 tokens, second token differs).
    The DP finds one substitution (token 2) → WER = 1/2 = 0.5.
    """
    ref = "你食咗飯未 我食咗"
    hyp = "你食咗飯未 我未食"
    assert abs(word_error_rate(ref, hyp) - 0.5) < 1e-9


# ---------------------------------------------------------------------------
# 2. _load_wer_threshold — test-config.toml resolution
# ---------------------------------------------------------------------------


def test_wer_threshold_default_when_config_missing():
    """When `~/.gundam-halo/test-config.toml` is missing,
    the WER threshold defaults to 0.15 (per spec §4.3)."""
    with patch.object(
        sys.modules[__name__],
        "_halo_home",
        lambda: Path("/tmp/__wer_test_no_such_path__"),
    ):
        assert _load_wer_threshold() == DEFAULT_WER_THRESHOLD == 0.15


def test_wer_threshold_resolves_user_override(tmp_path, monkeypatch):
    """A user-supplied threshold in `test-config.toml`
    overrides the default 0.15."""
    monkeypatch.setenv("HALO_HOME", str(tmp_path))
    (tmp_path / "test-config.toml").write_text(
        '[held_out_eval]\nwer_threshold = 0.10\n',
        encoding="utf-8",
    )
    assert _load_wer_threshold() == 0.10


def test_wer_threshold_out_of_range_falls_back(tmp_path, monkeypatch):
    """An out-of-range threshold (e.g. 1.5) silently falls
    back to the default — better than failing the test on
    a config typo."""
    monkeypatch.setenv("HALO_HOME", str(tmp_path))
    (tmp_path / "test-config.toml").write_text(
        '[held_out_eval]\nwer_threshold = 1.5\n',  # out of [0, 1]
        encoding="utf-8",
    )
    assert _load_wer_threshold() == DEFAULT_WER_THRESHOLD


def test_wer_threshold_wrong_type_falls_back(tmp_path, monkeypatch):
    """A non-numeric threshold falls back to the default."""
    monkeypatch.setenv("HALO_HOME", str(tmp_path))
    (tmp_path / "test-config.toml").write_text(
        '[held_out_eval]\nwer_threshold = "strict"\n',
        encoding="utf-8",
    )
    assert _load_wer_threshold() == DEFAULT_WER_THRESHOLD
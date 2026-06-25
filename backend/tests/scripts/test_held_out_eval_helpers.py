"""Sprint 38 — tests for the shared held_out_eval helpers.

The bash `record-held-out.sh` calls a subset of these
helpers (date formatting, filename, transcript validation)
via inline Python. The pytest surface verifies the
contract independently of the bash script — the bash
script's interactive parts (recorder playback, editor
launch) are NOT tested here.
"""
from __future__ import annotations

from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# heldout_filename — date + ext validation
# ---------------------------------------------------------------------------


def test_heldout_filename_basic():
    """Normal case: ISO date + 'wav'."""
    from app.voice.held_out_eval import heldout_filename

    assert heldout_filename("2026-06-25") == "held-out-2026-06-25.wav"
    assert heldout_filename("2026-06-25", ext="txt") == "held-out-2026-06-25.txt"


def test_heldout_filename_rejects_bad_date():
    """Non-ISO date strings raise ValueError."""
    from app.voice.held_out_eval import heldout_filename

    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        heldout_filename("2026/06/25")
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        heldout_filename("2026-6-25")  # single-digit month/day
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        heldout_filename("not-a-date")


def test_heldout_filename_rejects_bad_ext():
    """Path-separator ext would let the bash script write
    outside the recordings dir — reject."""
    from app.voice.held_out_eval import heldout_filename

    with pytest.raises(ValueError, match="alphanumeric"):
        heldout_filename("2026-06-25", ext="../../etc/passwd")
    with pytest.raises(ValueError, match="alphanumeric"):
        heldout_filename("2026-06-25", ext="wav;rm -rf /")


# ---------------------------------------------------------------------------
# today_iso_date — local-time YYYY-MM-DD
# ---------------------------------------------------------------------------


def test_today_iso_date_format():
    """Returns today's local date as YYYY-MM-DD."""
    from datetime import date

    from app.voice.held_out_eval import today_iso_date

    assert today_iso_date() == date.today().isoformat()


# ---------------------------------------------------------------------------
# word_error_rate — Levenshtein DP
# ---------------------------------------------------------------------------


def test_word_error_rate_perfect_match():
    """Reference == hypothesis → WER 0.0."""
    from app.voice.held_out_eval import word_error_rate

    assert word_error_rate("你好 世界", "你好 世界") == 0.0
    assert word_error_rate("hello world", "hello world") == 0.0


def test_word_error_rate_empty_inputs():
    """Both empty → 0.0. Either empty → 1.0."""
    from app.voice.held_out_eval import word_error_rate

    assert word_error_rate("", "") == 0.0
    assert word_error_rate("", "extra word") == 1.0
    assert word_error_rate("missing word", "") == 1.0


def test_word_error_rate_deletion_only():
    """Hypothesis shorter than reference → all deletions."""
    from app.voice.held_out_eval import word_error_rate

    # 1 deletion / 2 ref words = 0.5
    assert word_error_rate("你好 世界", "你好") == 0.5


def test_word_error_rate_substitution():
    """Substitution = 1 error / N ref words."""
    from app.voice.held_out_eval import word_error_rate

    # 1 substitution / 2 ref words = 0.5
    assert word_error_rate("你好 世界", "你好呀 世界") == 0.5


def test_word_error_rate_insertion_and_deletion():
    """Multi-word insertion + deletion weighted by edit count."""
    from app.voice.held_out_eval import word_error_rate

    # "A B" vs "X Y Z" → 2 sub + 1 ins = 3 / 2 = 1.5
    assert word_error_rate("A B", "X Y Z") == 1.5


# ---------------------------------------------------------------------------
# load_wer_threshold — falls back to default when no config
# ---------------------------------------------------------------------------


def test_load_wer_threshold_default(monkeypatch, tmp_path):
    """When HALO_HOME has no test-config.toml, returns the
    default (15%)."""
    monkeypatch.setenv("HALO_HOME", str(tmp_path))
    from app.voice.held_out_eval import load_wer_threshold, DEFAULT_WER_THRESHOLD

    assert load_wer_threshold() == DEFAULT_WER_THRESHOLD


def test_load_wer_threshold_from_config(monkeypatch, tmp_path):
    """When test-config.toml has [held_out_eval].wer_threshold,
    that value wins."""
    monkeypatch.setenv("HALO_HOME", str(tmp_path))
    (tmp_path / "test-config.toml").write_text(
        "[held_out_eval]\nwer_threshold = 0.10\n"
    )
    from app.voice.held_out_eval import load_wer_threshold

    assert load_wer_threshold() == 0.10


def test_load_wer_threshold_clamps_out_of_range(monkeypatch, tmp_path):
    """Out-of-range threshold (e.g. -0.5, 1.5) falls back to default."""
    monkeypatch.setenv("HALO_HOME", str(tmp_path))
    (tmp_path / "test-config.toml").write_text(
        "[held_out_eval]\nwer_threshold = 1.5\n"
    )
    from app.voice.held_out_eval import load_wer_threshold, DEFAULT_WER_THRESHOLD

    assert load_wer_threshold() == DEFAULT_WER_THRESHOLD


# ---------------------------------------------------------------------------
# latest_heldout_wav + heldout_paths — HALO_HOME redirection
# ---------------------------------------------------------------------------


def test_latest_heldout_wav_empty_dir(monkeypatch, tmp_path):
    """When recordings/ doesn't exist, returns None."""
    monkeypatch.setenv("HALO_HOME", str(tmp_path))
    from app.voice.held_out_eval import latest_heldout_wav

    assert latest_heldout_wav() is None


def test_latest_heldout_wav_picks_newest(monkeypatch, tmp_path):
    """When multiple held-out-<date>.wav exist, picks by mtime."""
    monkeypatch.setenv("HALO_HOME", str(tmp_path))
    recordings = tmp_path / "recordings"
    recordings.mkdir()
    old = recordings / "held-out-2026-01-01.wav"
    new = recordings / "held-out-2026-06-25.wav"
    old.write_bytes(b"old")
    new.write_bytes(b"new")
    # Force mtime ordering.
    import os
    os.utime(old, (1000, 1000))
    os.utime(new, (2000, 2000))

    from app.voice.held_out_eval import latest_heldout_wav

    assert latest_heldout_wav() == new


def test_heldout_paths_returns_both(monkeypatch, tmp_path):
    """heldout_paths returns (wav, txt) — None when either missing."""
    monkeypatch.setenv("HALO_HOME", str(tmp_path))
    recordings = tmp_path / "recordings"
    recordings.mkdir()

    from app.voice.held_out_eval import heldout_paths

    # Both present.
    wav = recordings / "held-out-2026-06-25.wav"
    txt = recordings / "held-out-2026-06-25.txt"
    wav.write_bytes(b"x")
    txt.write_text("ref")
    w, t = heldout_paths()
    assert w == wav
    assert t == txt

    # WAV only (no txt).
    txt.unlink()
    w, t = heldout_paths()
    assert w == wav
    assert t is None


# ---------------------------------------------------------------------------
# check_cached_whisper_model
# ---------------------------------------------------------------------------


def test_check_cached_whisper_model_hit(monkeypatch, tmp_path):
    """Returns the cached .pt path when present."""
    monkeypatch.setenv("WHISPER_CACHE", str(tmp_path))
    (tmp_path / "base.pt").write_bytes(b"fake-pt")
    from app.voice.held_out_eval import check_cached_whisper_model

    assert check_cached_whisper_model("base") == tmp_path / "base.pt"


def test_check_cached_whisper_model_miss(monkeypatch, tmp_path):
    """Returns None when cache dir has no matching .pt."""
    monkeypatch.setenv("WHISPER_CACHE", str(tmp_path))
    from app.voice.held_out_eval import check_cached_whisper_model

    assert check_cached_whisper_model("base") is None


# ---------------------------------------------------------------------------
# wav_to_pcm_bytes — format validation
# ---------------------------------------------------------------------------


def test_wav_to_pcm_bytes_format_validation(tmp_path):
    """Non-16kHz / non-mono / non-s16le WAV raises ValueError."""
    from app.voice.held_out_eval import wav_to_pcm_bytes

    # Build a stereo WAV manually (whisper requires mono).
    import wave
    stereo = tmp_path / "stereo.wav"
    with wave.open(str(stereo), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(16_000)
        wf.writeframes(b"\x00\x00" * 32)  # 16 samples * 2 channels = 32 bytes
    with pytest.raises(ValueError, match="mono"):
        wav_to_pcm_bytes(stereo)

"""Tests for the wake-phrase detection helper.

The matcher is pure-string, in-process — fast and easy to exhaustively
test. We cover:
  - exact match in each canonical form
  - case insensitivity
  - ASR artifacts (e.g. "Unicorn  幫我" → phrase stripped + filler word
    stripped too)
  - non-matching transcripts
  - empty / weird inputs
  - the helper used by the UI (`first_wake_phrase`)
"""
from __future__ import annotations

import pytest

from app.voice.wake_phrase import detect_wake_phrase, first_wake_phrase


PHRASES = ["Unicorn", "NTD", "gundam", "獨角獸", "高達"]


# ---- exact match (English) ----


def test_unicorn_exact():
    m = detect_wake_phrase("Unicorn, open Safari", PHRASES)
    assert m.matched is True
    assert m.phrase == "Unicorn"
    assert m.stripped == "open Safari"


def test_unicorn_lowercase():
    """Case-insensitive — Whisper may emit 'unicorn'."""
    m = detect_wake_phrase("unicorn, open Safari", PHRASES)
    assert m.matched is True
    assert m.phrase == "Unicorn"  # canonical from the user's list
    assert m.stripped == "open Safari"


def test_ntd():
    m = detect_wake_phrase("NTD what is the weather", PHRASES)
    assert m.matched is True
    assert m.phrase == "NTD"
    assert m.stripped == "what is the weather"


def test_gundam_lowercase():
    m = detect_wake_phrase("gundam, take a screenshot", PHRASES)
    assert m.matched is True
    assert m.phrase == "gundam"
    assert m.stripped == "take a screenshot"


# ---- exact match (Chinese) ----


def test_cantonese_unicorn():
    m = detect_wake_phrase("獨角獸 開 Safari", PHRASES)
    assert m.matched is True
    assert m.phrase == "獨角獸"
    assert m.stripped == "開 Safari"


def test_cantonese_gundam():
    m = detect_wake_phrase("高達 幫我打開 Chrome", PHRASES)
    assert m.matched is True
    assert m.phrase == "高達"
    # The "幫我" filler is also stripped.
    assert m.stripped == "打開 Chrome"


# ---- no match ----


def test_no_match():
    m = detect_wake_phrase("what's the weather?", PHRASES)
    assert m.matched is False
    assert m.phrase == ""
    assert m.stripped == "what's the weather?"


def test_no_match_unicorn_in_middle():
    """Wake phrase only at the start counts."""
    m = detect_wake_phrase("open Unicorn for me", PHRASES)
    assert m.matched is False
    assert m.stripped == "open Unicorn for me"


def test_empty_input():
    m = detect_wake_phrase("", PHRASES)
    assert m.matched is False
    assert m.stripped == ""


def test_empty_phrases_list():
    m = detect_wake_phrase("Unicorn hello", [])
    assert m.matched is False
    assert m.stripped == "Unicorn hello"


def test_whitespace_only_input():
    m = detect_wake_phrase("   \t  ", PHRASES)
    assert m.matched is False
    assert m.stripped == ""


# ---- filler-word handling ----


def test_filler_after_wake_phrase_is_stripped():
    """Cantonese speakers say "高達幫我" (= "Gundam, help me"); the
    filler "幫我" should also be stripped."""
    m = detect_wake_phrase("高達 幫我 開 個 Terminal", PHRASES)
    assert m.matched is True
    assert m.stripped == "開 個 Terminal"


def test_filler_does_not_double_strip():
    """If the user's text is "幫我 開 Terminal" (no wake phrase at
    all), the filler should NOT be stripped."""
    m = detect_wake_phrase("幫我 開 Terminal", PHRASES)
    assert m.matched is False
    # Filler is only stripped AFTER a wake phrase match; without
    # a match, the entire text is returned.
    assert m.stripped == "幫我 開 Terminal"


def test_punctuation_after_wake_phrase_stripped():
    m = detect_wake_phrase("Unicorn,  開 Gmail", PHRASES)
    assert m.matched is True
    assert m.stripped == "開 Gmail"


# ---- unicode normalization ----


def test_full_width_unicorn():
    """Some users on iOS / Pinyin keyboards may emit the full-width
    'Ｕｎｉｃｏｒｎ' form. NFKC normalization should fold it back."""
    m = detect_wake_phrase("\uff35\uff4e\uff49\uff43\uff4f\uff52\uff4e open Safari", PHRASES)
    assert m.matched is True
    assert m.stripped == "open Safari"


# ---- scan bound ----


def test_wake_phrase_at_position_50():
    """Wake phrase can be the FIRST word but not preceded by
    other words — leading-wake semantics. A 50-char padding prefix
    means the wake phrase is NOT leading, so it must NOT match."""
    pad = "x" * 50
    m = detect_wake_phrase(f"{pad} Unicorn open Safari", PHRASES)
    assert m.matched is False


def test_wake_phrase_beyond_scan_window():
    """Same: wake phrase after a long prefix should not match."""
    pad = "x" * 65
    m = detect_wake_phrase(f"{pad} Unicorn open Safari", PHRASES)
    assert m.matched is False


def test_wake_phrase_leading_with_small_padding():
    """Wake phrase at position 5 is fine — we just need it to be
    the first non-whitespace word."""
    text = "    Unicorn open Safari"  # 4 leading spaces
    m = detect_wake_phrase(text, PHRASES)
    assert m.matched is True
    # The leading whitespace is preserved in the tail (we strip
    # only the wake phrase itself, not pre-wake whitespace — the
    # user wouldn't usually have leading whitespace anyway).
    assert "open Safari" in m.stripped


# ---- first_wake_phrase helper ----


def test_first_wake_phrase():
    assert first_wake_phrase(PHRASES) == "Unicorn"


def test_first_wake_phrase_skips_empty():
    assert first_wake_phrase(["", "  ", "NTD"]) == "NTD"


def test_first_wake_phrase_empty_list():
    assert first_wake_phrase([]) is None
    assert first_wake_phrase(["", "  "]) is None


# ---- longer phrase wins on partial overlap ----


def test_longest_phrase_wins_on_partial_overlap():
    """If a user accidentally has both 'NTD' and 'NTD-pilot' in
    their list, the longer match should win (else the shorter
    would shadow the longer on some transcripts)."""
    m = detect_wake_phrase("NTD-pilot, status?", ["NTD", "NTD-pilot"])
    assert m.phrase == "NTD-pilot"
    assert m.stripped == "status?"

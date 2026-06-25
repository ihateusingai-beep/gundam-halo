"""Sprint 42 — TOML config fail-loud tests.

Verifies the `_load_toml` hardening:
- Missing TOML → empty dict (regression: existing happy path)
- Malformed TOML → ConfigParseError with file/line/column
  (instead of raw tomllib.TOMLDecodeError stack trace)
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# 1. Missing TOML → empty dict (regression — Sprint 32 P1.3 baseline)
# ---------------------------------------------------------------------------


def test_missing_toml_returns_empty_dict(tmp_path):
    """Non-existent config.toml → empty dict (load_config() then
    fills in dataclass defaults). This is the existing happy
    path for fresh installs — must stay working."""
    from app.core.config_loader import _load_toml

    missing = tmp_path / "does-not-exist.toml"
    assert _load_toml(missing) == {}


# ---------------------------------------------------------------------------
# 2. Malformed TOML → ConfigParseError with position
# ---------------------------------------------------------------------------


def test_unclosed_table_bracket_raises_with_line_column(tmp_path):
    """`[voice.vad` (unclosed `[`) → ConfigParseError at line 1, col 11."""
    from app.core.config_loader import ConfigParseError, _load_toml

    bad = tmp_path / "bad.toml"
    bad.write_text("[voice.vad\nbad = 1\n")

    with pytest.raises(ConfigParseError) as exc_info:
        _load_toml(bad)

    err = exc_info.value
    assert err.config_path == bad
    assert err.line == 1
    assert err.column == 11
    assert "Expected ']'" in str(err)
    assert str(err).startswith(f"Failed to parse {bad}:")


def test_unterminated_string_raises_with_line_column(tmp_path):
    """`a = "unclosed` → ConfigParseError at line 1, col 14
    (Python 3.11 tomllib reports "Illegal character '\\n'
    (at line 1, column 14)")."""
    from app.core.config_loader import ConfigParseError, _load_toml

    bad = tmp_path / "bad.toml"
    bad.write_text('a = "unclosed\n')

    with pytest.raises(ConfigParseError) as exc_info:
        _load_toml(bad)
    err = exc_info.value
    assert err.line == 1
    assert err.column == 14


def test_config_parse_error_message_includes_repro_hint(tmp_path):
    """The error message includes the `uv run python -c ...`
    repro hint so the user can debug without reading source."""
    from app.core.config_loader import ConfigParseError, _load_toml

    bad = tmp_path / "bad.toml"
    bad.write_text("[voice.vad\nbad = 1\n")

    with pytest.raises(ConfigParseError) as exc_info:
        _load_toml(bad)

    msg = str(exc_info.value)
    assert "uv run python" in msg, (
        "Error message should hint at the manual repro command"
    )
    assert str(bad) in msg, "Error should include the offending file path"


# ---------------------------------------------------------------------------
# 3. ConfigParseError attributes are stable
# ---------------------------------------------------------------------------


def test_config_parse_error_attributes_accessible():
    """The .config_path / .line / .column attributes are
    accessible on the exception (for callers that want to
    format their own error UI without re-parsing the message)."""
    from app.core.config_loader import ConfigParseError

    err = ConfigParseError(
        config_path=Path("/tmp/x.toml"),
        line=5,
        column=12,
        message="test syntax error",
    )
    assert err.config_path == Path("/tmp/x.toml")
    assert err.line == 5
    assert err.column == 12
    assert "test syntax error" in str(err)

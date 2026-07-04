"""Tests for `app.voice.audio_io` — the canonical ffmpeg→WAV helper.

Sprint 56 R2: covers the bug that prompted this module:
  - Sprint 54 `gen_cantonese_corpus.py` used `wave.open()` to probe
    duration. It returned 0.001s for every clip because ffmpeg
    inserts a LIST metadata chunk between the standard `fmt ` and
    `data` sub-chunks — the `data` chunk was no longer at byte 44,
    so the offset-read returned the LIST chunk size (26) divided
    by SAMPLE_RATE * 2 = 0.001s.
  - `soundfile` (used here) parses the actual WAV header so it
    works for BOTH layouts.

These tests use a synthetic 1-second sine wave to avoid needing
real MP3 test fixtures.
"""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np
import pytest


class TestWavDurationSeconds:
    """`wav_duration_seconds(wav_path)` reads the actual WAV header."""

    def test_standard_wav_header(self, tmp_path: Path):
        """Standard layout (data chunk at byte 44): soundfile reads
        the correct duration. The pre-Sprint-56 `wave.open()` probe
        would also succeed on this layout.
        """
        wav_path = tmp_path / "standard.wav"
        sr = 16000
        t = np.linspace(0, 1.0, sr, endpoint=False)  # 1 second
        x = (0.5 * np.sin(2 * np.pi * 440 * t) * 32767).astype(np.int16)
        with wave.open(str(wav_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes(x.tobytes())

        from app.voice.audio_io import wav_duration_seconds
        dur = wav_duration_seconds(wav_path)
        assert 0.95 < dur < 1.05, f"expected ~1s, got {dur}"

    def test_ffmpeg_list_extended_wav(self, tmp_path: Path):
        """ffmpeg-emitted WAV with LIST metadata chunk insertion.

        This is the layout the pre-Sprint-56 `wave.open()` probe
        BROKE: it would return 0.001s because the `data` chunk
        was no longer at byte 44.

        We use ffmpeg itself (when available) to generate a
        real LIST-extended WAV. If ffmpeg is not on PATH the test
        is skipped (no need to gate the canonical bug fix on
        ffmpeg being installed in the test env).
        """
        import shutil
        if not shutil.which("ffmpeg"):
            pytest.skip("ffmpeg not on PATH; real ffmpeg-emitted WAV unavailable")

        # Generate a real 1-second 440Hz sine wave through ffmpeg.
        # ffmpeg's WAV writer inserts a LIST/INFO/ISFT chunk
        # between fmt  and data — exactly the layout the pre-Sprint-56
        # `wave.open()` probe misread.
        wav_path = tmp_path / "ffmpeg_style.wav"
        import subprocess
        res = subprocess.run(
            [
                "ffmpeg", "-y", "-nostdin", "-loglevel", "error",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                "-ar", "16000", "-ac", "1", "-f", "wav",
                "-acodec", "pcm_s16le", str(wav_path),
            ],
            capture_output=True,
            text=True,
        )
        assert res.returncode == 0, f"ffmpeg failed: {res.stderr}"

        # Verify the WAV actually has the LIST chunk (the bug
        # condition). If a future ffmpeg drops the LIST chunk,
        # this test becomes degenerate — skip with a note.
        with open(wav_path, "rb") as f:
            header = f.read(200)
        if b"LIST" not in header:
            pytest.skip(
                "ffmpeg no longer inserts LIST chunk — test no longer "
                "exercises the pre-Sprint-56 bug condition"
            )

        from app.voice.audio_io import wav_duration_seconds
        dur = wav_duration_seconds(wav_path)
        # The pre-Sprint-56 `wave.open()` probe would return ~0.001s
        # for this file. We expect ~1.0s.
        assert 0.5 < dur < 2.0, (
            f"expected ~1.0s (LIST-chunk-handled), got {dur}. "
            f"This is the exact bug Sprint 56 R2 fixed: a LIST-chunk "
            f"between fmt  and data caused the wave.open() probe to "
            f"read LIST size (26) / SAMPLE_RATE * 2 = 0.001s."
        )


class TestFfmpegToWav:
    """`ffmpeg_to_wav` requires ffmpeg on PATH; we mock with a
    subprocess stub that writes a stubbed WAV directly. (Real
    end-to-end test in scripts/ requires a fixture MP3 file.)
    """

    def test_raises_if_ffmpeg_missing(self, monkeypatch, tmp_path: Path):
        """If `shutil.which('ffmpeg')` returns None, raise RuntimeError."""
        monkeypatch.setattr("shutil.which", lambda cmd: None)
        from app.voice.audio_io import ffmpeg_to_wav
        with pytest.raises(RuntimeError, match="ffmpeg not on PATH"):
            ffmpeg_to_wav(tmp_path / "in.mp3", tmp_path / "out.wav")

    def test_raises_if_input_missing(self, monkeypatch, tmp_path: Path):
        """If the input file doesn't exist, raise FileNotFoundError."""
        monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/ffmpeg")
        from app.voice.audio_io import ffmpeg_to_wav
        with pytest.raises(FileNotFoundError, match="input audio not found"):
            ffmpeg_to_wav(tmp_path / "missing.mp3", tmp_path / "out.wav")

    def test_ffmpeg_failure_propagates(self, monkeypatch, tmp_path: Path):
        """If ffmpeg exits non-zero, raise RuntimeError with the
        relevant stderr snippet."""
        monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/ffmpeg")
        # Stub `subprocess.run` to simulate ffmpeg failure
        class _Result:
            returncode = 1
            stderr = "Error: unsupported codec"
        monkeypatch.setattr(
            "subprocess.run",
            lambda *args, **kw: _Result(),
        )

        in_p = tmp_path / "in.mp3"
        in_p.write_bytes(b"\x00")  # non-empty so FileNotFoundError skipped
        from app.voice.audio_io import ffmpeg_to_wav
        with pytest.raises(RuntimeError, match="ffmpeg failed"):
            ffmpeg_to_wav(in_p, tmp_path / "out.wav")


class TestSampleRateConstant:
    """`SAMPLE_RATE = 16_000` is exported and frozen."""

    def test_sample_rate_is_16k(self):
        from app.voice.audio_io import SAMPLE_RATE
        assert SAMPLE_RATE == 16_000

    def test_sample_rate_is_int(self):
        """Both `int` and `Final[int]` typing — verify runtime type."""
        from app.voice.audio_io import SAMPLE_RATE
        assert isinstance(SAMPLE_RATE, int)

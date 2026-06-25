"""Sprint 38 — CLI runner test.

Mirrors `tests/voice/test_held_out_eval.py` (the pytest
surface) but exercises `scripts/run_held_out_eval.py`:
the dry-run path, the real-inference path (with mocked
ASR), and the exit-code contract.

We don't actually invoke `whisper.load_model('base')` in
tests — the ASR is mocked at the `asr_factory.create_asr`
boundary, so the test runs without the 75 MB base.pt
and without any real Whisper dependency.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add scripts/ to sys.path so `import run_held_out_eval` works.
SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import run_held_out_eval  # noqa: E402  (after sys.path tweak)


# ---------------------------------------------------------------------------
# Fixtures — write a synthetic held-out WAV + TXT in tmp_path,
# redirect HALO_HOME so `latest_heldout_wav()` finds them.
# ---------------------------------------------------------------------------


def _write_silent_wav(path: Path, duration_s: float = 1.0, sr: int = 16000) -> None:
    """Write a 16 kHz mono s16le WAV with silence.

    Matches the format `wav_to_pcm_bytes` validates
    against (mono, s16le, 16 kHz).
    """
    import wave

    n_frames = int(duration_s * sr)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(b"\x00\x00" * n_frames)


@pytest.fixture
def heldout_dir(monkeypatch, tmp_path):
    """Set HALO_HOME to tmp_path; create recordings/ + a held-out WAV + TXT."""
    monkeypatch.setenv("HALO_HOME", str(tmp_path))
    recordings = tmp_path / "recordings"
    recordings.mkdir()
    wav = recordings / "held-out-2026-06-25.wav"
    _write_silent_wav(wav, duration_s=1.0)
    txt = recordings / "held-out-2026-06-25.txt"
    txt.write_text("你好 世界")
    return wav, txt


# ---------------------------------------------------------------------------
# 1. Path resolution
# ---------------------------------------------------------------------------


def test_resolve_paths_finds_latest_heldout(monkeypatch, tmp_path):
    """Default path: pick latest held-out-<date>.{wav,txt}."""
    monkeypatch.setenv("HALO_HOME", str(tmp_path))
    recordings = tmp_path / "recordings"
    recordings.mkdir()
    wav = recordings / "held-out-2026-06-25.wav"
    _write_silent_wav(wav)
    txt = recordings / "held-out-2026-06-25.txt"
    txt.write_text("ref")

    args = MagicMock(wav=None, txt=None)
    resolved = run_held_out_eval._resolve_paths(args)
    assert resolved == (wav, txt)


def test_resolve_paths_explicit_overrides(monkeypatch, tmp_path):
    """--wav + --txt override the latest lookup."""
    monkeypatch.setenv("HALO_HOME", str(tmp_path))
    (tmp_path / "recordings").mkdir()
    explicit_wav = tmp_path / "explicit.wav"
    _write_silent_wav(explicit_wav)
    explicit_txt = tmp_path / "explicit.txt"
    explicit_txt.write_text("ref")

    args = MagicMock(wav=explicit_wav, txt=explicit_txt)
    resolved = run_held_out_eval._resolve_paths(args)
    assert resolved == (explicit_wav, explicit_txt)


def test_resolve_paths_missing_wav(monkeypatch, tmp_path):
    """No held-out set → returns None."""
    monkeypatch.setenv("HALO_HOME", str(tmp_path))
    args = MagicMock(wav=None, txt=None)
    assert run_held_out_eval._resolve_paths(args) is None


# ---------------------------------------------------------------------------
# 2. Backend construction (mocked)
# ---------------------------------------------------------------------------


def test_resolve_asr_backend_constructs_via_factory(monkeypatch):
    """The CLI builds the ASR via asr_factory.create_asr(cfg.voice.asr)."""
    fake_asr = MagicMock()
    with patch("run_held_out_eval.asr_factory.create_asr", return_value=fake_asr):
        result = run_held_out_eval._resolve_asr_backend(MagicMock(backend=None))
    assert result is fake_asr


def test_resolve_asr_backend_overrides_config(monkeypatch):
    """--backend whisper_hf mutates cfg.voice.asr.backend before
    constructing the ASR."""
    fake_asr = MagicMock()
    with patch("run_held_out_eval.asr_factory.create_asr", return_value=fake_asr) as factory_mock:
        run_held_out_eval._resolve_asr_backend(MagicMock(backend="whisper_hf"))
    # The factory was called with the mutated cfg.
    cfg_arg = factory_mock.call_args.args[0]
    assert cfg_arg.backend == "whisper_hf"


def test_resolve_asr_backend_factory_error_returns_none(monkeypatch):
    """If asr_factory raises, _resolve_asr_backend returns None."""
    with patch(
        "run_held_out_eval.asr_factory.create_asr",
        side_effect=RuntimeError("model missing"),
    ):
        assert run_held_out_eval._resolve_asr_backend(MagicMock(backend=None)) is None


# ---------------------------------------------------------------------------
# 3. Inference (mocked ASR)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_inference_mocked_asr():
    """The inference loop calls warmup + transcribe; returns (hypothesis, duration_s)."""
    fake_asr = MagicMock()
    fake_asr.warmup = AsyncMock(return_value=None)
    fake_asr.transcribe = AsyncMock(return_value="你好 世界")
    hypothesis, duration_s = await run_held_out_eval._run_inference(fake_asr, b"\x00" * 32, 16000)
    assert hypothesis == "你好 世界"
    assert duration_s >= 0
    fake_asr.warmup.assert_awaited_once()
    fake_asr.transcribe.assert_awaited_once_with(b"\x00" * 32, sample_rate=16000)


# ---------------------------------------------------------------------------
# 4. CLI main() — full integration (mocked ASR, tmp_path WAV)
# ---------------------------------------------------------------------------


def test_cli_main_dry_run_no_wav_exits_2(monkeypatch, tmp_path, capsys):
    """Dry-run with no held-out WAV → exit 2 (no fixture)."""
    monkeypatch.setenv("HALO_HOME", str(tmp_path))
    rc = run_held_out_eval.main(["--dry-run"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "No held-out WAV found" in err
    assert "scripts/record-held-out.sh" in err


def test_cli_main_dry_run_with_wav_exits_0(monkeypatch, heldout_dir, capsys):
    """Dry-run with valid WAV + TXT → exit 0, prints summary."""
    rc = run_held_out_eval.main(["--dry-run"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "DRY RUN" in out
    assert "held-out-2026-06-25.wav" in out
    assert "Threshold" in out


def test_cli_main_real_eval_pass(monkeypatch, heldout_dir, capsys):
    """Mocked ASR returns reference verbatim → WER = 0 → exit 0."""
    fake_asr = MagicMock()
    fake_asr.warmup = AsyncMock(return_value=None)
    fake_asr.transcribe = AsyncMock(return_value="你好 世界")

    with patch("run_held_out_eval.asr_factory.create_asr", return_value=fake_asr):
        with patch("run_held_out_eval.wav_to_pcm_bytes", return_value=(b"\x00" * 32, 16000)):
            rc = run_held_out_eval.main([])

    assert rc == 0, capsys.readouterr().out
    out = capsys.readouterr().out
    assert "WER: 0.0%" in out
    assert "PASS" in out


def test_cli_main_real_eval_fail(monkeypatch, heldout_dir, capsys):
    """Mocked ASR returns garbage → WER > 0 → exit 1."""
    fake_asr = MagicMock()
    fake_asr.warmup = AsyncMock(return_value=None)
    fake_asr.transcribe = AsyncMock(return_value="完全唔同嘅嘢")

    with patch("run_held_out_eval.asr_factory.create_asr", return_value=fake_asr):
        with patch("run_held_out_eval.wav_to_pcm_bytes", return_value=(b"\x00" * 32, 16000)):
            rc = run_held_out_eval.main([])

    assert rc == 1
    out = capsys.readouterr().out
    assert "FAIL" in out


def test_cli_main_threshold_override(monkeypatch, heldout_dir, capsys):
    """--threshold 0.0 forces any non-perfect match to fail.

    Threshold is `<` (exclusive), so `wer < 0.0` is never
    True unless we have a NaN — meaning a WER > 0 always
    fails. WER = 0 passes (passes are the strict
    threshold + epsilon).
    """
    fake_asr = MagicMock()
    fake_asr.warmup = AsyncMock(return_value=None)
    # WER > 0 (substitution): 1/2 = 0.5
    fake_asr.transcribe = AsyncMock(return_value="你好呀 世界")

    with patch("run_held_out_eval.asr_factory.create_asr", return_value=fake_asr):
        with patch("run_held_out_eval.wav_to_pcm_bytes", return_value=(b"\x00" * 32, 16000)):
            rc = run_held_out_eval.main(["--threshold", "0.0"])
    assert rc == 1  # 0.5 < 0.0 → false → FAIL
    out = capsys.readouterr().out
    assert "FAIL" in out


def test_cli_main_writes_trend_json(monkeypatch, heldout_dir, tmp_path):
    """Run real eval → JSON file appears under --out."""
    fake_asr = MagicMock()
    fake_asr.warmup = AsyncMock(return_value=None)
    fake_asr.transcribe = AsyncMock(return_value="你好 世界")

    out_path = tmp_path / "result.json"
    with patch("run_held_out_eval.asr_factory.create_asr", return_value=fake_asr):
        with patch("run_held_out_eval.wav_to_pcm_bytes", return_value=(b"\x00" * 32, 16000)):
            rc = run_held_out_eval.main(["--out", str(out_path)])
    assert rc == 0
    assert out_path.is_file()

    # JSON shape: {"timestamp": ..., "results": [{...EvalResult...}]}
    data = json.loads(out_path.read_text())
    assert "timestamp" in data
    assert len(data["results"]) == 1
    r = data["results"][0]
    assert r["wer"] == 0.0
    assert r["passed"] is True
    assert r["reference"] == "你好 世界"
    assert r["hypothesis"] == "你好 世界"

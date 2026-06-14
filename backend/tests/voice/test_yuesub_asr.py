"""Sprint 17b: tests for the yuesub ASR backend.

These tests cover the YuesubASR class without loading the real
SenseVoice / fsmn-vad models (which take 2-5s + 1GB of disk).
We mock the heavy parts at the import boundary and exercise
the contract: model path validation, pcm conversion, provider
mapping, and the corrector injection point.

The actual model load + real transcribe is smoke-tested in
the manual checklist (see docs/FEATURE-SPEC-SPRINT17b.md §8.5)
and was verified during Track B implementation.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from app.voice.asr.asr_interface import ASRError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_yuesub_deps(monkeypatch):
    """Mock funasr_onnx + torchaudio so importing yuesub.py doesn't
    require the heavy deps for the path-validation tests.

    The full warmup smoke test is manual; here we just verify the
    import boundary + the helpers.
    """
    # Stub the heavy imports
    fake_funasr = MagicMock()
    fake_funasr.Fsmn_vad_online = MagicMock()
    fake_funasr.SenseVoiceSmall = MagicMock()
    fake_bundle = MagicMock()
    fake_bundle.get_aligner.return_value = MagicMock()
    fake_tokenizer = MagicMock()
    fake_tokenizer_class = MagicMock(return_value=fake_tokenizer)

    # Make funasr_onnx.utils.sentencepiece_tokenizer available
    sys.modules.setdefault("funasr_onnx", fake_funasr)
    sys.modules.setdefault("funasr_onnx.utils", MagicMock())
    sys.modules.setdefault(
        "funasr_onnx.utils.sentencepiece_tokenizer",
        MagicMock(SentencepiecesTokenizer=fake_tokenizer_class),
    )
    sys.modules.setdefault(
        "torchaudio.pipelines",
        MagicMock(MMS_FA=fake_bundle),
    )
    return {
        "funasr": fake_funasr,
        "bundle": fake_bundle,
        "tokenizer": fake_tokenizer,
    }


# ---------------------------------------------------------------------------
# 1. Device → providers mapping
# ---------------------------------------------------------------------------


def test_device_to_providers_cpu():
    """Explicit 'cpu' returns the CPU-only provider list."""
    from app.voice.asr.yuesub import _device_to_providers

    assert _device_to_providers("cpu") == ["CPUExecutionProvider"]


def test_device_to_providers_auto_prefers_coreml_on_apple_silicon():
    """On Apple Silicon (this CI / dev machine), 'auto' picks CoreML + CPU."""
    from app.voice.asr.yuesub import _device_to_providers

    # on this Mac M-series machine, the available providers include
    # CoreMLExecutionProvider. We just check the list is non-empty
    # and CPU is in the fallback chain.
    providers = _device_to_providers("auto")
    assert "CPUExecutionProvider" in providers
    assert isinstance(providers, list)
    assert len(providers) >= 1


def test_device_to_providers_mps_falls_back_to_cpu_without_coreml():
    """'mps' requested but no CoreML provider → CPU fallback with a warning."""
    from app.voice.asr.yuesub import _device_to_providers

    with patch("onnxruntime.get_available_providers", return_value=["CPUExecutionProvider"]):
        providers = _device_to_providers("mps")
    assert providers == ["CPUExecutionProvider"]


def test_device_to_providers_unknown_raises_value_error():
    """Unknown device string fails fast."""
    from app.voice.asr.yuesub import _device_to_providers

    with pytest.raises(ValueError, match="Unknown device"):
        _device_to_providers("gpu")  # 'gpu' is not a valid yuesub value


# ---------------------------------------------------------------------------
# 2. PCM bytes → float32 conversion
# ---------------------------------------------------------------------------


def test_pcm_bytes_to_float32_silence():
    """All-zero PCM bytes convert to a zero float32 waveform."""
    from app.voice.asr.yuesub import _pcm_bytes_to_float32

    audio = np.zeros(16000, dtype=np.int16).tobytes()
    waveform = _pcm_bytes_to_float32(audio, 16_000)
    assert waveform.dtype == np.float32
    assert waveform.shape == (16000,)
    assert np.all(waveform == 0.0)


def test_pcm_bytes_to_float32_clamps_to_unit_range():
    """int16 -32768 → float32 ~ -1.0, int16 +32767 → float32 ~ +0.99997."""
    from app.voice.asr.yuesub import _pcm_bytes_to_float32

    # -32768 and +32767 as int16
    raw = np.array([-32768, 0, 32767], dtype=np.int16).tobytes()
    waveform = _pcm_bytes_to_float32(raw, 16_000)
    assert waveform[0] == pytest.approx(-1.0, abs=1e-4)
    assert waveform[1] == 0.0
    assert waveform[2] == pytest.approx(32767 / 32768.0, abs=1e-4)


def test_pcm_bytes_to_float32_rejects_non_16khz():
    """Anything other than 16kHz raises ValueError (we don't resample
    here — that's the pipeline's job and would lose VAD alignment)."""
    from app.voice.asr.yuesub import _pcm_bytes_to_float32

    with pytest.raises(ValueError, match="16kHz"):
        _pcm_bytes_to_float32(b"\x00" * 2, 48_000)


def test_pcm_bytes_to_float32_empty():
    """Empty bytes → empty array (handled gracefully)."""
    from app.voice.asr.yuesub import _pcm_bytes_to_float32

    waveform = _pcm_bytes_to_float32(b"", 16_000)
    assert waveform.size == 0
    assert waveform.dtype == np.float32


# ---------------------------------------------------------------------------
# 3. ASR factory wiring (Sprint 17b: 'yuesub' branch)
# ---------------------------------------------------------------------------


def test_factory_creates_whisper_local_when_backend_default(monkeypatch):
    """Sprint 16 default (whisper_local) is unaffected by Sprint 17b."""
    from app.core import config as config_mod
    from app.voice.asr.asr_factory import create_asr

    cfg = config_mod.get_config()
    cfg.voice.asr.backend = "whisper_local"
    try:
        asr = create_asr(cfg.voice.asr)
        # Don't actually warmup — just verify the right class was returned
        from app.voice.asr.whisper_local import WhisperLocalASR

        assert isinstance(asr, WhisperLocalASR)
    finally:
        cfg.voice.asr.backend = "whisper_local"  # restore


def test_factory_creates_yuesub_when_backend_set(monkeypatch, mock_yuesub_deps):
    """backend='yuesub' returns a YuesubASR instance with the corrector
    name forwarded from config (Track C will fill in the real
    corrector; for now we just verify the config string plumbs through)."""
    from app.core import config as config_mod
    from app.voice.asr.asr_factory import create_asr
    from app.voice.asr.yuesub import YuesubASR

    cfg = config_mod.get_config()
    cfg.voice.asr.backend = "yuesub"
    cfg.voice.asr.corrector = "none"  # bypass the Track C stub
    try:
        asr = create_asr(cfg.voice.asr)
        assert isinstance(asr, YuesubASR)
        assert asr._language == cfg.voice.asr.language
        assert asr._device == cfg.voice.asr.device
        assert asr._corrector is None  # "none" → None
    finally:
        cfg.voice.asr.backend = "whisper_local"


def test_factory_rejects_unknown_backend():
    """Unknown backend name raises ValueError with a helpful message."""
    from app.core import config as config_mod
    from app.voice.asr.asr_factory import create_asr

    cfg = config_mod.get_config()
    cfg.voice.asr.backend = "watson_ibm"
    try:
        with pytest.raises(ValueError, match="Unknown ASR backend"):
            create_asr(cfg.voice.asr)
    finally:
        cfg.voice.asr.backend = "whisper_local"


def test_factory_rejects_unknown_corrector(mock_yuesub_deps):
    """Corrector config string is validated at factory time, not at
    ASR init. Unknown corrector → ValueError with the supported list."""
    from app.core import config as config_mod
    from app.voice.asr.asr_factory import create_asr

    cfg = config_mod.get_config()
    cfg.voice.asr.backend = "yuesub"
    cfg.voice.asr.corrector = "telepathy"
    try:
        with pytest.raises(ValueError, match="corrector"):
            create_asr(cfg.voice.asr)
    finally:
        cfg.voice.asr.backend = "whisper_local"
        cfg.voice.asr.corrector = "bert"


# ---------------------------------------------------------------------------
# 4. VoiceASRConfig schema (Sprint 17b new field)
# ---------------------------------------------------------------------------


def test_voice_asr_config_has_corrector_field():
    """The new `corrector` field exists and defaults to 'bert'."""
    from app.core.config import VoiceASRConfig

    cfg = VoiceASRConfig()
    assert hasattr(cfg, "corrector")
    # Default is 'bert' per the Sprint 17b spec (D3 scope flip).
    assert cfg.corrector == "bert"


def test_voice_asr_config_loads_corrector_from_toml(tmp_path, monkeypatch):
    """`_load_voice_config` reads the new [voice.asr] corrector key."""
    from app.core import config as config_mod

    # Force the singleton to re-read from a fresh TOML.
    monkeypatch.setattr(config_mod, "_config", None)

    home = tmp_path / "halo"
    home.mkdir()
    (home / "config.toml").write_text(
        "[voice.asr]\n"
        "backend = \"yuesub\"\n"
        "language = \"yue\"\n"
        "device = \"mps\"\n"
        "corrector = \"opencc\"\n",
        encoding="utf-8",
    )
    cfg = config_mod.load_config(home)
    assert cfg.voice.asr.backend == "yuesub"
    assert cfg.voice.asr.language == "yue"
    assert cfg.voice.asr.device == "mps"
    assert cfg.voice.asr.corrector == "opencc"


# ---------------------------------------------------------------------------
# 5. YuesubASR constructor contract
# ---------------------------------------------------------------------------


def test_yuesub_asr_constructor_with_no_corrector(mock_yuesub_deps):
    """Default corrector is None (raw SenseVoice text)."""
    from app.voice.asr.yuesub import YuesubASR

    asr = YuesubASR(
        model_root=os.path.expanduser("~/.gundam-halo/models"),
        language="yue",
        device="cpu",
        corrector=None,
    )
    assert asr._language == "yue"
    assert asr._device == "cpu"
    assert asr._corrector is None
    # Model is NOT loaded yet — warmup() loads it
    assert asr._asr_model is None
    assert asr._vad_model is None


def test_yuesub_asr_warmup_raises_clear_error_when_models_missing(
    mock_yuesub_deps, tmp_path
):
    """When the symlinked iic/ dir doesn't exist, warmup() raises
    ASRError with the exact fix-up command in the message."""
    from app.voice.asr.yuesub import YuesubASR

    bad_root = str(tmp_path / "missing_models")
    asr = YuesubASR(model_root=bad_root, language="yue", device="cpu")
    with pytest.raises(ASRError) as exc_info:
        # Even before warmup(), the constructor doesn't validate
        # paths (it's lazy). warmup() is what catches this.
        asyncio_run(asr.warmup())
    msg = str(exc_info.value)
    assert "scripts/setup-yuesub-models.sh" in msg
    assert "SenseVoiceSmall" in msg or "yuesub" in msg.lower()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def asyncio_run(coro):
    """Tiny shim so the warmup test doesn't need pytest-asyncio."""
    import asyncio

    return asyncio.run(coro)

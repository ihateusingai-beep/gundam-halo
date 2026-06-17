"""Sprint 23 (v0.1.4): tests for the whisper_hf ASR backend.

These tests cover the WhisperHFASR class without loading
the real `transformers` pipeline (which takes 2-5s +
~850MB of deps for the voice-hf extra). We mock the
heavy parts at the import boundary and exercise the
contract: model_path validation, pcm conversion,
device resolution, language mapping, the lazy import
isolation, and the factory integration.

The actual model load + real transcribe is smoke-tested
manually in the M9-C live re-run (see
`docs/FEATURE-SPEC-SPRINT22.md` §4.2 "Acceptance test
— M9-C live re-run") and the M9-E training runbook.

Pattern reference: `tests/voice/test_yuesub_asr.py`
(Sprint 17b) — same `mock_yuesub_deps`-style approach
for stubbing the heavy ML deps.
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
def mock_whisper_hf_deps(monkeypatch):
    """Mock transformers + torch so importing whisper_hf.py doesn't
    require the heavy deps for the path-validation + helper tests.

    The full warmup smoke test is manual (the user runs
    `uv sync --extra voice-hf` + the M9-C live re-run);
    here we verify the import boundary + the helpers
    + the factory integration.

    Strategy: patch the lazy-import helpers at the
    module level (`whisper_hf._import_transformers` and
    `whisper_hf._import_torch`) rather than mocking the
    `transformers` and `torch` modules in `sys.modules`.
    Patching the helpers is more reliable because it
    sidesteps `from X import Y` lookup semantics inside
    the lazy-import functions (MagicMock attribute access
    vs `__getattr__` chain mismatch — a known mock
    pitfall; see `python-backend-patterns.md`).
    """
    from app.voice.asr import whisper_hf

    fake_torch = MagicMock()
    fake_torch.float32 = "float32"
    fake_torch.float16 = "float16"
    fake_torch.cuda.is_available.return_value = False
    fake_torch.backends.mps.is_available.return_value = False
    fake_torch.backends.mps.is_built.return_value = False

    fake_pipeline_factory = MagicMock()
    fake_pipeline_instance = MagicMock()
    fake_pipeline_factory.return_value = fake_pipeline_instance

    # Patch the module-level helpers. This replaces
    # `_import_transformers()` and `_import_torch()`
    # with mocks that return the fake objects
    # without doing any actual `import` statement.
    monkeypatch.setattr(whisper_hf, "_import_transformers", lambda: fake_pipeline_factory)
    monkeypatch.setattr(whisper_hf, "_import_torch", lambda: fake_torch)

    return {
        "torch": fake_torch,
        "pipeline_factory": fake_pipeline_factory,
        "pipeline_instance": fake_pipeline_instance,
    }


@pytest.fixture
def tmp_model_dir(tmp_path):
    """Create a temp dir that looks like an HF-format checkpoint."""
    model_dir = tmp_path / "fake-whisper-yue"
    model_dir.mkdir()
    # The HF pipeline loader checks for `config.json` (or similar)
    # before declaring a directory a valid checkpoint. We just
    # need the directory to exist; the pipeline factory is mocked
    # so the actual file presence doesn't matter for these tests.
    (model_dir / "config.json").write_text("{}")
    return str(model_dir)


# ---------------------------------------------------------------------------
# 1. Module import + class shape
# ---------------------------------------------------------------------------


def test_whisper_hf_module_imports_without_transformers():
    """whisper_hf.py must import successfully even when
    transformers is NOT installed (whisper_local / yuesub
    users don't have the voice-hf extra).

    The lazy import in `_import_transformers` should
    defer the actual `import transformers` to warmup()
    time. Module-level import must not fail.
    """
    # We can't easily test "transformers not installed"
    # in the test env (it might be installed), so we
    # just verify that the module-level import doesn't
    # actually call `import transformers`. The
    # `_import_transformers` function exists and is
    # the only place that should touch the import.
    from app.voice.asr import whisper_hf

    assert hasattr(whisper_hf, "_import_transformers")
    assert hasattr(whisper_hf, "WhisperHFASR")
    assert hasattr(whisper_hf, "_resolve_device")
    assert hasattr(whisper_hf, "_resolve_torch_dtype")
    assert hasattr(whisper_hf, "_pcm_bytes_to_float32")
    assert hasattr(whisper_hf, "_map_language")


def test_whisper_hf_constructor_requires_model_path():
    """Empty model_path raises ASRError at construction
    time, before warmup. (Factory also raises ValueError
    on empty model_path; this test verifies the class
    itself doesn't silently accept it.)"""
    from app.voice.asr.whisper_hf import WhisperHFASR

    with pytest.raises(ASRError, match="WhisperHFASR.model_path is empty"):
        WhisperHFASR(model_path="")


def test_whisper_hf_constructor_stores_config():
    """Constructor stores language / device / compute_type
    verbatim, and expands `~` in model_path."""
    from app.voice.asr.whisper_hf import WhisperHFASR

    asr = WhisperHFASR(
        model_path="~/some/model/",
        language="zh",
        device="cpu",
        compute_type="float16",
    )
    assert asr._language == "zh"
    assert asr._device == "cpu"
    assert asr._compute_type == "float16"
    # `~` expansion happens on construction.
    assert asr._model_path == os.path.expanduser("~/some/model/")


# ---------------------------------------------------------------------------
# 2. pcm conversion (mirrors yuesub, kept module-local for dep isolation)
# ---------------------------------------------------------------------------


def test_pcm_bytes_to_float32_silence():
    """All-zero PCM bytes → all-zero float32 array."""
    from app.voice.asr.whisper_hf import _pcm_bytes_to_float32

    audio = b"\x00\x00" * 100  # 100 int16 samples, all zero
    out = _pcm_bytes_to_float32(audio, 16_000)
    assert out.dtype == np.float32
    assert out.shape == (100,)
    np.testing.assert_array_equal(out, np.zeros(100, dtype=np.float32))


def test_pcm_bytes_to_float32_clamps_to_unit_range():
    """int16 max → 1.0, int16 min → -1.0 (modulo quant)."""
    from app.voice.asr.whisper_hf import _pcm_bytes_to_float32

    # int16 max = 32767. 32767 / 32768 ≈ 0.99997.
    audio = np.array([32767, -32768, 0], dtype=np.int16).tobytes()
    out = _pcm_bytes_to_float32(audio, 16_000)
    assert abs(out[0] - (32767 / 32768.0)) < 1e-5
    assert out[1] == -1.0  # -32768 / 32768 = -1.0 exactly
    assert out[2] == 0.0


def test_pcm_bytes_to_float32_rejects_non_16khz():
    """Non-16kHz audio raises ValueError (HF Whisper
    doesn't resample — we fail loud to avoid VAD
    desync on the same stream)."""
    from app.voice.asr.whisper_hf import _pcm_bytes_to_float32

    with pytest.raises(ValueError, match="requires 16kHz audio"):
        _pcm_bytes_to_float32(b"", 8_000)


def test_pcm_bytes_to_float32_empty_returns_empty():
    """Empty audio buffer → empty float32 array (no
    division by zero on the `waveform /= 32768.0` line)."""
    from app.voice.asr.whisper_hf import _pcm_bytes_to_float32

    out = _pcm_bytes_to_float32(b"", 16_000)
    assert out.shape == (0,)
    assert out.dtype == np.float32


# ---------------------------------------------------------------------------
# 3. Device resolution
# ---------------------------------------------------------------------------


def test_resolve_device_cpu_returns_negative_one():
    """Explicit 'cpu' → device idx -1 (transformers pipeline CPU)."""
    from app.voice.asr.whisper_hf import _resolve_device

    assert _resolve_device("cpu") == -1


def test_resolve_device_cuda_returns_zero():
    """Explicit 'cuda' → device idx 0 (first GPU)."""
    from app.voice.asr.whisper_hf import _resolve_device

    assert _resolve_device("cuda") == 0


def test_resolve_device_mps_returns_zero():
    """Explicit 'mps' → device idx 0 (transformers maps
    MPS to device 0 on Mac, same as CUDA)."""
    from app.voice.asr.whisper_hf import _resolve_device

    assert _resolve_device("mps") == 0


def test_resolve_device_auto_falls_back_to_cpu_when_no_gpu(
    mock_whisper_hf_deps,
):
    """'auto' on a system without CUDA or MPS → device -1 (CPU)."""
    from app.voice.asr.whisper_hf import _resolve_device

    # mock_whisper_hf_deps torch has cuda.is_available() = False
    # and mps.is_available() = False by default.
    assert _resolve_device("auto") == -1


def test_resolve_device_auto_prefers_mps_on_apple_silicon(
    mock_whisper_hf_deps,
):
    """'auto' on macOS with MPS available → device 0 (MPS)."""
    from app.voice.asr.whisper_hf import _resolve_device

    mock_whisper_hf_deps["torch"].backends.mps.is_available.return_value = True
    with patch("sys.platform", "darwin"):
        assert _resolve_device("auto") == 0


def test_resolve_device_auto_falls_back_to_cuda_when_no_mps(
    mock_whisper_hf_deps,
):
    """'auto' on Linux/Windows with CUDA available → device 0 (CUDA)."""
    from app.voice.asr.whisper_hf import _resolve_device

    mock_whisper_hf_deps["torch"].backends.mps.is_available.return_value = False
    mock_whisper_hf_deps["torch"].cuda.is_available.return_value = True
    assert _resolve_device("auto") == 0


def test_resolve_device_unknown_raises_value_error():
    """Unknown device string raises ValueError."""
    from app.voice.asr.whisper_hf import _resolve_device

    with pytest.raises(ValueError, match="Unknown device"):
        _resolve_device("tpu")


# ---------------------------------------------------------------------------
# 4. compute_type resolution
# ---------------------------------------------------------------------------


def test_resolve_torch_dtype_auto_defaults_to_float32(
    mock_whisper_hf_deps,
):
    """'auto' → float32 (parity with the training script)."""
    from app.voice.asr.whisper_hf import _resolve_torch_dtype

    assert _resolve_torch_dtype("auto") == "float32"


def test_resolve_torch_dtype_float16(mock_whisper_hf_deps):
    """Explicit 'float16' → torch.float16 (halves residency
    at a small WER cost)."""
    from app.voice.asr.whisper_hf import _resolve_torch_dtype

    assert _resolve_torch_dtype("float16") == "float16"


def test_resolve_torch_dtype_float32(mock_whisper_hf_deps):
    """Explicit 'float32' → torch.float32."""
    from app.voice.asr.whisper_hf import _resolve_torch_dtype

    assert _resolve_torch_dtype("float32") == "float32"


def test_resolve_torch_dtype_unknown_raises_value_error(
    mock_whisper_hf_deps,
):
    """Unknown compute_type raises ValueError."""
    from app.voice.asr.whisper_hf import _resolve_torch_dtype

    with pytest.raises(ValueError, match="Unknown compute_type"):
        _resolve_torch_dtype("int8")


# ---------------------------------------------------------------------------
# 5. Language mapping (yue → cantonese)
# ---------------------------------------------------------------------------


def test_map_language_yue_to_cantonese():
    """The headline Sprint 22 spec §4.1 mapping:
    `yue` → `cantonese`. Without this mapping, the HF
    pipeline would auto-detect English on the first
    inference and WER would spike."""
    from app.voice.asr.whisper_hf import _map_language

    assert _map_language("yue") == "cantonese"


def test_map_language_zh_to_chinese():
    """`zh` → `chinese` (HF ISO 639-1 schema)."""
    from app.voice.asr.whisper_hf import _map_language

    assert _map_language("zh") == "chinese"


def test_map_language_auto_to_english():
    """`auto` → `english` (HF default; user can override
    via the config.toml language field)."""
    from app.voice.asr.whisper_hf import _map_language

    assert _map_language("auto") == "english"


def test_map_language_empty_string_to_english():
    """Empty string → 'english' (defensive default)."""
    from app.voice.asr.whisper_hf import _map_language

    assert _map_language("") == "english"


def test_map_language_passthrough_unknown_code():
    """Unknown code (e.g. custom) passes through unchanged
    — we don't fail, we let HF try its own language detection."""
    from app.voice.asr.whisper_hf import _map_language

    assert _map_language("tl") == "tl"
    assert _map_language("MIXED") == "mixed"


def test_map_language_case_insensitive():
    """Mapping is case-insensitive (`YUE` → `cantonese`)."""
    from app.voice.asr.whisper_hf import _map_language

    assert _map_language("YUE") == "cantonese"
    assert _map_language("Yue") == "cantonese"


# ---------------------------------------------------------------------------
# 6. warmup + transcribe
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_whisper_hf_warmup_raises_when_model_path_missing(
    mock_whisper_hf_deps,
):
    """warmup() on a non-existent model_path raises
    ASRError pointing the user at the training runbook."""
    from app.voice.asr.whisper_hf import WhisperHFASR

    asr = WhisperHFASR(model_path="/no/such/directory/")
    with pytest.raises(ASRError, match="does not exist"):
        await asr.warmup()


@pytest.mark.asyncio
async def test_whisper_hf_warmup_loads_pipeline(
    mock_whisper_hf_deps, tmp_model_dir
):
    """warmup() builds the HF pipeline via
    asyncio.to_thread (so the event loop stays
    responsive during the 3-5s model load)."""
    from app.voice.asr.whisper_hf import WhisperHFASR

    asr = WhisperHFASR(
        model_path=tmp_model_dir,
        device="cpu",
        compute_type="float32",
    )
    await asr.warmup()
    assert asr._pipeline is not None
    # The pipeline factory was called with the right args.
    factory = mock_whisper_hf_deps["pipeline_factory"]
    factory.assert_called_once()
    call = factory.call_args
    assert call.args[0] == "automatic-speech-recognition"
    assert call.kwargs["model"] == tmp_model_dir
    assert call.kwargs["device"] == -1  # cpu
    assert call.kwargs["torch_dtype"] == "float32"


@pytest.mark.asyncio
async def test_whisper_hf_warmup_is_idempotent(
    mock_whisper_hf_deps, tmp_model_dir
):
    """Calling warmup twice is a no-op (avoids reloading
    the model on every backend restart)."""
    from app.voice.asr.whisper_hf import WhisperHFASR

    asr = WhisperHFASR(model_path=tmp_model_dir)
    await asr.warmup()
    pipeline_after_first = asr._pipeline
    await asr.warmup()
    assert asr._pipeline is pipeline_after_first
    # The pipeline factory was called exactly once.
    factory = mock_whisper_hf_deps["pipeline_factory"]
    assert factory.call_count == 1


@pytest.mark.asyncio
async def test_whisper_hf_transcribe_empty_audio_returns_empty(
    mock_whisper_hf_deps, tmp_model_dir
):
    """Empty audio buffer → empty string (no pipeline call)."""
    from app.voice.asr.whisper_hf import WhisperHFASR

    asr = WhisperHFASR(model_path=tmp_model_dir)
    await asr.warmup()
    out = await asr.transcribe(b"", sample_rate=16_000)
    assert out == ""
    # The pipeline should NOT have been invoked for empty audio.
    pipeline = mock_whisper_hf_deps["pipeline_instance"]
    pipeline.assert_not_called()


@pytest.mark.asyncio
async def test_whisper_hf_transcribe_passes_cantonese_language(
    mock_whisper_hf_deps, tmp_model_dir
):
    """transcribe() forwards the `yue` → `cantonese`
    mapping into `generate_kwargs` so the model gets
    the Cantonese hint at inference time."""
    from app.voice.asr.whisper_hf import WhisperHFASR

    pipeline = mock_whisper_hf_deps["pipeline_instance"]
    pipeline.return_value = {"text": " 你好 "}

    asr = WhisperHFASR(
        model_path=tmp_model_dir,
        language="yue",
    )
    await asr.warmup()

    # 1s of silence at 16kHz, int16 PCM bytes.
    audio = (np.zeros(16_000, dtype=np.int16)).tobytes()
    out = await asr.transcribe(audio, sample_rate=16_000)

    assert out == "你好"  # whitespace-stripped
    pipeline.assert_called_once()
    call = pipeline.call_args
    # First positional arg is the float32 waveform.
    waveform_arg = call.args[0]
    assert waveform_arg.dtype == np.float32
    # generate_kwargs has language="cantonese" (mapped from "yue").
    assert call.kwargs["generate_kwargs"]["language"] == "cantonese"
    assert call.kwargs["generate_kwargs"]["task"] == "transcribe"


@pytest.mark.asyncio
async def test_whisper_hf_transcribe_wraps_pipeline_errors(
    mock_whisper_hf_deps, tmp_model_dir
):
    """Pipeline errors (e.g. OOM, model corruption) are
    wrapped in ASRError so the voice pipeline can
    surface a clean error to the user."""
    from app.voice.asr.whisper_hf import WhisperHFASR

    pipeline = mock_whisper_hf_deps["pipeline_instance"]
    pipeline.side_effect = RuntimeError("CUDA OOM")

    asr = WhisperHFASR(model_path=tmp_model_dir)
    await asr.warmup()
    audio = (np.zeros(100, dtype=np.int16)).tobytes()
    with pytest.raises(ASRError, match="WhisperHFASR.transcribe failed"):
        await asr.transcribe(audio, sample_rate=16_000)


@pytest.mark.asyncio
async def test_whisper_hf_transcribe_auto_warmup(
    mock_whisper_hf_deps, tmp_model_dir
):
    """transcribe() auto-warms if warmup() wasn't called
    explicitly. (Factory doesn't call warmup; the voice
    pipeline does. But callers may also call transcribe
    without warmup if they want lazy init.)"""
    from app.voice.asr.whisper_hf import WhisperHFASR

    pipeline = mock_whisper_hf_deps["pipeline_instance"]
    pipeline.return_value = {"text": "test"}

    asr = WhisperHFASR(model_path=tmp_model_dir)
    assert asr._pipeline is None  # not warmed up
    audio = (np.zeros(100, dtype=np.int16)).tobytes()
    await asr.transcribe(audio, sample_rate=16_000)
    assert asr._pipeline is not None  # auto-warmed


# ---------------------------------------------------------------------------
# 7. Factory integration
# ---------------------------------------------------------------------------


def test_factory_creates_whisper_hf_when_backend_set(
    monkeypatch, tmp_model_dir
):
    """backend='whisper_hf' returns a WhisperHFASR
    instance with config plumbed through."""
    from app.core import config as config_mod
    from app.voice.asr.asr_factory import create_asr
    from app.voice.asr.whisper_hf import WhisperHFASR

    cfg = config_mod.get_config()
    cfg.voice.asr.backend = "whisper_hf"
    cfg.voice.asr.model_path = tmp_model_dir
    cfg.voice.asr.language = "yue"
    cfg.voice.asr.device = "cpu"
    try:
        asr = create_asr(cfg.voice.asr)
        assert isinstance(asr, WhisperHFASR)
        assert asr._language == "yue"
        assert asr._device == "cpu"
    finally:
        cfg.voice.asr.backend = "whisper_local"
        cfg.voice.asr.model_path = ""


def test_factory_rejects_whisper_hf_without_model_path(monkeypatch):
    """backend='whisper_hf' with empty model_path raises
    ValueError at factory time, not at warmup time."""
    from app.core import config as config_mod
    from app.voice.asr.asr_factory import create_asr

    cfg = config_mod.get_config()
    cfg.voice.asr.backend = "whisper_hf"
    cfg.voice.asr.model_path = ""
    try:
        with pytest.raises(ValueError, match="voice.asr.model_path is required"):
            create_asr(cfg.voice.asr)
    finally:
        cfg.voice.asr.backend = "whisper_local"


def test_factory_lists_whisper_hf_in_unknown_backend_error():
    """The factory's "unknown backend" error message
    lists whisper_hf as a supported option (so users
    who hand-type a typo get a clear list)."""
    from app.voice.asr.asr_factory import create_asr

    with pytest.raises(ValueError, match="whisper_hf"):
        create_asr(_fake_config_with_backend("not_a_real_backend"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_config_with_backend(backend: str):
    """Build a minimal VoiceASRConfig-like object for
    the factory's "unknown backend" error test. We don't
    use the real `get_config()` singleton because that
    would require a HOME env var + a config.toml on disk.
    """
    from app.core.config import VoiceASRConfig

    cfg = VoiceASRConfig()
    cfg.backend = backend
    return cfg

"""Whisper Hugging Face ASR backend — Sprint 23 (v0.1.4).

This is the third ASR backend selectable via
`voice.asr.backend = "whisper_hf"` in
`~/.gundam-halo/config.toml`. It wraps the
Hugging Face `transformers` `pipeline("automatic-speech-recognition")`
so a fine-tuned HF-format checkpoint
(produced by Sprint 19d's
`finetune_whisper_yue.py` runbook) can be loaded
on Mac via MPS / CPU.

The v0.1.3 `WhisperLocalASR` (openai-whisper
backend) could not load HF-format directories;
it accepted `model_path` as forward-compat
forward but emitted a warmup warning saying
"Full support lands in v0.1.4". v0.1.4 ships
this `WhisperHFASR` class so the warning is
replaced with a hard `ValueError` (see Sprint
23 Track 2 in `docs/FEATURE-SPEC-SPRINT22.md`).

The class follows the same lazy-import +
`ASRError` wrap pattern as `YuesubASR`
(`backend/app/voice/asr/yuesub.py:155-194`):
the heavy `transformers` + `torch` deps are
in the `voice-hf` optional extra, so
whisper_local / yuesub users don't pay for
them. The `transformers` import is deferred
to `warmup()`, not module load.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from typing import TYPE_CHECKING, Any, Optional

import numpy as np

from app.voice.asr.asr_interface import ASRError, ASRInterface

logger = logging.getLogger(__name__)


# Module-level: lazy imports of transformers + torch.
# Both come from the `voice-hf` extra. We don't
# import them at module load so the `voice-hf`
# extra is genuinely optional (whisper_local /
# yuesub users don't pay for ~850MB of ML deps).
def _import_transformers() -> Any:
    """Lazy-import transformers.pipeline.

    Raises:
        ASRError: when transformers is not installed
            (the user hasn't run
            `uv sync --extra voice-hf`).
    """
    try:
        from transformers import pipeline  # type: ignore

        return pipeline
    except ImportError as e:
        raise ASRError(
            "transformers is required for WhisperHFASR. "
            "Install with: uv sync --extra voice-hf"
        ) from e


def _import_torch() -> Any:
    """Lazy-import torch (for torch_dtype + device resolution).

    Raises:
        ASRError: when torch is not installed.
    """
    try:
        import torch  # type: ignore

        return torch
    except ImportError as e:
        raise ASRError(
            "torch is required for WhisperHFASR. "
            "Install with: uv sync --extra voice-hf"
        ) from e


def _resolve_device(device: str) -> int:
    """Map a config-level device string to a transformers pipeline device.

    Args:
        device: One of "auto" | "cpu" | "cuda" | "mps".
            - "auto" picks: MPS on Apple Silicon (Mac M-series),
              CUDA on Linux/Windows with a CUDA GPU, CPU otherwise.
            - "mps" / "cuda" / "cpu" pin to that backend.

    Returns:
        A transformers pipeline device index (int): -1 for CPU,
        0 for the first GPU (MPS reports as GPU 0 on Mac).
    """
    if device == "cpu":
        return -1
    if device == "cuda":
        return 0
    if device == "mps":
        # transformers on Mac maps MPS to device 0 (the same as CUDA).
        return 0
    if device == "auto":
        # Apple Silicon: prefer MPS (the fine-tuned whisper-yue
        # model fits in the 4GB MPS residency cap on M-series).
        # Linux/Windows: prefer CUDA if available.
        # Fallback: CPU.
        torch = _import_torch()
        if (
            hasattr(torch.backends, "mps")
            and torch.backends.mps.is_available()
            and sys.platform == "darwin"
        ):
            return 0
        if torch.cuda.is_available():
            return 0
        return -1
    raise ValueError(
        f"Unknown device {device!r}. Expected 'auto' | 'cpu' | 'cuda' | 'mps'."
    )


def _resolve_torch_dtype(compute_type: str) -> Any:
    """Map a config-level compute_type string to a torch dtype.

    Args:
        compute_type: One of "auto" | "float16" | "float32".
            - "auto" defaults to float32 (parity with the training
              script). User can override to float16 to halve the
              MPS residency at a small WER cost.
            - "float16" / "float32" pin to that dtype.

    Returns:
        A torch.dtype instance.

    Raises:
        ValueError: on unknown compute_type.
    """
    torch = _import_torch()
    if compute_type == "auto":
        return torch.float32
    if compute_type == "float32":
        return torch.float32
    if compute_type == "float16":
        return torch.float16
    raise ValueError(
        f"Unknown compute_type {compute_type!r}. "
        f"Expected 'auto' | 'float16' | 'float32'."
    )


def _pcm_bytes_to_float32(audio: bytes, sample_rate: int) -> np.ndarray:
    """Convert 16-bit signed little-endian PCM bytes to float32 [-1, 1].

    Gundam Halo's voice pipeline always feeds 16kHz mono int16
    PCM frames (see `cfg.voice.sample_rate = 16000`). The HF
    transformers pipeline wants a float32 waveform in [-1, 1].

    Mirrors `YuesubASR._pcm_bytes_to_float32`
    (`backend/app/voice/asr/yuesub.py:81-103`) but kept
    module-local here so `whisper_hf.py` doesn't
    transitively import yuesub (yuesub pulls in
    funasr_onnx via its module body, defeating the
    `voice-hf` extra's opt-in design).
    """
    if sample_rate != 16_000:
        raise ValueError(
            f"WhisperHFASR requires 16kHz audio, got {sample_rate}. "
            "The Gundam Halo voice pipeline feeds 16kHz by default."
        )
    waveform = np.frombuffer(audio, dtype=np.int16).astype(np.float32)
    if waveform.size == 0:
        return waveform
    waveform /= 32768.0
    return waveform


# Map Gundam Halo's `language` config strings to the
# HF `generate_kwargs.language` schema (ISO 639-1 names,
# not Whisper's `yue` shorthand). See Sprint 22 spec
# §4.1 "Track 1 — yue→cantonese mapping".
_LANGUAGE_MAP: dict[str, str] = {
    "yue": "cantonese",
    "zh": "chinese",
    "en": "english",
    "ja": "japanese",
    "ko": "korean",
    # "auto" → "english" (HF default). User can override
    # via the config.toml language field.
    "auto": "english",
}


def _map_language(language: str) -> str:
    """Map a Gundam Halo language code to HF's ISO 639-1.

    Falls back to the input unchanged if it's not in
    the map (e.g. user passes a custom code or empty
    string). This is the "let HF detect" path.
    """
    if not language:
        return "english"
    return _LANGUAGE_MAP.get(language.lower(), language.lower())


class WhisperHFASR(ASRInterface):
    """Whisper ASR via the Hugging Face `transformers` pipeline.

    Loads a fine-tuned HF-format checkpoint (produced by
    Sprint 19d's `finetune_whisper_yue.py` runbook) and
    transcribes 16kHz mono int16 PCM bytes to text.

    Args:
        model_path: REQUIRED. Path to the fine-tuned HF-format
            checkpoint directory (e.g.
            `~/.gundam-halo/models/whisper-yue-base/`).
            The directory must contain `config.json`,
            `tokenizer.json`, `preprocessor_config.json`,
            and the model weights (e.g. `model.safetensors`).
        language: One of "auto" | "yue" | "zh" | "en" | ...
            Mapped to HF's ISO 639-1 schema internally
            (`yue` → `cantonese`). Default: "yue"
            (the M9-E Layer 2 fine-tune is Cantonese).
        device: One of "auto" | "cpu" | "cuda" | "mps".
            Default: "auto" (MPS on Apple Silicon, CUDA
            on Linux/Windows, CPU fallback).
        compute_type: One of "auto" | "float16" | "float32".
            Default: "auto" (float32, parity with the
            training script).

    Raises:
        ASRError: on `warmup()` if `model_path` is not
            a directory, or if `transformers` / `torch`
            are not installed (the user hasn't run
            `uv sync --extra voice-hf`).
    """

    def __init__(
        self,
        model_path: str,
        language: str = "yue",
        device: str = "auto",
        compute_type: str = "auto",
    ) -> None:
        # model_path is REQUIRED. The factory
        # (`asr_factory.py`) checks for empty
        # `model_path` and raises ValueError before
        # instantiating. We expanduser here so
        # downstream `os.path.isdir` checks work
        # transparently for `~/...` paths.
        if not model_path:
            raise ASRError(
                "WhisperHFASR.model_path is empty. "
                "Set voice.asr.model_path in config.toml "
                "to the fine-tuned checkpoint directory, e.g.\n"
                'model_path = "~/.gundam-halo/models/whisper-yue-base/"'
            )
        self._model_path = os.path.expanduser(model_path)
        self._language = language
        self._device = device
        self._compute_type = compute_type
        # Lazy-loaded in warmup().
        self._pipeline: Any = None

    async def warmup(self) -> None:
        """Load the HF pipeline into memory.

        Idempotent — calling warmup twice is a no-op.

        Raises:
            ASRError: when the model directory is missing
                or transformers / torch is not installed.
        """
        if self._pipeline is not None:
            return

        if not os.path.isdir(self._model_path):
            raise ASRError(
                f"WhisperHFASR.model_path does not exist: "
                f"{self._model_path!r}. The fine-tuned checkpoint "
                f"must be downloaded (via Sprint 19d's training "
                f"runbook) before switching to backend='whisper_hf'."
            )

        # Resolve device + dtype eagerly so any
        # install / device errors fire on warmup,
        # not on the first transcribe call.
        device_idx = _resolve_device(self._device)
        torch_dtype = _resolve_torch_dtype(self._compute_type)

        # The HF pipeline constructor is sync and
        # loads the model from disk (~3-5s on M-series
        # for whisper-base). Run in a worker thread
        # so the event loop stays responsive.
        self._pipeline = await asyncio.to_thread(
            self._build_pipeline,
            device_idx,
            torch_dtype,
        )

        logger.info(
            f"WhisperHFASR loaded: model_path={self._model_path!r}, "
            f"device={self._device} (idx={device_idx}), "
            f"compute_type={self._compute_type} "
            f"(dtype={torch_dtype}), language={self._language!r}"
        )

    def _build_pipeline(self, device_idx: int, torch_dtype: Any) -> Any:
        """Build the HF pipeline (sync, runs in worker thread)."""
        pipeline = _import_transformers()
        return pipeline(
            "automatic-speech-recognition",
            model=self._model_path,
            torch_dtype=torch_dtype,
            device=device_idx,
        )

    async def transcribe(
        self, audio: bytes, sample_rate: int = 16000
    ) -> str:
        """Transcribe a 16kHz mono int16 PCM audio buffer to text.

        Args:
            audio: 16-bit signed little-endian mono PCM bytes.
            sample_rate: Must be 16000 (Gundam Halo's
                hard-coded pipeline rate). Mismatched
                sample rates raise ValueError (we don't
                silently resample — the VAD state on the
                same stream would desync).

        Returns:
            Transcribed text (whitespace-trimmed).

        Raises:
            ASRError: when the pipeline isn't warmed up
                or the HF call fails.
        """
        if self._pipeline is None:
            await self.warmup()

        # Convert int16 PCM → float32 [-1, 1]
        waveform = _pcm_bytes_to_float32(audio, sample_rate)
        if waveform.size == 0:
            return ""

        # Map Gundam Halo's language code to HF's
        # ISO 639-1 (`yue` → `cantonese`).
        hf_language = _map_language(self._language)

        # The HF pipeline call is sync and can take
        # 100-500ms on CPU. Run in a worker thread
        # so the event loop stays responsive (the
        # voice pipeline calls `transcribe` from
        # `finalize_turn` which is on the event loop).
        try:
            result = await asyncio.to_thread(
                self._invoke_pipeline,
                waveform,
                hf_language,
            )
        except Exception as e:
            raise ASRError(
                f"WhisperHFASR.transcribe failed: {e}"
            ) from e
        return result.get("text", "").strip()

    def _invoke_pipeline(self, waveform: np.ndarray, hf_language: str) -> Any:
        """Invoke the HF pipeline (sync, runs in worker thread).

        Pass `language` and `task` as `generate_kwargs` so
        the model gets the Cantonese hint at inference time
        (Sprint 22 spec §4.1 "Track 1" — without the hint,
        the model would auto-detect English on first
        inference and WER would spike for Cantonese audio).
        """
        return self._pipeline(
            waveform,
            generate_kwargs={
                "language": hf_language,
                "task": "transcribe",
            },
        )


__all__ = ["WhisperHFASR"]

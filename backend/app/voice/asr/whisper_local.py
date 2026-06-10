"""Local Whisper ASR — uses the `openai-whisper` Python package.

Model sizes: tiny (39M) | base (74M) | small (244M) | medium (769M) | large (1.5G)
For v1 we default to `base` — good Cantonese / English / Mandarin coverage
at ~75MB download and fast inference on Apple Silicon (Metal backend).

On first call, `whisper` downloads the model to `~/.cache/whisper/`.
The `device` and `compute_type` fields are passed through to whisper's
`transcribe` function.

Why openai-whisper over whisper.cpp in v1:
- One less binary dependency
- PyTorch handles MPS/CPU selection automatically
- The Python API is enough for our throughput (1-2 turns/sec max)
M2+ can swap to whisper.cpp via the same interface for lower latency.

M9-E Layer 2 (v0.1.3): the `model_path` field is accepted in the
constructor for forward-compat with the upcoming HF-transformers
backend. In this v0.1.x line, `WhisperLocalASR` still uses the
`openai-whisper` inference path, which only understands size names
or `.pt` files — it cannot load a Hugging Face format checkpoint
directory. A `model_path` directory is detected at warmup and a
clear warning is logged; the field will be fully wired in v0.1.4
when the HF backend lands (see docs/tickets/M9-E.md).
"""

from __future__ import annotations

import logging
import os
import tempfile
import wave

from app.voice.asr.asr_interface import ASRError, ASRInterface

logger = logging.getLogger(__name__)

# Default cache dir for whisper model downloads
_DEFAULT_WHISPER_CACHE = os.path.expanduser("~/.cache/whisper")


class WhisperLocalASR(ASRInterface):
    """Local Whisper ASR via the `openai-whisper` package."""

    def __init__(
        self,
        model_size: str = "base",
        model_path: str = "",  # M9-E Layer 2: HF-format dir, wired in v0.1.4
        language: str | None = None,  # None = auto-detect
        device: str = "auto",  # auto|cpu|cuda|mps
        compute_type: str = "auto",  # auto|int8|float16|float32
    ) -> None:
        self._model_size = model_size
        self._model_path = model_path
        self._language = None if language in (None, "", "auto") else language
        self._device = self._resolve_device(device)
        self._compute_type = compute_type
        self._model = None  # loaded on warmup

    def _resolve_device(self, device: str) -> str:
        """Map 'auto' to the best available device for this platform."""
        if device != "auto":
            return device
        try:
            import torch

            if torch.backends.mps.is_available():
                return "mps"  # Apple Silicon Metal
            if torch.cuda.is_available():
                return "cuda"
        except ImportError:
            pass
        return "cpu"

    async def warmup(self) -> None:
        """Load Whisper model into memory."""
        if self._model is not None:
            return

        # M9-E Layer 2 forward-compat: if a model_path is set, surface
        # the gap so the operator knows the v0.1.x line can't load a
        # Hugging Face format directory yet. v0.1.4 will replace this
        # backend with a HF-pipeline implementation.
        if self._model_path:
            expanded = os.path.expanduser(self._model_path)
            if os.path.isdir(expanded):
                logger.warning(
                    f"voice.asr.model_path={self._model_path!r} is set "
                    f"but WhisperLocalASR (openai-whisper backend) cannot "
                    f"load HF-format directories. Falling back to "
                    f"model_size={self._model_size!r}. Full support "
                    f"lands in v0.1.4 (see docs/tickets/M9-E.md)."
                )
            else:
                logger.warning(
                    f"voice.asr.model_path={self._model_path!r} does not "
                    f"exist on disk. Falling back to "
                    f"model_size={self._model_size!r}."
                )

        try:
            import whisper  # type: ignore
        except ImportError as e:  # pragma: no cover
            raise ASRError(
                "openai-whisper is required for WhisperLocalASR. "
                "Install with: uv add openai-whisper"
            ) from e

        # Ensure cache dir exists
        os.makedirs(_DEFAULT_WHISPER_CACHE, exist_ok=True)

        logger.info(
            f"Loading Whisper {self._model_size} (device={self._device})"
        )
        # `download_root` controls where whisper stores the .pt file
        self._model = whisper.load_model(
            self._model_size,
            device=self._device,
            download_root=_DEFAULT_WHISPER_CACHE,
        )
        logger.info("Whisper ready")

    async def transcribe(
        self, audio: bytes, sample_rate: int = 16000
    ) -> str:
        """Transcribe PCM audio bytes via whisper.

        Whisper needs a file path or numpy array. We wrap the bytes
        in a temp .wav file because whisper's `transcribe` will use
        ffmpeg to decode it; passing numpy directly is also possible
        but the file path approach is more battle-tested.

        Returns whitespace-trimmed text.
        """
        if self._model is None:
            raise ASRError("WhisperLocalASR.warmup() must be called first")

        if sample_rate != 16000:
            # Whisper auto-resamples to 16kHz, but we want to be explicit
            # so the temp file matches what whisper expects.
            raise ValueError(
                f"WhisperLocalASR requires 16kHz audio, got {sample_rate}"
            )

        # Write PCM bytes to a temp .wav file
        with tempfile.NamedTemporaryFile(
            suffix=".wav", delete=False
        ) as tmp:
            try:
                with wave.open(tmp.name, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)  # 16-bit
                    wf.setframerate(sample_rate)
                    wf.writeframes(audio)
                tmp_path = tmp.name
            except Exception:
                # Clean up on wave-write failure
                try:
                    os.unlink(tmp.name)
                except OSError:
                    pass
                raise

        try:

            logger.debug(
                f"Transcribing {len(audio)} bytes "
                f"({len(audio) / 2 / sample_rate:.2f}s)"
            )
            result = self._model.transcribe(
                tmp_path,
                language=self._language,
                fp16=(self._device == "mps" or self._device == "cuda"),
                verbose=None,  # suppress whisper's stdout logging
            )
            text = (result.get("text") or "").strip()
            logger.info(f"ASR result: {text!r}")
            return text
        except Exception as e:
            logger.error(f"Whisper transcription failed: {e}")
            raise ASRError(f"Whisper failed: {e}") from e
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


__all__ = ["WhisperLocalASR"]

"""Silero VAD v5 implementation.

Port of the pattern from Open-LLM-VTuber's `vad/silero.py` — same ONNX
model, same threshold defaults, same 16kHz mono PCM input format.

Differences from upstream:
- We don't ship a model downloader in M1; user must drop the ONNX file
  at the configured path. (We'll add auto-download in a follow-up.)
- We expose only the synchronous `process_frame` API; no streaming
  generator. The pipeline handles frame orchestration.

References:
- Silero VAD: https://github.com/snakers4/silero-vad
- Open-LLM-VTuber pattern: ~150 LOC, MIT

Backend dispatch:
- `.onnx` → onnxruntime (legacy default; the v5 ONNX file at
  `https://github.com/snakers4/silero-vad/raw/master/src/silero_vad/data/silero_vad.onnx`
  is corrupted as of 2024-06, so we prefer the bundled `.jit`)
- `.jit`/`.pt` → torch.jit (the actual TorchScript model from
  `silero-vad` PyPI; the only currently-valid V5 model)
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path

import numpy as np

from app.voice.vad.vad_interface import VADEvent, VADInterface
from app.core.registry import register_vad

logger = logging.getLogger(__name__)


class SileroVADLoadError(RuntimeError):
    """Raised when the Silero VAD model cannot be loaded."""


@register_vad("silero")
class SileroVAD(VADInterface):
    """Silero VAD v5 — runs locally on CPU.

    Default thresholds match Open-LLM-VTuber defaults (0.5 start, 0.3 end).
    Frame is 16-bit signed PCM mono at 16kHz; Silero expects int16 numpy.

    Backend is selected from the model file extension:
      * `.onnx` → onnxruntime (preferred if the ONNX file is known-good)
      * `.jit` / `.pt` → torch.jit (current PyPI-bundled V5 model)
    """

    def __init__(self, model_path: str | Path | None = None) -> None:
        self._model_path = Path(os.path.expanduser(model_path)) if model_path else None
        self._backend: str = ""  # "onnx" | "torch"
        self._session = None  # ONNX Runtime InferenceSession OR torch.jit.ScriptModule
        self._vad_iterator = None  # VADIterator wrapper (TorchScript path)
        self._state: np.ndarray | None = None  # LSTM state (N, 128) — ONNX path only
        self._context_size = 64  # Silero VAD v5 needs 64 samples of context
        self._context: np.ndarray | None = None  # rolling context — ONNX path only
        self._warmed_up = False

    async def warmup(self) -> None:
        """Load the model. Lazy: only loads on first call."""
        if self._warmed_up:
            return

        if self._model_path is None or not self._model_path.exists():
            raise SileroVADLoadError(
                f"Silero VAD model not found at {self._model_path}. "
                "See ARCHITECTURE §15.10 for model_path config. "
                "(Auto-download coming in follow-up.)"
            )

        ext = self._model_path.suffix.lower()
        if ext in (".jit", ".pt"):
            self._backend = "torch"
            try:
                import torch  # type: ignore
                from silero_vad import VADIterator  # type: ignore
            except ImportError as e:  # pragma: no cover
                raise SileroVADLoadError(
                    "torch + silero-vad are required for TorchScript SileroVAD. "
                    "Install with: uv add torch silero-vad"
                ) from e
            logger.info(f"Loading Silero VAD (TorchScript) from {self._model_path}")
            self._session = torch.jit.load(
                str(self._model_path), map_location="cpu"
            )
            self._session.eval()
            # VADIterator wraps the JIT model with internal state + rolling context.
            # We own one iterator per VAD instance and reset it on `reset()`.
            self._vad_iterator = VADIterator(self._session)
        elif ext == ".onnx":
            self._backend = "onnx"
            try:
                import onnxruntime as ort  # type: ignore
            except ImportError as e:  # pragma: no cover
                raise SileroVADLoadError(
                    "onnxruntime is required for ONNX SileroVAD. "
                    "Install with: uv add onnxruntime"
                ) from e
            logger.info(f"Loading Silero VAD (ONNX) from {self._model_path}")
            sess_options = ort.SessionOptions()
            sess_options.inter_op_num_threads = 1
            sess_options.intra_op_num_threads = 1
            self._session = ort.InferenceSession(
                str(self._model_path),
                sess_options=sess_options,
                providers=["CPUExecutionProvider"],
            )
        else:
            raise SileroVADLoadError(
                f"Unsupported Silero VAD model extension: {ext!r}. "
                "Use .onnx, .jit, or .pt"
            )

        self.reset()
        self._warmed_up = True
        logger.info(f"Silero VAD ready (backend={self._backend})")

    def reset(self) -> None:
        """Reset internal LSTM state and audio context buffer."""
        # State shape: (2, batch=1, 128) for v5
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._context = np.zeros((0,), dtype=np.int16)
        if self._vad_iterator is not None:
            self._vad_iterator.reset_states()

    def process_frame(
        self, audio_frame: bytes, sample_rate: int = 16000
    ) -> VADEvent:
        """Run one frame through Silero VAD.

        Silero v5 requires exactly 512 samples per inference call at 16kHz.
        We split a 250ms frame (4000 samples at 16kHz) into 512-sample
        chunks, with a 64-sample rolling context carried across calls.
        """
        if not self._warmed_up:
            raise RuntimeError("SileroVAD.warmup() must be called first")

        if sample_rate != 16000:
            # Silero VAD v5 is hardcoded to 16kHz. Resampling is out of M1 scope.
            raise ValueError(
                f"SileroVAD requires 16kHz audio, got {sample_rate}"
            )

        # 16-bit signed PCM → float32 in [-1, 1]
        if self._backend == "torch":
            # TorchScript path: VADIterator handles state + context for us.
            # Drive the iterator so it accumulates state across frames, then
            # also call the raw model to extract the speech probability for
            # this frame. The TorchScript model's `forward(x, sr)` returns
            # only the probability (state lives inside the JIT module).
            import torch  # type: ignore
            int16 = np.frombuffer(audio_frame, dtype=np.int16)
            x = torch.from_numpy(int16.astype(np.float32) / 32768.0).reshape(1, -1)
            sr_tensor = torch.tensor(sample_rate, dtype=torch.int64)
            max_prob = 0.0
            chunk_size = 512
            with torch.no_grad():
                for start in range(0, x.shape[1] - chunk_size + 1, chunk_size):
                    chunk = x[:, start:start + chunk_size]
                    # Drive the iterator (updates internal state + context)
                    self._vad_iterator(chunk, sample_rate)
                    # Get probability for this chunk
                    out = self._session(chunk, sr_tensor)
                    p = float(out.flatten()[0].item())
                    if p > max_prob:
                        max_prob = p
            return VADEvent(
                is_speech=max_prob >= 0.5,
                probability=max_prob,
                timestamp_ms=int(time.time() * 1000),
            )

        # ONNX path: manual state + context
        new_samples = np.frombuffer(audio_frame, dtype=np.int16)
        if self._context is not None and len(self._context) > 0:
            samples = np.concatenate([self._context, new_samples])
        else:
            samples = new_samples

        if len(new_samples) >= self._context_size:
            self._context = new_samples[-self._context_size:].copy()
        else:
            self._context = new_samples.copy()

        chunk_size = 512
        max_prob = 0.0
        for start in range(0, len(samples) - chunk_size + 1, chunk_size):
            chunk = samples[start : start + chunk_size].astype(np.float32) / 32768.0
            chunk = chunk.reshape(1, -1)  # (1, 512)
            ort_inputs = {
                "input": chunk,
                "state": self._state,
                "sr": np.array(sample_rate, dtype=np.int64),
            }
            ort_out = self._session.run(None, ort_inputs)
            prob = float(ort_out[0].item())
            self._state = ort_out[1]
            if prob > max_prob:
                max_prob = prob

        return VADEvent(
            is_speech=max_prob >= 0.5,
            probability=max_prob,
            timestamp_ms=int(time.time() * 1000),
        )


__all__ = ["SileroVAD", "SileroVADLoadError"]

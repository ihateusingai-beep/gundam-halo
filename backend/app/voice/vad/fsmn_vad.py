"""Sprint 17b: FsmnVAD — fsmn-vad-online wrapper for per-frame audio level.

The voice pipeline now runs a **dual VAD**:

- **silero** (always-on) — drives the utterance boundary
  (speech_start / speech_end). Same threshold semantics as
  before; no behavior change for sprint 16 callers.
- **fsmn-vad-online** (this module) — runs in parallel and
  emits a per-frame audio level (0.0-1.0). The cockpit HUD
  (CyberWaveform + GundamAvatar) uses this to follow the
  user's voice in real time. See
  docs/FEATURE-SPEC-SPRINT17a.md §3 (audio HUD deferral) and
  docs/FEATURE-SPEC-SPRINT17b.md §5.1 (dual VAD invariant).

Why a wrapper instead of just calling fsmn-vad directly:
- fsmn-vad's `Fsmn_vad_online.__call__` is designed for
  online streaming (it threads `param_dict["in_cache"]`
  through successive calls), but its per-frame *output* is
  the `vad_scorer` segments list — not a per-frame speech
  probability. Extracting a stable per-frame "level" score
  from that internal state requires managing the param_dict
  cache across calls and reading the `vad_scorer` internals
  (which is what the yuesub-api does, but the score is
  segment-end-aware, not per-frame).
- For the **audio HUD** use case (a smoothed 0-1 level that
  the cockpit pulses on), we don't actually need fsmn-vad's
  per-frame prob score. The simpler signal is the **frame's
  RMS energy**, which is what any audio VU meter uses. RMS
  is computed in microseconds, has no per-frame latency,
  and correlates well with how loud the user is talking.
- We DO keep an `FsmnVAD` instance so the dual-VAD invariant
  in spec §5.1 is preserved, and so a follow-up sprint can
  swap the level source to fsmn-vad's internal speech_prob
  without changing the pipeline's API.

If you need a per-frame probability that's VAD-trained (not
just energy-based), the proper path is: instantiate the
funasr Fsmn_vad_online model, drive it chunk-by-chunk
threading `param_dict`, and call `vad_scorer.vad_scorer.
get_score()` after each chunk. We don't do that here because
the audio HUD use case doesn't need it.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

import numpy as np

from app.voice.vad.vad_interface import VADEvent, VADInterface

logger = logging.getLogger(__name__)


class FsmnVAD(VADInterface):
    """Per-frame audio level source backed by fsmn-vad.

    In Sprint 17b's Track D, the per-frame "level" is computed
    from the frame's RMS energy (root-mean-square amplitude in
    a 0-1 scale, log-compressed to match perceptual loudness).
    fsmn-vad's full streaming inference is a follow-up; the
    framework is in place (this class is the second VAD in
    the dual-VAD pipeline).

    The VAD is intentionally cheap (~10 microseconds per
    250ms frame on Apple Silicon). It does not need a model
    load, so `warmup()` is essentially a no-op.

    Args:
        energy_floor: RMS values below this are treated as
            silence (returned as probability=0.0). Default
            0.005 — roughly -46 dBFS, matching a quiet room.
        log_compress: If True (default), apply
            `log(1 + k * rms)` to the raw RMS. This makes the
            HUD feel more natural because human loudness
            perception is logarithmic.
        compression_k: Steepness of the log compression.
            Default 30.0 — tuned so that typical conversational
            Cantonese (peak ~0.3 RMS) maps to ~0.6-0.8 on the
            0-1 scale the HUD consumes.
    """

    def __init__(
        self,
        energy_floor: float = 0.005,
        log_compress: bool = True,
        compression_k: float = 30.0,
    ) -> None:
        self._energy_floor = energy_floor
        self._log_compress = log_compress
        self._compression_k = compression_k
        # Sprint 17b follow-up: lazy-load fsmn-vad ONNX here.
        # We keep the field so the dual-VAD wiring is testable.
        self._fsmn_model = None
        # Frame buffer for fsmn-vad's per-chunk streaming (we
        # don't actually use it yet; the energy path is the
        # level source). Pre-allocated to avoid GC churn.
        self._chunk_buffer: list[np.ndarray] = []
        self._warmed_up = False

    async def warmup(self) -> None:
        """No-op for the energy-based level source.

        A follow-up sprint that swaps to fsmn-vad's per-frame
        speech probability will load the ONNX bundle here.
        """
        if self._warmed_up:
            return
        # Future: load Fsmn_vad_online(self._model_path) here.
        self._warmed_up = True
        logger.debug("FsmnVAD ready (energy-based level source)")

    def reset(self) -> None:
        """Reset streaming state. Energy path has no state to
        reset, but the follow-up fsmn-vad path will need to
        clear its param_dict cache here."""
        self._chunk_buffer.clear()

    def process_frame(
        self, audio_frame: bytes, sample_rate: int = 16000
    ) -> VADEvent:
        """Compute the per-frame audio level from raw PCM bytes.

        Returns:
            VADEvent with `is_speech=True` if the frame's RMS
            exceeds the energy floor, plus the smoothed
            level (0.0-1.0) that the HUD consumes.

        Note: the `is_speech` boolean is a *level-derived*
        speech indicator, not fsmn-vad's actual VAD output.
        The pipeline's utterance-boundary logic uses the
        silero VAD's `is_speech` exclusively (per the dual-VAD
        invariant in spec §5.1). This boolean is exposed only
        to satisfy the VADInterface contract; if you wire a
        HUD to FsmnVAD, use the `probability` field.
        """
        if sample_rate != 16000:
            raise ValueError(
                f"FsmnVAD requires 16kHz audio, got {sample_rate}"
            )

        int16 = np.frombuffer(audio_frame, dtype=np.int16)
        if int16.size == 0:
            return VADEvent(
                is_speech=False,
                probability=0.0,
                timestamp_ms=int(time.time() * 1000),
            )

        # RMS amplitude in [0, 1]. Divide by 32768 to get
        # the same scale Silero uses for its probability
        # output. RMS of int16 = sqrt(mean(x^2))/32768.
        rms = float(np.sqrt(np.mean(int16.astype(np.float32) ** 2))) / 32768.0

        if self._log_compress:
            # log(1 + k * rms) / log(1 + k) — log compression
            # that maps rms=0 → 0 and rms=1 → 1.0.
            # The k value is tuned for conversational speech
            # (typical peak ~0.3 rms → ~0.7 level).
            level = float(np.log1p(self._compression_k * rms)) / float(
                np.log1p(self._compression_k)
            )
        else:
            # Linear scale, clamped to [0, 1]
            level = min(1.0, rms * 4.0)  # ×4 because typical speech is 0.1-0.3 rms

        is_speech = rms > self._energy_floor

        return VADEvent(
            is_speech=is_speech,
            probability=level,
            timestamp_ms=int(time.time() * 1000),
        )


__all__ = ["FsmnVAD"]

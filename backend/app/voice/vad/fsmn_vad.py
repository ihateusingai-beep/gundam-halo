"""Sprint 17b + 19a: FsmnVAD — fsmn-vad-online wrapper for per-frame audio level.

The voice pipeline runs a **dual VAD**:

- **silero** (always-on) — drives the utterance boundary
  (speech_start / speech_end). Same threshold semantics as
  before; no behavior change for sprint 16 callers.
- **fsmn-vad-online** (this module) — runs in parallel and
  emits a per-frame audio level (0.0-1.0). The cockpit HUD
  (CyberWaveform + GundamAvatar) uses this to follow the
  user's voice in real time. See
  docs/FEATURE-SPEC-SPRINT17a.md §3 (audio HUD deferral),
  docs/FEATURE-SPEC-SPRINT17b.md §5.1 (dual-VAD invariant),
  and docs/FEATURE-SPEC-SPRINT19a.md (Sprint 19a — VAD-
  trained level source).

Sprint 19a replaces the Sprint 17b Track D RMS-energy
placeholder with fsmn-vad-online's actual per-frame speech
probability. The mapping is SNR-based (frame loudness vs
rolling noise floor) so the HUD responds to **voice**
rather than just **loud sound** — a TV with no speech
produces a flat wave, a soft-spoken user produces a
healthy pulse.

Backward compat: when `model_dir=None` (the default), the
class falls back to the Sprint 17b energy path so existing
tests keep passing. Production callers pass
`model_dir=cfg.vad.model_path` via the vad_factory.
"""
from __future__ import annotations

import logging
import math
import time
from typing import Optional

import numpy as np

from app.voice.vad.vad_interface import VADEvent, VADInterface
from app.core.registry import register_vad

logger = logging.getLogger(__name__)


# Sentinel SNR level for "no frame data yet" (e.g. before
# the FSMN has accumulated enough audio to compute a
# rolling noise floor). The HUD treats this as silence.
_NO_FRAME_LEVEL = 0.0


@register_vad("fsmn")
class FsmnVAD(VADInterface):
    """Per-frame audio level source backed by fsmn-vad-online.

    Sprint 19a: the level source is now VAD-trained (frame
    SNR, not raw RMS). Sprint 17b's energy path remains as
    a fallback when `model_dir=None` (the default for tests
    that don't ship the fsmn-vad model) and as a safety net
    when the model raises mid-turn.

    The VAD is intentionally cheap when in energy mode (~10
    microseconds per 250ms frame on Apple Silicon) and
    ~30-50ms per frame in model mode on CPU. The pipeline
    rate-limits the `vad.audio_level` WS broadcast to 50ms,
    so the model-mode inference fits comfortably.

    Args:
        model_dir: Path to the funasr fsmn-vad model
            directory (typically `~/.gundam-halo/models/iic/
            speech_fsmn_vad_zh-cn-16k-common-pytorch`).
            If None, falls back to the RMS-energy level
            source (Sprint 17b behavior). If a path is
            provided, the model is **lazy-loaded on first
            `process_frame` call** so the funasr_onnx
            import cost is paid only when actually used.
        energy_floor: RMS values below this are treated as
            silence (returned as probability=0.0) when in
            energy mode. Default 0.005 — roughly -46 dBFS,
            matching a quiet room.
        log_compress: If True (default), apply
            `log(1 + k * rms)` to the raw RMS in energy
            mode. This makes the HUD feel more natural
            because human loudness perception is
            logarithmic.
        compression_k: Steepness of the log compression in
            energy mode. Default 30.0.
    """

    def __init__(
        self,
        model_dir: Optional[str] = None,
        energy_floor: float = 0.005,
        log_compress: bool = True,
        compression_k: float = 30.0,
    ) -> None:
        self._model_dir = model_dir
        # Lazy-loaded on first process_frame call.
        # `_model` is None when running in energy mode or
        # before the first model-mode call.
        self._model = None
        self._energy_floor = energy_floor
        self._log_compress = log_compress
        self._compression_k = compression_k
        # Pre-allocated buffer for the energy path (Sprint
        # 17b kept this for stateful callers).
        self._chunk_buffer: list[np.ndarray] = []
        self._warmed_up = False

    async def warmup(self) -> None:
        """No-op for the energy path. For the model path, it
        sets the `output_frame_probs` flag and pre-allocates
        a clean `frame_probs` list. The actual model
        instantiation is lazy and happens on first
        `process_frame` call.

        We deliberately don't load the ONNX bundle in
        `warmup()` because the funasr_onnx import takes
        ~500ms; we want the voice WS connection to succeed
        quickly even if the model path is enabled. The
        pipeline's existing 50ms rate-limit on
        `vad.audio_level` broadcasts gives us slack to
        load the model on the first frame.
        """
        if self._warmed_up:
            return
        if self._model_dir is not None:
            # Pre-create an empty frame_probs list on the
            # scorer's placeholder. The real scorer is
            # created by _ensure_model_loaded() on first
            # process_frame call. If the model is already
            # loaded (test fixture), reset its state.
            if self._model is not None:
                self._model.vad_scorer.vad_opts.output_frame_probs = True
                self._model.vad_scorer.AllResetDetection()
        self._warmed_up = True
        logger.debug(
            f"FsmnVAD ready (model={'enabled' if self._model_dir else 'energy-only'})"
        )

    def _ensure_model_loaded(self):
        """Lazy-load the fsmn-vad-online model on first use.

        Returns the loaded model, or None if `model_dir` is
        unset (caller falls back to the energy path).

        Raises:
            FileNotFoundError: if `model_dir` is set but the
                directory doesn't exist.
            RuntimeError: if the funasr_onnx import or
                model instantiation fails for any other
                reason.

        The import is deferred to first use so a test that
        instantiates `FsmnVAD(model_dir=None)` never pays
        the ~500ms funasr_onnx import cost.
        """
        if self._model_dir is None:
            return None
        if self._model is None:
            import os
            if not os.path.isdir(self._model_dir):
                raise FileNotFoundError(
                    f"FsmnVAD model_dir does not exist: {self._model_dir}"
                )
            try:
                from funasr_onnx import Fsmn_vad_online
            except ImportError as e:
                raise RuntimeError(
                    f"FsmnVAD requires funasr_onnx for model mode: {e}"
                ) from e
            logger.info(f"Loading fsmn-vad-online from {self._model_dir}")
            self._model = Fsmn_vad_online(
                self._model_dir,
                quantize=True,
                intra_op_num_threads=2,
            )
            # Ask the scorer to retain per-frame speech
            # probabilities so process_frame can read the
            # most recent one. Default in VADXOptions is
            # False to save memory.
            self._model.vad_scorer.vad_opts.output_frame_probs = True
            # Reset the scorer's internal state in case the
            # warmup() pre-allocated placeholders.
            self._model.vad_scorer.AllResetDetection()
        return self._model

    def reset(self) -> None:
        """Reset streaming state for a new turn.

        Energy path: clear the buffer. Model path: reset
        the scorer's internal cache via AllResetDetection
        so a new turn doesn't see stale `data_buf` from
        the previous turn.
        """
        self._chunk_buffer.clear()
        if self._model is not None:
            self._model.vad_scorer.AllResetDetection()

    def _rms_level(self, int16: np.ndarray) -> float:
        """Energy-path level calculation (Sprint 17b).

        Returns a value in [0, 1] for the HUD to consume.
        """
        if int16.size == 0:
            return 0.0
        rms = float(np.sqrt(np.mean(int16.astype(np.float32) ** 2))) / 32768.0
        if self._log_compress:
            level = float(np.log1p(self._compression_k * rms)) / float(
                np.log1p(self._compression_k)
            )
        else:
            level = min(1.0, rms * 4.0)
        return level

    def _snr_level(self) -> float:
        """VAD-path level calculation (Sprint 19a).

        Returns the frame SNR scaled into [0, 1] for the
        HUD. Reads from the scorer's accumulated
        `decibel` list and the rolling `noise_average_decibel`.

        Returns 0.0 if the scorer hasn't accumulated enough
        frames yet (e.g. first chunk of a turn, where
        the noise floor is still settling).
        """
        decibel_list = self._model.vad_scorer.decibel
        if not decibel_list:
            return _NO_FRAME_LEVEL
        last_db = decibel_list[-1]
        noise_db = self._model.vad_scorer.noise_average_decibel
        # SNR in dB. Divide by 20 to scale typical speech
        # (10-20 dB SNR) into the [0, 1] HUD range. A
        # 30 dB SNR shout clamps to 1.0.
        snr = (last_db - noise_db) / 20.0
        return max(0.0, min(1.0, snr))

    def process_frame(
        self, audio_frame: bytes, sample_rate: int = 16000
    ) -> VADEvent:
        """Compute the per-frame audio level from raw PCM bytes.

        VAD-trained path (Sprint 19a): lazy-load
        fsmn-vad-online on first call, drive it chunk-by-
        chunk, and read the frame SNR from the scorer's
        `decibel` and `noise_average_decibel` fields. The
        model state persists across calls (the scorer
        accumulates `data_buf` and rolling noise floor
        internally).

        Energy path (Sprint 17b fallback): compute RMS
        loudness. Used when `model_dir=None` and as a
        safety net when the model raises mid-turn.

        Returns:
            VADEvent with `is_speech=True` if the level
            exceeds 0.5, plus the smoothed level
            (0.0-1.0) that the HUD consumes.

        Note: the `is_speech` boolean is a *level-derived*
        speech indicator, not fsmn-vad's actual VAD state
        machine output. The pipeline's utterance-boundary
        logic uses the silero VAD's `is_speech` exclusively
        (per the dual-VAD invariant in spec §5.1). This
        boolean is exposed only to satisfy the
        VADInterface contract; if you wire a HUD to
        FsmnVAD, use the `probability` field.
        """
        if sample_rate != 16000:
            raise ValueError(
                f"FsmnVAD requires 16kHz audio, got {sample_rate}"
            )

        int16 = np.frombuffer(audio_frame, dtype=np.int16)
        ts_ms = int(time.time() * 1000)

        if int16.size == 0:
            return VADEvent(
                is_speech=False,
                probability=0.0,
                timestamp_ms=ts_ms,
            )

        # Try the VAD-trained path first (Sprint 19a).
        # Falls back to energy on:
        #   1. model_dir=None (energy mode by design)
        #   2. Model load error (FileNotFoundError, ImportError,
        #      ONNX runtime error). The fallback keeps the
        #      cockpit HUD alive even if the model is missing.
        model = None
        try:
            model = self._ensure_model_loaded()
        except Exception as e:
            logger.warning(
                f"FsmnVAD model load failed: {e}; using energy path"
            )

        if model is not None:
            try:
                audio = int16.astype(np.float32) / 32768.0
                _ = model(audio, is_final=False)
                level = self._snr_level()
                # The VAD path's is_speech follows the
                # funasr state machine decision, not a
                # fixed 0.5 threshold on the level. We
                # derive it from the scorer's noise-vs-
                # speech comparison (matches the funasr
                # internal GetFrameState logic).
                is_speech = self._vad_speech_decision()
            except Exception as e:
                # Model failed mid-turn. Log and fall back
                # to energy for this frame only.
                logger.warning(
                    f"fsmn-vad-online error: {e}; falling back to RMS"
                )
                rms = float(np.sqrt(np.mean(int16.astype(np.float32) ** 2))) / 32768.0
                level = self._rms_level(int16)
                is_speech = rms > self._energy_floor
        else:
            rms = float(np.sqrt(np.mean(int16.astype(np.float32) ** 2))) / 32768.0
            level = self._rms_level(int16)
            is_speech = rms > self._energy_floor

        return VADEvent(
            is_speech=is_speech,
            probability=level,
            timestamp_ms=ts_ms,
        )

    def _vad_speech_decision(self) -> bool:
        """VAD-path is_speech (Sprint 19a).

        Mirrors funasr's `E2EVadModel.GetFrameState` decision
        rule: speech is present when the current frame's
        speech posterior exceeds the silence posterior by
        the configured `speech_noise_thres` margin. This is
        what the funasr state machine uses to flip into
        `kFrameStateSpeech`; we replicate the check here so
        the VADInterface's `is_speech` boolean reflects the
        model's actual decision.

        Returns False (silence) when the scorer hasn't
        accumulated enough frames yet.
        """
        probs = self._model.vad_scorer.frame_probs
        if not probs:
            return False
        last = probs[-1]
        speech_post = math.exp(last.speech_prob)
        noise_post = math.exp(last.noise_prob)
        return speech_post >= noise_post + self._model.vad_scorer.speech_noise_thres


__all__ = ["FsmnVAD"]

"""Yuesub Cantonese ASR backend — Sprint 17b.

This is the second ASR backend selectable via
`voice.asr.backend = "yuesub"` in `~/.gundam-halo/config.toml`.
It wraps the `funasr_onnx` SenseVoiceSmall + Fsmn_vad_online
ONNX runtime bindings (lifted from `~/workspace/yuesub-api`'s
`OnnxTranscriber`) and adapts them to Gundam Halo's
`ASRInterface` contract so the rest of the voice pipeline
doesn't know which backend is plugged in.

Why a separate file (vs vendoring OnnxTranscriber.py):
- The ASR backend factory (`asr_factory.create_asr()`) takes
  a `VoiceASRConfig` and returns an `ASRInterface`. The
  yuesub-api `OnnxTranscriber` is a file-based, list-returning
  class that doesn't fit that contract — it expects a path
  to a full audio file and returns a list of
  `TranscribeResult` dataclasses. Gundam Halo's pipeline
  passes a `bytes` buffer of one utterance at a time and
  wants a single string back.
- We keep the yuesub-api repo untouched as a dev reference
  (no Flask/Gradio surface dependency).
- We thread the corrector in via constructor injection
  (Track C wraps the yuesub-api `Corrector` in an async
  adapter and passes it here). The corrector runs after
  ASR per-segment, before wake detection, so corrections
  like "俾" → "畀" are visible to the wake-phrase
  detector.

Model paths (Sprint 17b §5.6 — D5 symlink):
- SenseVoiceSmall ONNX bundle at
  `~/.gundam-halo/models/iic/SenseVoiceSmall/`
  (symlink to `~/workspace/yuesub-api/models/iic/SenseVoiceSmall`)
- Fsmn_vad ONNX bundle at
  `~/.gundam-halo/models/iic/speech_fsmn_vad_zh-cn-16k-common-pytorch/`
  (same symlink)
- denoiser.onnx at `~/.gundam-halo/models/denoiser.onnx`
- hon9kon9ize/bert-large-cantonese (optional, for
  corrector="bert") at `~/.gundam-halo/models/hon9kon9ize/`

Run `bash scripts/setup-yuesub-models.sh` once to create
the symlinks before instantiating this backend.

Why MPS-on-Apple-Silicon for SenseVoice (not GPU):
SenseVoice is a 234M-param ONNX model with a static graph.
ONNX Runtime on Apple Silicon uses CoreMLExecutionProvider
when available, which leverages MPS automatically. We don't
pass `device="mps"` to SenseVoiceSmall because ONNX RT
manages that itself via the `providers` list.
"""
from __future__ import annotations

import logging
import os
import time
from typing import TYPE_CHECKING, Any, List, Literal, Optional, Sequence, Union

import numpy as np

from app.voice.asr.asr_interface import ASRError, ASRInterface
from app.core.registry import register_asr

logger = logging.getLogger(__name__)

# Default model locations (override via constructor). The D5 symlink
# target — `~/.gundam-halo/models/iic` is created by
# `scripts/setup-yuesub-models.sh`.
_DEFAULT_MODEL_ROOT = os.path.expanduser("~/.gundam-halo/models")
_SENSE_VOICE_DIRNAME = "SenseVoiceSmall"
_FSMN_VAD_DIRNAME = "speech_fsmn_vad_zh-cn-16k-common-pytorch"


def _resolve_models_dir() -> str:
    """Return the iic/ subdir under the symlinked model root.

    If the user hasn't run `scripts/setup-yuesub-models.sh`, this
    dir will not exist; we surface a clear error in __init__ rather
    than silently picking a default.
    """
    return os.path.join(_DEFAULT_MODEL_ROOT, "iic")


def _pcm_bytes_to_float32(audio: bytes, sample_rate: int) -> np.ndarray:
    """Convert 16-bit signed little-endian PCM bytes to float32 [-1, 1].

    Gundam Halo's voice pipeline always feeds 16kHz mono int16
    PCM frames (see `cfg.voice.sample_rate = 16000`). The yuesub
    SenseVoice model wants a float32 waveform in [-1, 1].
    """
    if sample_rate != 16_000:
        # The Gundam Halo pipeline hard-codes 16kHz. If a caller
        # passes a different rate, we fail loudly rather than
        # silently resampling (we'd lose alignment with the VAD
        # state that's running on the same stream).
        raise ValueError(
            f"YuesubASR requires 16kHz audio, got {sample_rate}. "
            "The Gundam Halo voice pipeline feeds 16kHz by default."
        )

    # int16 -> float32 / 32768
    waveform = np.frombuffer(audio, dtype=np.int16).astype(np.float32)
    if waveform.size == 0:
        return waveform
    waveform /= 32768.0
    return waveform


def _device_to_providers(device: str) -> List[str]:
    """Map a config-level device string to a funasr_onnx providers list.

    Sprint 17b's `voice.asr.device` config field accepts
    "auto" | "mps" | "cpu". We translate that into the
    ONNX Runtime provider list that funasr_onnx expects.

    Note: Apple Silicon MPS is exposed by ONNX Runtime via the
    CoreMLExecutionProvider, NOT the MPS provider directly.
    `onnxruntime.get_available_providers()` lists what's
    actually available on this machine.
    """
    if device == "auto":
        try:
            import onnxruntime  # type: ignore

            available = onnxruntime.get_available_providers()
            if "CoreMLExecutionProvider" in available:
                return ["CoreMLExecutionProvider", "CPUExecutionProvider"]
            if "CUDAExecutionProvider" in available:
                return ["CUDAExecutionProvider", "CPUExecutionProvider"]
        except ImportError:
            pass
        return ["CPUExecutionProvider"]

    if device == "mps":
        # Apple Silicon. Check whether CoreML EP is actually
        # available; otherwise fall back to CPU with a warning.
        try:
            import onnxruntime  # type: ignore

            if "CoreMLExecutionProvider" in onnxruntime.get_available_providers():
                return ["CoreMLExecutionProvider", "CPUExecutionProvider"]
        except ImportError:
            pass
        logger.warning(
            "voice.asr.device='mps' but onnxruntime has no "
            "CoreMLExecutionProvider — falling back to CPU."
        )
        return ["CPUExecutionProvider"]

    if device == "cpu":
        return ["CPUExecutionProvider"]

    raise ValueError(
        f"Unknown device {device!r}. Expected 'auto' | 'mps' | 'cpu'."
    )


# Lazy import of funasr_onnx (the dependency is in the
# `voice-yuesub` extra — whisper_local users don't have it).
def _import_funasr_onnx():
    try:
        from funasr_onnx import Fsmn_vad_online, SenseVoiceSmall  # type: ignore

        return Fsmn_vad_online, SenseVoiceSmall
    except ImportError as e:  # pragma: no cover
        raise ASRError(
            "funasr_onnx is required for YuesubASR. "
            "Install with: uv sync --extra voice-yuesub"
        ) from e


# Lazy import of the aligner used for token-span alignment.
def _import_aligner():
    try:
        from torchaudio.pipelines import MMS_FA as bundle  # type: ignore

        return bundle
    except ImportError as e:  # pragma: no cover
        raise ASRError(
            "torchaudio is required for YuesubASR (for the "
            "MMS_FA aligner). Install with: uv add torchaudio"
        ) from e


def _import_tokenizer():
    try:
        from funasr_onnx.utils.sentencepiece_tokenizer import (  # type: ignore
            SentencepiecesTokenizer,
        )

        return SentencepiecesTokenizer
    except ImportError as e:  # pragma: no cover
        raise ASRError(
            "funasr_onnx.utils.sentencepiece_tokenizer is required "
            "for YuesubASR. This ships with the funasr_onnx extra."
        ) from e


# Type-only import for the corrector (Track C). Keeps the
# circular import out of runtime: corrector.py imports
# funasr_onnx; if yuesub.py imported corrector at module
# load time, we'd pull in funasr_onnx via the corrector too.
if TYPE_CHECKING:
    from app.voice.corrector.corrector import Corrector  # noqa: F401


@register_asr("yuesub")
class YuesubASR(ASRInterface):
    """Cantonese ASR via the yuesub-api SenseVoiceSmall + Fsmn_vad stack.

    Args:
        model_root: Path to the iic/ directory containing the
            SenseVoiceSmall/ and speech_fsmn_vad_zh-cn-16k-common-pytorch/
            ONNX bundles. Default: `~/.gundam-halo/models/iic` (the
            D5 symlink target).
        language: One of "auto" | "yue" | "zh" | "en". Forwarded to
            SenseVoice's `read_tags(language, textnorm)`. Default "auto".
        device: One of "auto" | "mps" | "cpu". Default "auto" picks
            CoreML EP on macOS, CUDA EP on Linux, CPU otherwise.
        corrector: Optional `Corrector` instance (Track C). When
            provided, the corrector is applied to each segment's text
            before wake detection. When None, raw SenseVoice text is
            returned (still useful for whisper_local fallback testing).
        textnorm: SenseVoice text normalization mode. Default "withitn"
            (inverse text normalization — preserves digits/punct). Set
            to "woitn" for raw transcript.
        offset_in_seconds: Time offset applied to all segment timestamps
            (default -0.25s, matching yuesub-api's default — the VAD
            tends to detect speech_start slightly after the actual start).
        max_length_seconds: Maximum duration of a single ASR segment
            (default 10s, matching yuesub-api). Longer utterances are
            split by fsmn-vad.
    """

    def __init__(
        self,
        model_root: str = _DEFAULT_MODEL_ROOT,
        language: str = "auto",
        device: str = "auto",
        corrector: Optional["Corrector"] = None,
        textnorm: Literal["withitn", "woitn"] = "withitn",
        offset_in_seconds: float = -0.25,
        max_length_seconds: int = 10,
    ) -> None:
        # Don't import funasr_onnx at module load time — that would
        # force whisper_local users to install the yuesub extras.
        # The actual import happens in warmup().
        self._model_root = model_root
        self._model_root_iic = os.path.join(model_root, "iic")
        self._language = language if language not in (None, "") else "auto"
        self._device = device
        self._providers = _device_to_providers(device)
        self._corrector = corrector  # Track C injection
        self._textnorm = textnorm
        self._offset_in_seconds = offset_in_seconds
        self._max_length_seconds = max_length_seconds

        # Lazy-loaded in warmup()
        self._asr_model: Any = None
        self._vad_model: Any = None
        self._tokenizer: Any = None
        self._aligner: Any = None
        self._special_token_ids: List[int] = []
        self._sample_rate = 16_000

    # -----------------------------------------------------------------------
    # Device + path validation
    # -----------------------------------------------------------------------

    def _validate_paths(self) -> tuple[str, str]:
        """Return (sense_voice_dir, fsmn_vad_dir) or raise ASRError."""
        if not os.path.isdir(self._model_root_iic):
            raise ASRError(
                f"yuesub model dir not found at {self._model_root_iic}. "
                "Run `bash scripts/setup-yuesub-models.sh` to create the "
                "symlinks from the yuesub-api repo, then restart the backend."
            )
        sv = os.path.join(self._model_root_iic, _SENSE_VOICE_DIRNAME)
        fsmn = os.path.join(self._model_root_iic, _FSMN_VAD_DIRNAME)
        for path, name in [(sv, "SenseVoiceSmall"), (fsmn, "fsmn-vad")]:
            if not os.path.isdir(path):
                raise ASRError(
                    f"yuesub {name} model not found at {path}. "
                    "Re-run `python download_models.py` inside the "
                    "yuesub-api repo, then re-run "
                    "`scripts/setup-yuesub-models.sh`."
                )
        return sv, fsmn

    # -----------------------------------------------------------------------
    # ASRInterface contract
    # -----------------------------------------------------------------------

    async def warmup(self) -> None:
        """Load SenseVoiceSmall + Fsmn_vad_online + tokenizer + aligner.

        This is the one-time model-load cost (~2-5s on Apple Silicon
        for SenseVoice, ~1s for fsmn-vad). Called once at backend
        startup by `pipeline.warmup()`. The first voice turn after
        the backend start pays this cost; subsequent turns are
        real-time.
        """
        if self._asr_model is not None:
            return

        sv_dir, fsmn_dir = self._validate_paths()

        Fsmn_vad_online, SenseVoiceSmall = _import_funasr_onnx()
        SentencepiecesTokenizer = _import_tokenizer()
        bundle = _import_aligner()

        logger.info(
            f"Loading yuesub ASR: SenseVoiceSmall={sv_dir} "
            f"providers={self._providers}"
        )
        t0 = time.time()
        self._asr_model = SenseVoiceSmall(
            sv_dir,
            batch_size=1,
            quantize=True,
            providers=self._providers,
        )
        logger.info(f"SenseVoiceSmall loaded in {time.time() - t0:.1f}s")

        t0 = time.time()
        self._vad_model = Fsmn_vad_online(
            fsmn_dir,
            batch_size=1,
            quantize=True,
            providers=self._providers,
            max_single_segment_time=self._max_length_seconds * 1000,
        )
        # Set the same cap on the inner vad scorer (Fsmn_vad_online
        # doesn't propagate max_single_segment_time to its scorer
        # automatically — lifted from yuesub-api OnnxTranscriber).
        self._vad_model.vad_scorer.vad_opts.max_single_segment_time = (
            self._max_length_seconds * 1000
        )
        logger.info(f"Fsmn_vad_online loaded in {time.time() - t0:.1f}s")

        # Tokenizer for token-span → text conversion
        bpe_path = os.path.join(
            sv_dir, "chn_jpn_yue_eng_ko_spectok.bpe.model"
        )
        self._tokenizer = SentencepiecesTokenizer(bpemodel=bpe_path)
        # Build a list of special token IDs (<|...|> tagged) to skip
        # when assembling the final transcript. Same logic as
        # yuesub-api OnnxTranscriber._load_tokenizer.
        labels = [
            self._tokenizer.sp.IdToPiece(i)
            for i in range(self._tokenizer.sp.piece_size())
        ]
        special_labels = [
            label for label in labels
            if label.startswith("<|") and label.endswith("|>")
        ]
        self._special_token_ids = [
            self._tokenizer.sp.PieceToId(i)
            for i in ["<s>", "</s>", "<unk>", "<pad>"] + special_labels
        ]

        # Aligner for token timestamps (mms_fa from torchaudio)
        self._aligner = bundle.get_aligner()

        logger.info("YuesubASR ready")

    async def transcribe(
        self, audio: bytes, sample_rate: int = 16_000
    ) -> str:
        """Transcribe a single utterance (PCM bytes) to text.

        Returns a single string (segments joined with spaces).
        Empty string if VAD finds no speech.

        Pipeline:
          1. PCM bytes → float32 waveform
          2. fsmn-vad segments the utterance (per-utterance batch;
             Track D will switch this to per-frame streaming for
             audio-level broadcasts)
          3. SenseVoice transcribes each segment
          4. (Optional) corrector post-processes each segment's text
          5. Segments are joined with spaces, whitespace-collapsed
        """
        if self._asr_model is None:
            raise ASRError("YuesubASR.warmup() must be called first")

        waveform = _pcm_bytes_to_float32(audio, sample_rate)
        if waveform.size == 0:
            return ""

        # VAD segment the utterance. Fsmn_vad_online returns
        # a list of segment dicts: [{"start": int, "end": int}, ...]
        # in 16kHz-sample units (i.e. divide by 16000 for seconds).
        # Track D will refactor this to use a per-frame streaming
        # path for the audio-level WS frame; the per-utterance path
        # here is correct for now.
        try:
            segments = self._vad_model(waveform)
        except Exception as e:
            raise ASRError(f"fsmn-vad failed: {e}") from e

        if not segments:
            return ""

        # ASR each segment
        results: List[str] = []
        for seg in segments:
            # Fsmn_vad_online in funasr_onnx 0.4.1 returns segments
            # as a list of [start_sample, end_sample] pairs (not
            # dicts). Defensive: handle both shapes.
            if isinstance(seg, dict):
                start_idx = int(seg.get("start", 0))
                end_idx = int(seg.get("end", waveform.shape[0]))
            else:
                # Iterable: (start_sample, end_sample) at 16kHz
                seg_list = list(seg)
                if len(seg_list) < 2:
                    continue
                start_idx = int(seg_list[0])
                end_idx = int(seg_list[1])

            if end_idx <= start_idx:
                continue
            end_idx = min(end_idx, waveform.shape[0])
            segment_audio = waveform[start_idx:end_idx]

            text = self._asr_segment(segment_audio)
            if text:
                # Corrector (Track C). The corrector's `acorrect`
                # is async; for corrector="opencc" it's near-instant
                # but still runs in a thread (uniform code path);
                # for corrector="bert" the 300-500ms cost is
                # absorbed by the sentence-streamed TTS pipeline.
                if self._corrector is not None:
                    text = await self._corrector.acorrect(text)
                results.append(text)

        # Join segments with spaces, collapse whitespace
        joined = " ".join(results)
        return " ".join(joined.split())

    # -----------------------------------------------------------------------
    # Internal: ASR one segment
    # -----------------------------------------------------------------------

    def _asr_segment(self, segment_audio: np.ndarray) -> str:
        """Run SenseVoice on a single segment and return the text.

        Lifted from yuesub-api OnnxTranscriber._asr + _process_token_spans.
        Returns "" if the segment is empty or fully noise.
        """
        try:
            language_list, textnorm_list = self._asr_model.read_tags(
                self._language, self._textnorm
            )
            waveform_list = self._asr_model.load_data(
                segment_audio,
                self._asr_model.frontend.opts.frame_opts.samp_freq,
            )
            feats, feats_len = self._asr_model.extract_feat(waveform_list)
            ctc_logits, _ = self._asr_model.infer(
                feats,
                feats_len,
                np.array(language_list[0:1], dtype=np.int32),
                np.array(textnorm_list[0:1], dtype=np.int32),
            )

            # CTC decode
            import torch  # local import to avoid a top-level torch
            # dependency for users who only use whisper_local

            ctc_logits_t = torch.from_numpy(ctc_logits).float()
            ratio = (
                waveform_list[0].shape[0] / ctc_logits_t.size(1) / self._sample_rate
            )

            x = ctc_logits_t[0]
            x = torch.nn.functional.log_softmax(x, dim=-1)
            yseq = x.argmax(dim=-1)
            yseq = torch.unique_consecutive(yseq, dim=-1)

            mask = yseq != self._asr_model.blank_id
            preds = yseq[mask]
            token_spans = self._aligner(ctc_logits_t[0], preds.unsqueeze(0))[0]

            # Stitch token spans into a single string, skipping
            # special tokens (<|lang|>, <|emo|>, <|itn|>, etc.).
            pieces: list[str] = []
            for ts in token_spans:
                if ts.token in self._special_token_ids:
                    continue
                piece = self._tokenizer.sp.IdToPiece(ts.token)
                pieces.append(piece)
            return "".join(pieces).strip()
        except Exception as e:
            # Don't blow up the whole utterance if one segment fails.
            # Log and return empty; the next segment still gets
            # transcribed and the joined result is best-effort.
            logger.warning(f"SenseVoice failed on one segment: {e}")
            return ""


__all__ = [
    "YuesubASR",
    "_resolve_models_dir",
    "_device_to_providers",
]

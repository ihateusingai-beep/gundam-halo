"""Whisper Hugging Face ASR backend — Sprint 23 (v0.1.4) + Sprint 35 (v0.1.5).

This is the third ASR backend selectable via
`voice.asr.backend = "whisper_hf"` in
`~/.gundam-halo/config.toml`. It wraps the
Hugging Face `transformers` `pipeline("automatic-speech-recognition")`
so a fine-tuned HF-format checkpoint
(produced by Sprint 19d's
`finetune_whisper_yue.py` runbook) can be loaded
on Mac via MPS / CPU.

Sprint 35 (v0.1.5, Track 31-D) adds an
**optional** `inference_backend = "mlx"` mode
that swaps the inference path from the HF
`pipeline` to `mlx-whisper.transcribe` (a
separate package, ~50MB, plus `mlx` ~400MB).
The training still uses HF + LoRA per
Sprint 19d; only inference swaps. The
`mlx-whisper` path is opt-in
(`uv sync --extra voice-hf-mlx`); the HF
pipeline remains the default. See
`docs/FEATURE-SPEC-SPRINT26.md` §4.4 + §6
("mlx-whisper doesn't support language =
'cantonese'") and `docs/FEATURE-SPEC-SPRINT31.md`
§Appendix B for the rationale.

**mlx-whisper Cantonese language-hint gap
workaround**: per spec §Appendix B, mlx-whisper
was thought to not expose a usable Cantonese
language hint. In practice (verified against
`mlx-examples/whisper/mlx_whisper/tokenizer.py`
on main, 2026-06-18), mlx-whisper's tokenizer
**does include** `"yue": "cantonese"` as the
last entry of its `LANGUAGES` dict — so we
can pass `language = "yue"` (the ISO 639-3
code) directly via `decode_options`. The HF
pipeline, by contrast, expects the full
ISO 639-1 name `"cantonese"` (different
schema). We therefore keep two language
maps: `_LANGUAGE_MAP` (HF, yue→cantonese)
and `_MLX_LANGUAGE_MAP` (mlx, yue→yue).
If mlx-whisper's tokenizer ever drops the
"yue" entry, we fall back to `initial_prompt`
prompt-engineering (a Cantonese context
string) to nudge the decoder; see
`_invoke_pipeline_mlx`.

The class follows the same lazy-import +
`ASRError` wrap pattern as `YuesubASR`
(`backend/app/voice/asr/yuesub.py:155-194`):
the heavy `transformers` + `torch` deps are
in the `voice-hf` optional extra, and the
`mlx` + `mlx-whisper` deps are in the
`voice-hf-mlx` optional extra. whisper_local /
yuesub users don't pay for any of them.
The imports are deferred to `warmup()` /
`_invoke_pipeline_mlx`, not module load.
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

# Sprint 35 (Track 31-D): the optional
# mlx-whisper inference path. Listed as a
# module-level constant so the test suite
# can monkeypatch the lazy import without
# importing `mlx_whisper` at module load
# (mlx is darwin-only + ~400MB; we don't
# want it on the import path of whisper_local
# / yuesub users).
INFERENCE_BACKEND_HF = "hf"
INFERENCE_BACKEND_MLX = "mlx"
_VALID_INFERENCE_BACKENDS = frozenset({INFERENCE_BACKEND_HF, INFERENCE_BACKEND_MLX})


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


def _import_mlx_whisper() -> Any:
    """Lazy-import the `mlx_whisper` module (Sprint 35 / Track 31-D).

    mlx-whisper is in the `voice-hf-mlx` optional extra, which
    is darwin-only (mlx itself only builds on macOS Apple
    Silicon + recent macOS Intel). whisper_local / yuesub
    users don't pay for the ~450MB `mlx` + `mlx-whisper`
    install. The import is deferred to
    `_invoke_pipeline_mlx` so the module body of
    `whisper_hf.py` stays free of darwin-only deps.

    Raises:
        ASRError: when mlx_whisper is not installed (the
            user hasn't run `uv sync --extra voice-hf-mlx`),
            or when running on a non-darwin platform
            (mlx is Apple-only — the install would have
            failed, but we surface a clear error if the
            user runs the import manually).
    """
    try:
        import mlx_whisper  # type: ignore

        return mlx_whisper
    except ImportError as e:
        raise ASRError(
            "mlx-whisper is required for inference_backend='mlx'. "
            "Install with: uv sync --extra voice-hf-mlx "
            "(darwin-only — mlx is not available on Linux/Windows)."
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


# Sprint 35 (Track 31-D): mlx-whisper's tokenizer uses
# a different language schema than the HF pipeline. The
# HF `generate_kwargs.language` expects the full ISO
# 639-1 name ("cantonese"); mlx-whisper's
# `decode_options["language"]` expects the short Whisper
# token code ("yue"). mlx-whisper's tokenizer (verified
# in `mlx-examples/whisper/mlx_whisper/tokenizer.py` on
# main, 2026-06-18) does include `"yue": "cantonese"`
# as the last LANGUAGES entry — so we can pass
# `language = "yue"` directly. (See the module docstring
# for the rationale + fallback via `initial_prompt`.)
_MLX_LANGUAGE_MAP: dict[str, str] = {
    "yue": "yue",          # Cantonese: mlx-whisper's "yue" token
    "zh": "zh",            # Mandarin Chinese
    "en": "en",            # English
    "ja": "ja",            # Japanese
    "ko": "ko",            # Korean
    # "auto" → None (let mlx-whisper auto-detect from
    # the first 30s of audio). This is mlx-whisper's
    # default behaviour; we just don't pass `language`.
    "auto": "",
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


def _mlx_map_language(language: str) -> Optional[str]:
    """Map a Gundam Halo language code to mlx-whisper's
    short token code (`"yue"` for Cantonese, etc.).

    Returns:
        The mlx-whisper language token (e.g. `"yue"`),
        or `None` to let mlx-whisper auto-detect
        (corresponds to "auto" in the config; we omit
        `language` from `decode_options`).

    Note:
        Differs from `_map_language` in that:
        - HF's schema needs the full ISO 639-1 name
          (`"cantonese"`); mlx-whisper's needs the
          short token (`"yue"`).
        - "auto" → None (mlx-whisper defaults to
          auto-detect when `language` is absent;
          passing `""` would raise ValueError in
          `get_tokenizer`).
    """
    if not language:
        return None
    mapped = _MLX_LANGUAGE_MAP.get(language.lower())
    if mapped is None:
        # Unknown code — pass it through unchanged
        # so mlx-whisper can try its own detection /
        # fail loud with its own error.
        return language.lower()
    if mapped == "":
        # "auto" → let mlx-whisper detect.
        return None
    return mapped


# Sprint 35 (Track 31-D): Cantonese context string for
# the mlx-whisper `initial_prompt` fallback. Per spec
# §Appendix B, if mlx-whisper's tokenizer ever drops
# the "yue" entry, we use prompt-engineering to nudge
# the decoder toward Cantonese output. The string is
# Common Voice yue-style colloquial Cantonese —
# short enough not to dominate the context window,
# but distinctive enough to bias the decoder's
# first-token distribution toward yue vocabulary.
# This is a no-op when the tokenizer accepts "yue"
# (the current path).
_CANTONESE_PROMPT_FALLBACK = (
    "粵語日常對話，例如：你食咗飯未？我哋去街市買餸。",
)


class WhisperHFASR(ASRInterface):
    """Whisper ASR via the Hugging Face `transformers` pipeline
    (default) or `mlx-whisper` (Sprint 35 / Track 31-D, opt-in).

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
            For `inference_backend = "mlx"`, the same path
            is passed to `mlx_whisper.transcribe` as
            `path_or_hf_repo` — the user is responsible
            for putting MLX-converted weights there (or
            symlinking to an `mlx-community/...` HF Hub
            mirror). The `voice-hf-mlx` extra does not
            auto-convert HF→MLX format.
        language: One of "auto" | "yue" | "zh" | "en" | ...
            Mapped to the active backend's language schema
            internally (HF: `yue` → `cantonese`;
            mlx-whisper: `yue` → `"yue"` token). Default:
            "yue" (the M9-E Layer 2 fine-tune is Cantonese).
        device: One of "auto" | "cpu" | "cuda" | "mps" | "mlx".
            Default: "auto" (MPS on Apple Silicon, CUDA
            on Linux/Windows, CPU fallback). The "mlx"
            value selects the mlx-whisper inference path
            (the factory maps `device = "mlx"` to
            `inference_backend = "mlx"`).
        compute_type: One of "auto" | "float16" | "float32".
            Default: "auto" (float32, parity with the
            training script). Ignored on the mlx path
            (mlx-whisper uses float16 internally — the
            `fp16` decode option defaults to True).
        inference_backend: One of "hf" | "mlx". Default: "hf".
            Sprint 35 (Track 31-D) opt-in flag. "mlx" swaps
            the inference path to `mlx_whisper.transcribe`
            for ~2× speedup on Apple Silicon (per spec
            §4.4 acceptance: 600ms → 300ms per turn).
            mlx is darwin-only; on non-Mac platforms the
            import raises a clear ASRError pointing at
            `uv sync --extra voice-hf-mlx`. The factory
            forwards `device = "mlx"` to this field, so
            end users typically don't set it directly.

    Raises:
        ASRError: on `warmup()` if `model_path` is not
            a directory, or if `transformers` / `torch`
            are not installed (the user hasn't run
            `uv sync --extra voice-hf`).
        ValueError: on unknown `inference_backend` value
            (only "hf" | "mlx" supported).
    """

    def __init__(
        self,
        model_path: str,
        language: str = "yue",
        device: str = "auto",
        compute_type: str = "auto",
        inference_backend: str = INFERENCE_BACKEND_HF,
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
        if inference_backend not in _VALID_INFERENCE_BACKENDS:
            raise ValueError(
                f"Unknown inference_backend {inference_backend!r}. "
                f"Expected 'hf' | 'mlx'."
            )
        self._model_path = os.path.expanduser(model_path)
        self._language = language
        self._device = device
        self._compute_type = compute_type
        self._inference_backend = inference_backend
        # Lazy-loaded in warmup() (HF path) or
        # _invoke_pipeline_mlx() (mlx path). The
        # mlx path is module-load-free — `mlx_whisper`
        # is only imported on the first `transcribe()`
        # call, never at __init__ time.
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
                or the HF / mlx call fails.
        """
        if self._inference_backend == INFERENCE_BACKEND_HF:
            if self._pipeline is None:
                await self.warmup()
        # The mlx path doesn't need a `warmup()` step —
        # `mlx_whisper.transcribe` is stateless and loads
        # the model on first call (cached in mlx-whisper's
        # `ModelHolder` singleton after that).

        # Convert int16 PCM → float32 [-1, 1]
        waveform = _pcm_bytes_to_float32(audio, sample_rate)
        if waveform.size == 0:
            return ""

        # Map Gundam Halo's language code to the active
        # backend's schema. HF and mlx-whisper use
        # different conventions (see `_map_language` +
        # `_mlx_map_language`).
        if self._inference_backend == INFERENCE_BACKEND_HF:
            backend_language = _map_language(self._language)
        else:
            backend_language = _mlx_map_language(self._language)

        # The backend call is sync and can take 100-500ms
        # on CPU (HF) or 100-300ms on Apple Silicon (mlx).
        # Run in a worker thread so the event loop stays
        # responsive (the voice pipeline calls
        # `transcribe` from `finalize_turn` which is on
        # the event loop).
        try:
            if self._inference_backend == INFERENCE_BACKEND_HF:
                result = await asyncio.to_thread(
                    self._invoke_pipeline,
                    waveform,
                    backend_language,
                )
            else:
                result = await asyncio.to_thread(
                    self._invoke_pipeline_mlx,
                    waveform,
                    backend_language,
                )
        except Exception as e:
            raise ASRError(
                f"WhisperHFASR.transcribe failed "
                f"(inference_backend={self._inference_backend!r}): {e}"
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

    def _invoke_pipeline_mlx(
        self, waveform: np.ndarray, mlx_language: Optional[str]
    ) -> Any:
        """Invoke mlx-whisper (sync, runs in worker thread).

        Sprint 35 (Track 31-D): opt-in alternative to
        `_invoke_pipeline`. Uses `mlx_whisper.transcribe`
        instead of the HF `pipeline` for ~2× speedup on
        Apple Silicon (per spec §4.4 acceptance: 600ms
        → 300ms per turn on M-series).

        **Cantonese language-hint workaround** (per spec
        §Appendix B): mlx-whisper's tokenizer uses a
        different language schema than the HF pipeline.
        We pass `language = "yue"` (the short Whisper
        token, which mlx-whisper's tokenizer does
        include — verified against
        `mlx-examples/whisper/mlx_whisper/tokenizer.py`
        on main, 2026-06-18). If the tokenizer ever
        drops the "yue" entry, we fall back to
        `initial_prompt` prompt-engineering — a short
        colloquial Cantonese string to bias the
        decoder's first-token distribution toward
        yue vocabulary. See `_CANTONESE_PROMPT_FALLBACK`.

        Args:
            waveform: float32 [-1, 1] waveform at 16kHz
                (the Gundam Halo voice pipeline rate).
            mlx_language: the short mlx-whisper language
                token (e.g. `"yue"` for Cantonese),
                or `None` to let mlx-whisper auto-detect
                (corresponds to `language = "auto"` in
                the config).

        Returns:
            A dict with at least `"text"` (and
            optionally `"segments"` + `"language"` —
            per `mlx_whisper.transcribe` docstring).
            The `transcribe()` wrapper extracts `text`
            and whitespace-strips it.

        Raises:
            ASRError: when `mlx_whisper` is not installed
                (the user hasn't run
                `uv sync --extra voice-hf-mlx`).
            RuntimeError: when `mlx_whisper.transcribe`
                itself fails (e.g. model_path missing,
                unsupported language token, etc.).
        """
        mlx_whisper = _import_mlx_whisper()

        # Build the mlx-whisper call kwargs.
        #
        # The real `mlx_whisper.transcribe` signature
        # (verified against
        # `mlx-examples/whisper/mlx_whisper/transcribe.py`
        # on main, 2026-06-18) takes top-level kwargs
        # for `path_or_hf_repo`, `temperature`,
        # `initial_prompt`, `word_timestamps`, etc.
        # **and** a `**decode_options` catch-all that
        # forwards into `DecodingOptions` — that
        # includes `language` and `task`. The cleanest
        # way to keep our call site tidy is to build a
        # dict and splat it; the test asserts the same
        # call shape so we don't have to refactor when
        # mlx-whisper adds new decode options.
        transcribe_kwargs: dict[str, Any] = {
            "path_or_hf_repo": self._model_path,
            # Cantonese prompt fallback (no-op when the
            # tokenizer accepts "yue" — see module
            # docstring). We always pass the prompt for
            # `language = "yue"` to make the bias
            # explicit; mlx-whisper's `initial_prompt`
            # is cheap (just tokenization) and improves
            # WER on domain-specific vocab.
            "initial_prompt": (
                _CANTONESE_PROMPT_FALLBACK
                if mlx_language == "yue"
                else None
            ),
        }
        # Forward language / task into mlx-whisper's
        # `**decode_options` (per the real API). We
        # only include `language` when the user picked
        # something specific — `language = "auto"`
        # (mlx_language is None) means "let mlx-whisper
        # detect", so we omit the key entirely.
        if mlx_language is not None:
            transcribe_kwargs["language"] = mlx_language
        transcribe_kwargs["task"] = "transcribe"

        # `path_or_hf_repo` is the model path (or HF Hub
        # repo). The same `model_path` we use for the
        # HF pipeline is forwarded here — the user is
        # responsible for putting MLX-converted weights
        # there (or symlinking to an `mlx-community/...`
        # mirror). The `voice-hf-mlx` extra does not
        # auto-convert HF→MLX format.
        # Let exceptions propagate — the `transcribe()`
        # wrapper catches and re-wraps them in ASRError
        # with the `inference_backend` field in the
        # message. Pre-wrapping here would lose the
        # original exception type / traceback.
        return mlx_whisper.transcribe(waveform, **transcribe_kwargs)


__all__ = [
    "WhisperHFASR",
    "INFERENCE_BACKEND_HF",
    "INFERENCE_BACKEND_MLX",
]

"""Tests for the M9-E Layer 2 Cantonese fine-tuned Whisper model.

These tests are the *acceptance gate* for M9-E. They:
  1. Verify the M9-C Cantonese fixture still transcribes correctly
     with the fine-tuned model.
  2. Verify a held-out Cantonese fixture (recorded by the user, NOT
     part of the training set) transcribes with WER < 20%.

If the fine-tuned model isn't on disk yet, these tests are
**skipped** — the actual M9-E training run is its own sprint.
That way the test suite stays green throughout development and
the test will start running the moment a trained model lands.

To run the test:
    1. Train the model:
       .venv/bin/python scripts/finetune_whisper_yue.py \\
           --output_dir ~/.gundam-halo/models/whisper-yue-base/
    2. Run pytest:
       .venv/bin/python -m pytest tests/voice/test_whisper_yue.py -v
"""
from __future__ import annotations

import os
import wave
from pathlib import Path

import pytest


# Default location matches finetune_whisper_yue.py
FINE_TUNED_MODEL_DIR = Path(
    os.path.expanduser("~/.gundam-halo/models/whisper-yue-base/")
)

# M9-C's Cantonese fixture, used as the basic functional check.
M9C_FIXTURE = Path(
    "tests/voice/fixtures/readme_query.wav"
)


def _wav_to_pcm_bytes(path: Path) -> tuple[bytes, int]:
    """Read a 16kHz mono s16le WAV into raw PCM bytes.

    Returns (pcm_bytes, sample_rate). Whisper wants raw PCM;
    WhisperLocalASR writes to a temp .wav before calling whisper.
    The HF pipeline prefers numpy; this helper preserves the
    contract the existing code uses.
    """
    with wave.open(str(path), "rb") as wf:
        assert wf.getnchannels() == 1, "expected mono"
        assert wf.getsampwidth() == 2, "expected s16le"
        assert wf.getframerate() == 16000, "expected 16kHz"
        pcm = wf.readframes(wf.getnframes())
    return pcm, 16000


# --- skip-everything guard -----------------------------------------------


def _require_fine_tuned_model() -> None:
    """Skip the test if the fine-tuned model isn't on disk yet.

    M9-E Layer 2 is its own sprint; until it lands, these tests
    just stay out of the way. Once the model is trained, they
    start running automatically.
    """
    if not FINE_TUNED_MODEL_DIR.exists():
        pytest.skip(
            f"Fine-tuned model not found at {FINE_TUNED_MODEL_DIR}. "
            f"Train with: .venv/bin/python scripts/finetune_whisper_yue.py"
        )


# --- tests ----------------------------------------------------------------


def test_fine_tuned_model_directory_exists():
    """Sanity check: the directory exists when the test is allowed
    to run. This is the gate; if it doesn't, the rest skip."""
    _require_fine_tuned_model()
    assert FINE_TUNED_MODEL_DIR.is_dir()


def test_fine_tuned_model_loads():
    """Load the HF-format Whisper model + processor from disk."""
    _require_fine_tuned_model()
    # Lazy import so the test file is importable without the
    # `train` extra installed.
    from transformers import WhisperForConditionalGeneration, WhisperProcessor

    model = WhisperForConditionalGeneration.from_pretrained(
        FINE_TUNED_MODEL_DIR
    )
    processor = WhisperProcessor.from_pretrained(FINE_TUNED_MODEL_DIR)
    assert model is not None
    assert processor is not None


def test_m9c_cantonese_fixture_transcribes():
    """The M9-C fixture must still transcribe the spoken Cantonese
    query correctly (or close enough — WER is the metric, not
    exact string match).

    The original spoken query is approximately:
        幫我讀 gundam-halo backend 嘅 README 嘅第一行

    Pre-M9-E (Whisper base) the ASR heard this as garbled English
    ("Please use the file read tool to read backhand read me and
    tell me the first line."). Post-M9-E the ASR should at least
    preserve the proper nouns ("gundam", "halo", "backend",
    "README") in the transcription.
    """
    _require_fine_tuned_model()

    if not M9C_FIXTURE.exists():
        pytest.skip(f"M9-C fixture missing at {M9C_FIXTURE}")

    pcm, sr = _wav_to_pcm_bytes(M9C_FIXTURE)
    assert sr == 16000

    # Lazy import — `train` extra only.
    from transformers import WhisperForConditionalGeneration, WhisperProcessor
    import torch

    model = WhisperForConditionalGeneration.from_pretrained(
        FINE_TUNED_MODEL_DIR
    )
    processor = WhisperProcessor.from_pretrained(FINE_TUNED_MODEL_DIR)

    # Inference path: feature extractor → tensor → generate → decode
    input_features = processor.feature_extractor(
        _pcm_to_numpy(pcm, sr),
        sampling_rate=sr,
        return_tensors="pt",
    ).input_features
    with torch.no_grad():
        predicted_ids = model.generate(input_features)
    transcription = processor.batch_decode(
        predicted_ids, skip_special_tokens=True
    )[0].strip()

    # We don't assert exact text — WER is the real metric. But at
    # least one of the key proper nouns must survive.
    proper_nouns = ["gundam", "halo", "backend", "README", "readme"]
    assert any(
        noun.lower() in transcription.lower() for noun in proper_nouns
    ), (
        f"Expected at least one proper noun from {proper_nouns} in "
        f"transcription, got: {transcription!r}"
    )


def test_held_out_wer_under_20_percent():
    """Held-out Cantonese fixture must achieve WER < 20%.

    The held-out fixture should be recorded by the user, NOT in
    the training set. M9-E acceptance criteria is WER < 20%
    on this kind of out-of-distribution sample — that's what
    production will actually face.
    """
    _require_fine_tuned_model()

    held_out_dir = Path(
        os.path.expanduser(
            "~/.gundam-halo/cache/cv-yue/eval-fixtures/"
        )
    )
    if not held_out_dir.exists() or not list(held_out_dir.glob("*.wav")):
        pytest.skip(
            f"No held-out Cantonese fixtures at {held_out_dir}. "
            f"Record 5-10 utterances + transcribe them to .wav + "
            f".txt pairs to enable WER eval."
        )

    # Lazy imports — `train` extra only.
    from transformers import WhisperForConditionalGeneration, WhisperProcessor
    import torch
    from jiwer import wer

    model = WhisperForConditionalGeneration.from_pretrained(
        FINE_TUNED_MODEL_DIR
    )
    processor = WhisperProcessor.from_pretrained(FINE_TUNED_MODEL_DIR)

    predictions: list[str] = []
    references: list[str] = []
    for wav_path in sorted(held_out_dir.glob("*.wav")):
        txt_path = wav_path.with_suffix(".txt")
        if not txt_path.exists():
            continue
        pcm, sr = _wav_to_pcm_bytes(wav_path)
        input_features = processor.feature_extractor(
            _pcm_to_numpy(pcm, sr),
            sampling_rate=sr,
            return_tensors="pt",
        ).input_features
        with torch.no_grad():
            predicted_ids = model.generate(input_features)
        predictions.append(
            processor.batch_decode(
                predicted_ids, skip_special_tokens=True
            )[0].strip()
        )
        references.append(txt_path.read_text().strip())

    if not predictions:
        pytest.skip("No (wav, txt) pairs found in held-out dir")

    score = wer(references, predictions)
    assert score < 0.20, (
        f"Held-out WER {score:.3f} exceeds the 0.20 threshold. "
        f"Predictions: {predictions!r} References: {references!r}"
    )


def _pcm_to_numpy(pcm: bytes, sample_rate: int):
    """Convert raw s16le PCM bytes to float32 numpy in [-1, 1]."""
    import numpy as np
    audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    return audio

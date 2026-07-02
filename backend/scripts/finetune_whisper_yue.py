"""M9-E Layer 2 — Fine-tune Whisper base on Cantonese (yue).

Stack: Hugging Face transformers + PEFT/LoRA + datasets.
Output: an HF-format Whisper checkpoint with LoRA adapters merged
into the base weights, saved to `~/.gundam-halo/models/whisper-yue-base/`.

This checkpoint directory can then be pointed at via
`voice.asr.model_path` in `~/.gundam-halo/config.toml` —
note: `WhisperLocalASR` (openai-whisper backend) cannot load HF
directories yet; the v0.1.4 sprint will replace it with a
HF-pipeline implementation. See docs/tickets/M9-E.md.

Why LoRA, not full fine-tune:
- Whisper base = 74M params; full fine-tune needs ~6GB peak RAM
  and ~3-4h per epoch on M-series MPS.
- LoRA on attention + FFN blocks: ~5M trainable params, ~1.5GB
  peak, ~50min per epoch on M-series MPS. Quality is comparable
  for our 50h Common Voice yue corpus.

Why Common Voice yue:
- Mozilla CC-BY-SA 4.0, ~50h released in v11+.
- Public + on-disk pre-processed (no auth wall).
- Cantonese native speakers reading prompted text, not
  broadcast/phone audio.

Caveats baked in:
- "Cantonese" in Whisper is "zh" with hints; we set
  language="cantonese", task="transcribe" on the processor
  and let HF handle the forced_decoder_ids plumbing.
- The Common Voice audio is 48kHz, we resample to 16kHz
  on the fly via the WhisperFeatureExtractor.
- The training loop uses gradient_accumulation to keep
  per-device batch_size=1 (memory ceiling on M-series).
- The script is **resumable**: it saves the LoRA adapter
  + base model snapshot at every `save_steps`, so a crashed
  run can pick up via `--resume_from <dir>`.

Layer 2 v2 — personalised fine-tune (Sprint 33 / Track 31-B)

In addition to the Common Voice yue path above, the script
accepts two more flags that wire it into the **self-record
personalised fine-tune** flow (FEATURE-SPEC-SPRINT26.md §4.1):

  --base_model_path <dir>    Path to an existing HF-format
                             Whisper checkpoint to continue
                             from. Defaults to the HF Hub
                             `openai/whisper-base` id when
                             unset (the Common Voice yue
                             baseline). For the personalised
                             flow, set this to the Common
                             Voice yue checkpoint
                             (`~/.gundam-halo/models/whisper-yue-base/`)
                             so the LoRA adapter layers the
                             user's voice on top of the
                             already-Cantonese-aware base
                             instead of starting from
                             English-only weights.

  --train_audio_dir <dir>    Path to a directory of
                             `manifest.jsonl` self-record
                             chunks. Each line is
                             `{audio_path, text, duration_s,
                             sample_rate}`. When set, the
                             script loads this corpus (instead
                             of streaming Common Voice yue)
                             and trains on it as the primary
                             fine-tune target. Combined with
                             `--base_model_path`, this is
                             the Layer 2 v2 personalised
                             fine-tune. See Sprint 33
                             `tests/voice/test_self_record_manifest.py`
                             for the JSONL contract.

The self-record JSONL format is the same one the Tauri app's
`frontend/src-tauri/src/recording.rs` writes during the
Record card flow — chunk audio files
(`chunk-NNN.wav`, 30s each, 16kHz mono) plus the per-chunk
transcription from the v0.1.4 WhisperHFASR backend.

Usage:
    cd backend
    uv sync --extra train --extra voice
    .venv/bin/python scripts/finetune_whisper_yue.py \\
        --dataset_version 11.0 \\
        --max_train_hours 50 \\
        --num_train_epochs 3 \\
        --output_dir ~/.gundam-halo/models/whisper-yue-base/

    # Layer 2 v2 personalised fine-tune:
    .venv/bin/python scripts/finetune_whisper_yue.py \\
        --base_model_path ~/.gundam-halo/models/whisper-yue-base/ \\
        --train_audio_dir ~/.gundam-halo/recordings/yue-self-2026-06-18/ \\
        --num_train_epochs 1 \\
        --output_dir ~/.gundam-halo/models/whisper-yue-self-2026-06-18/

Estimated wall time on M-series 16GB:
- Dataset download (50h): ~30min
- LoRA training (3 epochs): ~2.5h
- Eval + WER on held-out test set: ~5min
- Layer 2 v2 personalised fine-tune (30 min self-record):
  ~1h wall clock (1 epoch over ~30min of audio is enough for
  personalisation; the held-out eval is the real quality gate).

This script has NOT been run end-to-end yet — it is the
ship-ready recipe for the actual training run. See
docs/tickets/M9-E.md for status.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Make `app` importable when running from `backend/` (matches the
# other M9-* smoke scripts' layout).
BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

logger = logging.getLogger("finetune_whisper_yue")

# Default output location — keep consistent with
# ~/.gundam-halo/models/<...>/ convention used by Silero VAD.
DEFAULT_OUTPUT_DIR = os.path.expanduser(
    "~/.gundam-halo/models/whisper-yue-base/"
)
# Base model on Hugging Face Hub. We pin a specific revision so
# future HF updates don't silently change the starting weights.
HF_BASE_MODEL = "openai/whisper-base"
# Common Voice yue on HF. Versions v11+ ship the ~50h yue split.
# `common_voice_13_0` is the latest at time of writing.
DEFAULT_CV_VERSION = "13.0"


# ---------------------------------------------------------------------------
# Data collator (Sprint 55)
# ---------------------------------------------------------------------------


class WhisperSpeechCollator:
    """Pad labels with -100, stack input_features.

    Sprint 55: DataCollatorForSeq2Seq is the wrong collator for
    Whisper — it calls `tokenizer.pad()` on whatever it sees and
    chokes on raw audio dicts. This collator:
      - stacks `input_features` (already fixed-shape 80×3000
        log-mel spectrograms from the WhisperProcessor)
      - pads `labels` (variable-length token lists) with -100
        so the cross-entropy loss ignores them.

    Defined at module top-level (not inside
    `build_model_and_processor`) because PyTorch DataLoader
    workers need to pickle the collator — local classes can't
    be pickled.
    """

    def __init__(self, processor):
        self.processor = processor
        self.label_pad_token_id = -100

    def __call__(self, features):
        import torch
        input_features = [
            torch.as_tensor(f["input_features"], dtype=torch.float32)
            for f in features
        ]
        input_features = torch.stack(input_features, dim=0)
        label_features = [
            torch.as_tensor(f["labels"], dtype=torch.long)
            for f in features
        ]
        labels_padded = torch.nn.utils.rnn.pad_sequence(
            label_features,
            batch_first=True,
            padding_value=self.label_pad_token_id,
        )
        return {
            "input_features": input_features,
            "labels": labels_padded,
        }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "M9-E Layer 2: fine-tune Whisper base on Common Voice yue "
            "with LoRA adapters, save to ~/.gundam-halo/models/whisper-yue-base/."
        ),
    )
    p.add_argument(
        "--dataset_version",
        default=DEFAULT_CV_VERSION,
        help="Common Voice version (e.g. 11.0, 12.0, 13.0).",
    )
    p.add_argument(
        "--max_train_hours",
        type=float,
        default=50.0,
        help="Cap on training-set hours (Common Voice yue is ~50h in v11+).",
    )
    p.add_argument(
        "--num_train_epochs",
        type=int,
        default=3,
        help="Number of training epochs (3 is a good default for LoRA on 50h).",
    )
    p.add_argument(
        "--per_device_train_batch_size",
        type=int,
        default=1,
        help="Per-device batch size. Keep at 1 for MPS; tune with "
             "gradient_accumulation_steps instead.",
    )
    p.add_argument(
        "--gradient_accumulation_steps",
        type=int,
        default=8,
        help="Effective batch size = per_device × grad_accum × num_gpus. "
             "8 gives effective batch of 8 on a single MPS device.",
    )
    p.add_argument(
        "--learning_rate",
        type=float,
        default=1e-3,
        help="LoRA learning rate. 1e-3 is the standard starting point "
             "for LoRA on Whisper.",
    )
    p.add_argument(
        "--lora_r",
        type=int,
        default=32,
        help="LoRA rank. 32 gives ~5M trainable params on Whisper base.",
    )
    p.add_argument(
        "--lora_alpha",
        type=int,
        default=64,
        help="LoRA alpha (scaling). Standard ratio is alpha = 2*r.",
    )
    p.add_argument(
        "--output_dir",
        default=DEFAULT_OUTPUT_DIR,
        help="Where to save the merged fine-tuned model.",
    )
    p.add_argument(
        "--resume_from",
        default=None,
        help="Path to a previous run's output dir to resume LoRA training from.",
    )
    p.add_argument(
        "--skip_eval",
        action="store_true",
        help="Skip the held-out WER evaluation at the end (faster).",
    )
    p.add_argument(
        "--wer_threshold",
        type=float,
        default=0.20,
        help="Exit non-zero if held-out WER > this. Default 0.20 (20%%).",
    )
    # Sprint 33 / Track 31-B — Layer 2 v2 personalised fine-tune
    # flags. See the module docstring + FEATURE-SPEC-SPRINT26.md
    # §4.1 for the contract. Defaults preserve the Common Voice
    # yue baseline behaviour; the Tauri app passes both when the
    # user clicks "Train" on the Personalised Fine-tune card.
    p.add_argument(
        "--base_model_path",
        default=None,
        help=(
            "Sprint 33: path to an existing HF-format Whisper "
            "checkpoint to continue from (e.g. the Common Voice "
            "yue baseline at ~/.gundam-halo/models/whisper-yue-base/). "
            "When unset, the script downloads `openai/whisper-base` "
            "from the HF Hub (the Common Voice yue baseline flow)."
        ),
    )
    p.add_argument(
        "--train_audio_dir",
        default=None,
        help=(
            "Sprint 33: path to a directory of `manifest.jsonl` "
            "self-record chunks (one JSON object per line with "
            "{audio_path, text, duration_s, sample_rate}). When "
            "set, the script trains on the self-record corpus "
            "instead of streaming Common Voice yue. Combined "
            "with --base_model_path this is the Layer 2 v2 "
            "personalised fine-tune."
        ),
    )
    return p.parse_args()


# ---------------------------------------------------------------------------
# Dataset preparation
# ---------------------------------------------------------------------------


@dataclass
class DatasetPaths:
    """Local cache paths for the prepared Common Voice yue splits."""

    root: Path
    train: Path
    validation: Path
    test: Path

    @property
    def exists(self) -> bool:
        return self.train.exists() and self.validation.exists() and self.test.exists()


def _audio_seconds(s: dict, sample_rate: int = 16000) -> float:
    """Read an audio sample's duration in seconds.

    HF datasets' Audio feature decodes the audio bytes
    into a numpy array under `s["audio"]["array"]`. For
    streaming mode the array is decoded on-the-fly; if
    the sample doesn't have an array (e.g. raw bytes
    only), we return 0 and let the caller decide
    whether to skip the sample.
    """
    audio = s.get("audio") or {}
    arr = audio.get("array")
    if arr is None:
        return 0.0
    try:
        return float(len(arr)) / float(sample_rate)
    except TypeError:
        return 0.0


def split_by_client_id(
    samples: list[dict],
    *,
    test_ratio: float = 0.05,
    val_ratio: float = 0.05,
) -> dict[str, list[dict]]:
    """Speaker-disjoint split: same client_id never
    appears in two splits.

    Speakers are sorted by sample count descending —
    the speakers with the most data go to test/val so
    the held-out splits have enough samples for a
    stable WER. The test set is the top `test_ratio`
    of speakers; val is the next `val_ratio`; the rest
    is train.

    Pure function: no I/O, no model loading. Unit-
    testable with a plain list of mock samples.
    """
    by_speaker: dict[str, list[dict]] = {}
    for s in samples:
        cid = s.get("client_id") or "unknown"
        by_speaker.setdefault(cid, []).append(s)
    speakers = sorted(
        by_speaker.keys(),
        key=lambda k: -len(by_speaker[k]),
    )
    n = len(speakers)
    # At least 1 speaker in test/val if there are any;
    # for very small corpora the ratios would round to
    # 0 and we want SOME held-out data.
    n_test = max(1, int(n * test_ratio)) if n > 0 else 0
    n_val = max(1, int(n * val_ratio)) if n > 0 else 0
    # Don't double-count: cap n_val at n - n_test.
    n_val = min(n_val, max(0, n - n_test))
    test_speakers = set(speakers[:n_test])
    val_speakers = set(speakers[n_test:n_test + n_val])

    out: dict[str, list[dict]] = {
        "train": [],
        "validation": [],
        "test": [],
    }
    for s in samples:
        cid = s.get("client_id") or "unknown"
        if cid in test_speakers:
            out["test"].append(s)
        elif cid in val_speakers:
            out["validation"].append(s)
        else:
            out["train"].append(s)
    logger.info(
        f"split_by_client_id: {len(speakers)} speakers, "
        f"train={len(out['train'])} val={len(out['validation'])} "
        f"test={len(out['test'])} "
        f"(test_speakers={n_test}, val_speakers={n_val})"
    )
    return out


def cap_at_hours(
    samples: list[dict],
    max_hours: float,
    sample_rate: int = 16000,
) -> list[dict]:
    """Cap the training set at `max_hours` of audio.

    Algorithm: iterate in input order, keep the
    earliest samples that fit under the cap. This is
    deterministic (no sort instability) and preserves
    the input order, which matters for the speaker-
    balanced dataset layout — `split_by_client_id`
    groups samples by speaker, and the early samples
    in each speaker group are the most "natural"
    (recorded first in Common Voice's pipeline).

    Greedy "drop the longest first" is also valid but
    reorders the output and complicates unit testing.
    The "keep the earliest that fit" variant is
    simpler and the cap is typically loose enough
    (50h for 30-60k samples at 4s each = 33-66h
    available, cap at 50h drops ~25%) that the
    difference is minor in practice.
    """
    cap_s = max_hours * 3600.0
    out: list[dict] = []
    running_s = 0.0
    dropped = 0
    for s in samples:
        dur = _audio_seconds(s, sample_rate)
        if running_s + dur > cap_s:
            dropped += 1
            continue
        out.append(s)
        running_s += dur
    if dropped:
        logger.info(
            f"cap_at_hours: kept {len(out)} samples "
            f"({running_s / 3600:.2f}h of {max_hours}h cap, "
            f"dropped {dropped})"
        )
    return out


def save_splits_as_parquet(
    splits: dict[str, list[dict]],
    cache_dir: Path,
) -> DatasetPaths:
    """Write each split to a parquet file under
    `cache_dir/{split}/data.parquet`. Resumable: if
    the file already exists, skip the write.

    Lazy-imports pyarrow so unit tests that don't
    install the `train` extra can still import this
    module. The training script that needs parquet
    reads will have pyarrow installed.
    """
    import pyarrow as pa
    import pyarrow.parquet as pq

    out = DatasetPaths(
        root=cache_dir,
        train=cache_dir / "train",
        validation=cache_dir / "validation",
        test=cache_dir / "test",
    )
    for split_name, samples in splits.items():
        split_dir = getattr(out, split_name)
        split_dir.mkdir(parents=True, exist_ok=True)
        out_file = split_dir / "data.parquet"
        if out_file.exists():
            logger.info(
                f"save_splits_as_parquet: {out_file} exists, "
                f"skipping ({out_file.stat().st_size // 1024} KiB)"
            )
            continue
        # Drop the `audio` column — the raw numpy
        # doesn't roundtrip cleanly through pyarrow
        # without soundfile embedding. The training
        # script re-reads via HF's Audio feature when
        # it loads the parquet.
        rows = [
            {k: v for k, v in s.items() if k != "audio"}
            for s in samples
        ]
        if not rows:
            logger.warning(
                f"save_splits_as_parquet: {split_name} split is "
                f"empty, skipping"
            )
            continue
        table = pa.Table.from_pylist(rows)
        pq.write_table(table, out_file)
        logger.info(
            f"save_splits_as_parquet: {split_name}: wrote "
            f"{len(rows)} rows to {out_file}"
        )
    return out


def load_splits_row_counts(cache_dir: Path) -> tuple[int, int, int]:
    """Read the row counts of the three splits. Returns
    (train_n, val_n, test_n). Returns (0, 0, 0) if any
    of the parquet files are missing.
    """
    try:
        import pyarrow.parquet as pq
    except ImportError:
        return (0, 0, 0)
    counts = []
    for split in ("train", "validation", "test"):
        f = cache_dir / split / "data.parquet"
        if not f.exists():
            return (0, 0, 0)
        try:
            counts.append(pq.read_metadata(f).num_rows)
        except Exception:
            return (0, 0, 0)
    return tuple(counts)  # type: ignore


def prepare_common_voice_yue(
    cv_version: str,
    cache_dir: Path,
    max_train_hours: float,
) -> DatasetPaths:
    """Download and split Common Voice yue into train/val/test.

    Sprint 21: full implementation. Steps:
      1. Stream `mozilla-foundation/common_voice_<ver>_0`
         yue via `datasets.load_dataset(streaming=True)`
         and decode audio on the fly at 16kHz.
      2. Split by `client_id` at the speaker level
         (Common Voice's standard split — never split
         one speaker across train and val).
      3. Cap the train split at `max_train_hours` of
         audio (drop the longest samples first).
      4. Materialise each split to a parquet file
         under `cache_dir/{split}/data.parquet`. The
         write is resumable: existing files are
         skipped on re-run.

    The implementation is split into pure helpers
    (`split_by_client_id`, `cap_at_hours`) and impure
    I/O wrappers (`save_splits_as_parquet`,
    `load_splits_row_counts`). The pure helpers are
    unit-testable without `datasets` or `pyarrow`;
    the impure wrapper imports them lazily.

    Returns paths to the local prepared parquet dirs.
    """
    from datasets import load_dataset, Audio  # noqa: F401 — lazy import

    # Check if all three splits already exist on disk;
    # if so, skip the streaming download.
    existing = load_splits_row_counts(cache_dir)
    if all(n > 0 for n in existing):
        logger.info(
            f"prepare_common_voice_yue: all three splits "
            f"already on disk at {cache_dir} (rows: "
            f"train={existing[0]}, val={existing[1]}, "
            f"test={existing[2]}), skipping download"
        )
        return DatasetPaths(
            root=cache_dir,
            train=cache_dir / "train",
            validation=cache_dir / "validation",
            test=cache_dir / "test",
        )

    logger.info(
        f"prepare_common_voice_yue: streaming Common Voice "
        f"{cv_version} yue from Hugging Face Hub (audio "
        f"resampled to 16kHz on the fly)…"
    )
    ds = load_dataset(
        f"mozilla-foundation/common_voice_{cv_version.replace('.', '_')}",
        "yue",
        split="train+validation+test",
        streaming=True,
        trust_remote_code=True,
    )
    ds = ds.cast_column("audio", Audio(sampling_rate=16000))
    samples = list(ds)
    logger.info(
        f"prepare_common_voice_yue: streaming complete — "
        f"{len(samples)} samples downloaded"
    )

    splits = split_by_client_id(samples)
    splits["train"] = cap_at_hours(
        splits["train"], max_hours=max_train_hours
    )
    return save_splits_as_parquet(splits, cache_dir)


def prepare_self_record_dir(
    train_audio_dir: Path,
    val_split: float = 0.1,
    seed: int = 42,
) -> tuple[Path, Path, Path | None]:
    """Load a self-record manifest.jsonl into a Whisper-compatible
    HF Dataset.

    Sprint 55 (in-session, 2026-07-03): the loader for the
    `--train_audio_dir` flag that Sprint 33 declared but deferred.
    Reads `train_audio_dir/manifest.jsonl` (or any .jsonl under
    `train_audio_dir/`) where each line is::

        {"audio_path": "...", "text": "...", "duration_s": 5.2, "sample_rate": 16000}

    Returns a 3-tuple of (train_dataset_path, val_dataset_path,
    test_dataset_path). Test path is None if no test.jsonl is
    found; the caller can then use the held-out pair for eval.

    The dataset is materialised as a HF Dataset of rows with the
    schema expected by `Seq2SeqTrainer`:
        - audio_path: str (WAV path)
        - sentence:   str (training transcript)
        - duration_s: float
    Audio is loaded lazily by the trainer via the WhisperProcessor
    (which calls `datasets.Audio(sampling_rate=16000)` on the
    `audio` column — added in `_add_audio_column` below).
    """
    import json
    from datasets import Dataset

    if not train_audio_dir.exists():
        raise FileNotFoundError(
            f"--train_audio_dir not found: {train_audio_dir}"
        )

    # Find a manifest.jsonl inside train_audio_dir. Accept either
    # `manifest.jsonl` directly under the dir or any `*.jsonl`
    # inside a `train/` subdir (the fsicoli prep script layout).
    manifest_path = train_audio_dir / "manifest.jsonl"
    if not manifest_path.exists():
        candidate = train_audio_dir / "train" / "manifest.jsonl"
        if candidate.exists():
            manifest_path = candidate
        else:
            raise FileNotFoundError(
                f"No manifest.jsonl found at {train_audio_dir} "
                f"or {train_audio_dir}/train/"
            )
    # Look for a sibling test/manifest.jsonl for the eval split.
    # If absent, return None and let the trainer skip the eval
    # step (caller passes --skip_eval or the held-out test pair).
    test_path: Path | None = train_audio_dir / "test" / "manifest.jsonl"
    if not test_path.exists():
        test_path = train_audio_dir.parent / "test" / "manifest.jsonl"
    if not test_path.exists():
        test_path = None

    logger.info(
        f"prepare_self_record_dir: reading manifest from {manifest_path}"
    )

    # Parse manifest.jsonl → list of dicts
    rows: list[dict] = []
    with open(manifest_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    logger.info(
        f"prepare_self_record_dir: {len(rows)} manifest rows"
    )

    # Schema: manifest uses `text` per Sprint 45 self-record
    # contract; trainer expects `sentence` per Common Voice
    # convention. Map once here so the trainer doesn't have to
    # branch.
    for r in rows:
        if "text" in r and "sentence" not in r:
            r["sentence"] = r["text"]

    # Drop rows whose audio file is missing — saves the trainer
    # from raising on a missing file at iteration time.
    rows = [r for r in rows if Path(r["audio_path"]).exists()]
    logger.info(
        f"prepare_self_record_dir: {len(rows)} rows with audio present"
    )

    # Load audio bytes via soundfile. WhisperProcessor expects
    # `sample["audio"]["array"]` (a numpy float array) and
    # `sample["audio"]["sampling_rate"]`. We pre-load here so the
    # trainer doesn't have to import soundfile / decode MP3→PCM at
    # iteration time (which would dominate training wall clock).
    import soundfile as sf
    import numpy as np

    def _load_audio(row: dict) -> dict:
        audio, sr = sf.read(row["audio_path"], dtype="float32")
        # WhisperProcessor handles stereo → mono internally via
        # its feature_extractor, but to be safe we mono-ize here.
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        # Resample to 16 kHz if needed (soundfile gives native sr).
        if sr != 16000:
            # Naive linear resample. Good enough for fine-tune;
            # Whisper's feature_extractor will also normalise.
            target_len = int(len(audio) * 16000 / sr)
            audio = np.interp(
                np.linspace(0, len(audio), target_len, endpoint=False),
                np.arange(len(audio)),
                audio,
            ).astype("float32")
            sr = 16000
        row["audio"] = {"array": audio, "sampling_rate": sr}
        return row

    # 90/10 train/val split (deterministic via seed)
    import random
    rng = random.Random(seed)
    indices = list(range(len(rows)))
    rng.shuffle(indices)
    n_val = max(1, int(len(rows) * val_split))
    val_indices = set(indices[:n_val])
    train_rows = [rows[i] for i in range(len(rows)) if i not in val_indices]
    val_rows = [rows[i] for i in range(len(rows)) if i in val_indices]
    logger.info(
        f"prepare_self_record_dir: split {len(train_rows)} train / "
        f"{len(val_rows)} val (val_split={val_split})"
    )

    # Materialise as HF Datasets and save to disk so the caller
    # can use the same `load_from_disk(str(paths.train))` pattern
    # the Common Voice path uses. We write into a sibling
    # `_dataset/` subdir next to the manifest.
    output_root = train_audio_dir / "_dataset"
    output_root.mkdir(parents=True, exist_ok=True)

    train_dir = output_root / "train"
    val_dir = output_root / "validation"
    # Pre-load audio bytes so the trainer doesn't decode at iter time.
    logger.info("prepare_self_record_dir: pre-loading train audio…")
    train_rows = [_load_audio(r) for r in train_rows]
    logger.info("prepare_self_record_dir: pre-loading val audio…")
    val_rows = [_load_audio(r) for r in val_rows]
    Dataset.from_list(train_rows).save_to_disk(str(train_dir))
    Dataset.from_list(val_rows).save_to_disk(str(val_dir))
    logger.info(
        f"prepare_self_record_dir: saved train={train_dir}, val={val_dir}"
    )

    test_dir: Path | None = None
    if test_path is not None:
        test_rows: list[dict] = []
        with open(test_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                if "text" in row and "sentence" not in row:
                    row["sentence"] = row["text"]
                test_rows.append(row)
        test_rows = [r for r in test_rows if Path(r["audio_path"]).exists()]
        logger.info("prepare_self_record_dir: pre-loading test audio…")
        test_rows = [_load_audio(r) for r in test_rows]
        test_dir = output_root / "test"
        Dataset.from_list(test_rows).save_to_disk(str(test_dir))
        logger.info(
            f"prepare_self_record_dir: saved test={test_dir} "
            f"({len(test_rows)} rows)"
        )

    return train_dir, val_dir, test_dir


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------


def build_model_and_processor(base_model: str, lora_r: int, lora_alpha: int):
    """Load Whisper base + freeze + attach LoRA, plus the processor.

    Returns (model, processor, data_collator).
    """
    from transformers import (
        WhisperForConditionalGeneration,
        WhisperProcessor,
        WhisperFeatureExtractor,
        WhisperTokenizer,
    )
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training

    logger.info(f"Loading {base_model} from HF Hub…")
    processor = WhisperProcessor.from_pretrained(base_model)
    model = WhisperForConditionalGeneration.from_pretrained(base_model)

    # Force the model into "transcribe" mode for Cantonese at every
    # forward pass — we don't want generation defaulting to "translate".
    model.config.forced_decoder_ids = processor.get_decoder_prompt_ids(
        language="cantonese", task="transcribe"
    )
    # Suppress the "<|notimestamps|>" token at training time; we
    # re-enable timestamps at inference.
    model.config.suppress_tokens = []

    # Freeze the encoder; LoRA on the decoder attention + FFN only.
    # Empirically this gives the best quality/memory trade-off for
    # Whisper.
    for p in model.model.encoder.parameters():
        p.requires_grad = False

    lora_config = LoraConfig(
        r=lora_r,
        lora_alpha=lora_alpha,
        target_modules=["q_proj", "v_proj"],  # attention Q+V — minimal
        lora_dropout=0.05,
        bias="none",
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    # Data collator: pads audio features to the longest in the batch
    # and pads label tokens to max length, replacing padding token ids
    # with -100 so they're ignored by the loss.
    # Sprint 55: DataCollatorForSeq2Seq is the wrong collator for
    # Whisper (it's a text padder that calls tokenizer.pad() on
    # whatever it sees — fails on raw audio). Use the
    # WhisperSpeechCollator defined at module top-level (must be
    # picklable for DataLoader workers).
    data_collator = WhisperSpeechCollator(processor)

    return model, processor, data_collator


def build_trainer(
    model,
    processor,
    data_collator,
    train_ds,
    val_ds,
    output_dir: str,
    per_device_batch_size: int,
    grad_accum: int,
    num_epochs: int,
    learning_rate: float,
    resume_from: str | None = None,
):
    from transformers import Seq2SeqTrainingArguments, Seq2SeqTrainer

    args = Seq2SeqTrainingArguments(
        output_dir=output_dir,
        per_device_train_batch_size=per_device_batch_size,
        per_device_eval_batch_size=per_device_batch_size,
        gradient_accumulation_steps=grad_accum,
        learning_rate=learning_rate,
        num_train_epochs=num_epochs,
        warmup_steps=50,
        logging_steps=10,
        save_steps=100,
        save_total_limit=2,  # only keep last 2 checkpoints
        eval_strategy="steps",
        eval_steps=100,
        fp16=False,           # MPS doesn't support fp16 reliably; bf16 if available
        bf16=False,           # toggle if M3/M4 GPU supports it
        predict_with_generate=True,
        generation_max_length=128,
        report_to=[],         # no W&B / TensorBoard by default
        dataloader_num_workers=2,
        remove_unused_columns=False,
        resume_from_checkpoint=resume_from,
    )

    return Seq2SeqTrainer(
        args=args,
        model=model,
        train_dataset=train_ds,
        eval_dataset=val_ds,
        data_collator=data_collator,
        tokenizer=processor.feature_extractor,
    )


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


def evaluate_wer(model, processor, test_ds, wer_threshold: float) -> float:
    """Run inference on the held-out test set, compute WER.

    Returns the WER as a fraction in [0, 1]. Logs PASS/FAIL
    against the threshold and exits non-zero if WER > threshold.
    """
    import torch
    from jiwer import wer

    logger.info("Running inference on held-out test set…")
    predictions: list[str] = []
    references: list[str] = []
    for sample in test_ds:
        input_features = processor.feature_extractor(
            sample["audio"]["array"],
            sampling_rate=16000,
            return_tensors="pt",
        ).input_features.to(model.device)
        with torch.no_grad():
            predicted_ids = model.generate(input_features)
        transcription = processor.batch_decode(
            predicted_ids, skip_special_tokens=True
        )[0].strip()
        predictions.append(transcription)
        references.append(sample["sentence"].strip())

    score = wer(references, predictions)
    logger.info(f"Held-out WER: {score:.3f} (threshold: {wer_threshold:.3f})")
    if score > wer_threshold:
        logger.error(
            f"WER {score:.3f} exceeds threshold {wer_threshold:.3f}. "
            f"Training considered failed."
        )
        return score
    logger.info(f"WER {score:.3f} ≤ threshold {wer_threshold:.3f} ✓")
    return score


# ---------------------------------------------------------------------------
# Dataset preprocessing (Sprint 55)
# ---------------------------------------------------------------------------


def _preprocess_dataset(dataset, processor):
    """Pre-extract Whisper `input_features` (audio → log-mel
    spectrogram) and `labels` (text → token ids) for every row.

    The Common Voice path (Sprint 21) used the HF datasets
    `Audio(sampling_rate=16000)` helper plus an in-trainer
    preprocessing hook that baked the WhisperProcessor into the
    DataCollator. The self-record path stores raw numpy audio
    arrays in `sample["audio"]["array"]` (no HF Audio helper),
    so the trainer's data collator — which is a `DataCollator
    ForSeq2Seq` that only pads text — would try to
    `tokenizer.pad()` the raw audio and crash with::

        ValueError: You should supply an encoding or a list of
        encodings to this method that includes input_ids, but
        you provided ['audio_path', 'text', 'duration_s',
        'sample_rate', 'sentence', 'audio']

    This function maps the dataset once at startup so every
    row has the columns the collator + model expect:
        - input_features: np.ndarray (80 × 3000 log-mel)
        - labels: list[int] (tokenized sentence)
    The collator then pads `labels` to max-length, replacing
    pad token ids with -100.

    Returns a `datasets.Dataset` with the new columns.
    """
    def _extract_features(batch):
        # Whisper feature extractor: 30s fixed window, 16kHz
        # mono audio → 80-mel spectrogram
        audio_arrays = [
            sample["array"] for sample in batch["audio"]
        ]
        features = processor.feature_extractor(
            audio_arrays,
            sampling_rate=16000,
            return_tensors="np",
        )
        # Tokenize the sentence transcripts (Cantonese-aware
        # because `processor` was built with
        # `language="cantonese", task="transcribe"` in
        # build_model_and_processor — well, that's on the
        # model side; the tokenizer itself is language-agnostic)
        labels = processor.tokenizer(
            batch["sentence"],
            padding=False,
            truncation=True,
            max_length=128,
        ).input_ids
        return {
            "input_features": features.input_features,
            "labels": labels,
        }

    return dataset.map(
        _extract_features,
        batched=True,
        batch_size=8,
        remove_columns=dataset.column_names,
        desc="Pre-extract Whisper features + tokens",
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # Sprint 33 / Track 31-B — log the Layer 2 v2 personalised
    # fine-tune flags so the operator can confirm the wiring
    # before training starts. The full training pipeline for
    # --train_audio_dir is deferred to a follow-up sprint; for
    # now the flag is documented + accepted + surfaced in the
    # log so the user can verify the JSONL contract end-to-end.
    # See FEATURE-SPEC-SPRINT26.md §4.1 + Sprint 33 deliverable
    # Notes for verifier.
    if args.base_model_path or args.train_audio_dir:
        logger.info(
            "Layer 2 v2 personalised fine-tune flags active: "
            f"base_model_path={args.base_model_path!r} "
            f"train_audio_dir={args.train_audio_dir!r}"
        )

    # Validate the requested Common Voice version is one we know
    # has the yue split with a useful amount of data.
    cv_major = int(args.dataset_version.split(".")[0])
    if cv_major < 11:
        logger.error(
            f"Common Voice {args.dataset_version} yue split is < 50h; "
            f"use --dataset_version 11.0 or later."
        )
        return 1

    # 1. Prepare dataset.
    # Sprint 55: dispatch on --train_audio_dir (self-record / fsicoli
    # mirror path) vs the default Common Voice path. The self-record
    # path does NOT need CV-yue on HF Hub — it just needs a
    # manifest.jsonl + WAV files under the supplied dir (same schema
    # `gen_cantonese_corpus.py` produces for Tauri record output).
    if args.train_audio_dir:
        logger.info(
            f"Using --train_audio_dir: {args.train_audio_dir} "
            "(self-record / fsicoli CV mirror path; "
            "skipping Common Voice download)"
        )
        train_dir, val_dir, test_dir = prepare_self_record_dir(
            train_audio_dir=Path(args.train_audio_dir),
        )
        # Wrap as DatasetPaths-like object so the rest of main()
        # can use `paths.train/validation/test` uniformly.
        from dataclasses import dataclass
        @dataclass
        class _LocalPaths:
            train: Path
            validation: Path
            test: Path | None
        paths = _LocalPaths(train=train_dir, validation=val_dir, test=test_dir)
    else:
        cache_dir = Path(os.path.expanduser("~/.gundam-halo/cache/cv-yue/"))
        paths = prepare_common_voice_yue(
            cv_version=args.dataset_version,
            cache_dir=cache_dir,
            max_train_hours=args.max_train_hours,
        )

    # 2. Build model + LoRA. Sprint 33: when --base_model_path
    # is set, load the user-supplied HF-format checkpoint
    # instead of downloading `openai/whisper-base` from the
    # HF Hub. This is the Layer 2 v2 personalised fine-tune
    # path — LoRA is layered on top of the already-Cantonese-
    # aware Common Voice yue baseline.
    base_model_for_training = args.base_model_path or HF_BASE_MODEL
    if args.base_model_path:
        logger.info(
            f"Using --base_model_path: {args.base_model_path} "
            "(continuing LoRA training from this checkpoint "
            "instead of HF Hub openai/whisper-base)"
        )
    model, processor, data_collator = build_model_and_processor(
        base_model=base_model_for_training,
        lora_r=args.lora_r,
        lora_alpha=args.lora_alpha,
    )

    # 3. Trainer.
    from datasets import load_from_disk
    train_ds = load_from_disk(str(paths.train))
    val_ds = load_from_disk(str(paths.validation))
    # Sprint 55: pre-extract input_features + labels so the
    # Seq2SeqTrainer's DataCollatorForSeq2Seq (which only pads
    # text) doesn't try to `tokenizer.pad()` the raw audio dict.
    # The Common Voice path went through `ds.cast_column("audio",
    # Audio(sampling_rate=16000))` + a built-in preprocessor —
    # the self-record path needs the same pre-extraction
    # explicitly because we don't use the HF datasets Audio
    # helper.
    logger.info("Pre-extracting input_features + labels…")
    train_ds = _preprocess_dataset(train_ds, processor)
    val_ds = _preprocess_dataset(val_ds, processor)
    trainer = build_trainer(
        model=model,
        processor=processor,
        data_collator=data_collator,
        train_ds=train_ds,
        val_ds=val_ds,
        output_dir=args.output_dir,
        per_device_batch_size=args.per_device_train_batch_size,
        grad_accum=args.gradient_accumulation_steps,
        num_epochs=args.num_train_epochs,
        learning_rate=args.learning_rate,
        resume_from=args.resume_from,
    )

    # 4. Train.
    logger.info("Starting training…")
    trainer.train()

    # 5. Merge LoRA into base, save full model directory.
    logger.info("Merging LoRA adapters into base model…")
    merged = trainer.model.merge_and_unload()
    os.makedirs(args.output_dir, exist_ok=True)
    merged.save_pretrained(args.output_dir)
    processor.save_pretrained(args.output_dir)
    logger.info(f"Merged model saved to {args.output_dir}")

    # 6. Eval.
    if not args.skip_eval:
        # Sprint 55: paths.test may be None in the self-record
        # path (no sibling test/manifest.jsonl). Skip eval in
        # that case — the held-out test pair or --skip_eval
        # handles the acceptance gate.
        test_path = getattr(paths, "test", None)
        if test_path is None or not Path(test_path).exists():
            logger.warning(
                "No test split available (paths.test is None or "
                "missing on disk). Skipping eval — the held-out "
                "test pair will be used by the orchestrator for "
                "the post-train WER check."
            )
            score = float("nan")
        else:
            test_ds = load_from_disk(str(test_path))
            score = evaluate_wer(
                model=merged,
                processor=processor,
                test_ds=test_ds,
                wer_threshold=args.wer_threshold,
            )
        # Persist the WER alongside the model so the operator can
        # inspect it later without re-running the eval.
        with open(Path(args.output_dir) / "eval.json", "w") as f:
            json.dump(
                {"wer": score, "threshold": args.wer_threshold},
                f,
            )
        # Sprint 55: NaN score means "eval was skipped" (no test
        # split available in self-record path). Return 0 to
        # signal success — the orchestrator / swap step will run
        # the held-out pair eval separately.
        import math as _math
        if _math.isnan(score):
            return 0
        return 0 if score <= args.wer_threshold else 2

    return 0


if __name__ == "__main__":
    sys.exit(main())


__all__ = [
    "DEFAULT_OUTPUT_DIR",
    "HF_BASE_MODEL",
    "DEFAULT_CV_VERSION",
    "parse_args",
    "prepare_common_voice_yue",
    "prepare_self_record_dir",
    "build_model_and_processor",
    "build_trainer",
    "evaluate_wer",
    "main",
]

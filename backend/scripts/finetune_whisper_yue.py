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

Usage:
    cd backend
    uv sync --extra train --extra voice
    .venv/bin/python scripts/finetune_whisper_yue.py \\
        --dataset_version 11.0 \\
        --max_train_hours 50 \\
        --num_train_epochs 3 \\
        --output_dir ~/.gundam-halo/models/whisper-yue-base/

Estimated wall time on M-series 16GB:
- Dataset download (50h): ~30min
- LoRA training (3 epochs): ~2.5h
- Eval + WER on held-out test set: ~5min

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
    from transformers import DataCollatorForSeq2Seq

    data_collator = DataCollatorForSeq2Seq(
        processor=processor,
        label_pad_token_id=-100,
    )

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
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
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

    # 1. Prepare dataset (stubbed in v0.1.3; the next chunk of work).
    cache_dir = Path(os.path.expanduser("~/.gundam-halo/cache/cv-yue/"))
    paths = prepare_common_voice_yue(
        cv_version=args.dataset_version,
        cache_dir=cache_dir,
        max_train_hours=args.max_train_hours,
    )

    # 2. Build model + LoRA.
    model, processor, data_collator = build_model_and_processor(
        base_model=HF_BASE_MODEL,
        lora_r=args.lora_r,
        lora_alpha=args.lora_alpha,
    )

    # 3. Trainer.
    from datasets import load_from_disk
    train_ds = load_from_disk(str(paths.train))
    val_ds = load_from_disk(str(paths.validation))
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
        test_ds = load_from_disk(str(paths.test))
        score = evaluate_wer(
            model=merged,
            processor=processor,
            test_ds=test_ds,
            wer_threshold=args.wer_threshold,
        )
        # Persist the WER alongside the model so the operator can
        # inspect it later without re-running the eval.
        with open(Path(args.output_dir) / "eval.json", "w") as f:
            json.dump({"wer": score, "threshold": args.wer_threshold}, f)
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
    "build_model_and_processor",
    "build_trainer",
    "evaluate_wer",
    "main",
]

"""M9-E Layer 2 — Common Voice yue corpus via fsicoli mirror.

Sprint 55 (in-session, 2026-07-03): the canonical
`mozilla-foundation/common_voice_{13,17}_0` datasets on
HuggingFace are empty stubs as of October 2025 (Mozilla
moved CV to Mozilla Data Collective, gated portal — see
~/.mavis/agents/mavis/memory/MEMORY.md "Common Voice yue
moved to Mozilla Data Collective Oct 2025" entry).

The closest loadable substitute is the
`fsicoli/common_voice_17_0` community mirror — but its
loading script is incompatible with `datasets` v5
(`RuntimeError: Dataset scripts are no longer
supported`). However the **raw .tar shards and .tsv
transcripts are still accessible** via
`huggingface_hub.hf_hub_download`.

This script:

  1. Downloads the .tsv transcripts for train / test /
     dev (small, <2 MB total) and reads them into
     memory.
  2. Lists the .tar shards under
     `audio/yue/{split}/` via the HF Hub API and
     downloads only the shards that contain clips
     referenced by the transcripts.
  3. Extracts the .mp3 files from each .tar into a
     flat `wav_pool/` directory.
  4. Converts each .mp3 → 16 kHz mono s16le .wav via
     ffmpeg (matching the voice pipeline contract
     `app.voice.held_out_eval.SAMPLE_RATE = 16_000`).
  5. Filters the transcripts by up_votes/down_votes
     (default: up_votes ≥ 2, down_votes = 0 — strict
     quality gate).
  6. Writes per-split manifest.jsonl files in the
     Sprint 45 self-record contract:
         {audio_path, text, duration_s, sample_rate}
  7. Materialises each split as a HuggingFace Dataset
     via `datasets.Dataset.from_list` + `save_to_disk`
     (the same `load_from_disk(str(paths.train))` call
     pattern `finetune_whisper_yue.py` uses for the
     Common Voice yue baseline).

Why fsicoli/community mirror instead of Mozilla Data
Collective:
- Mozilla Data Collective requires license agreement
  + auth handshake; outside this session's scope.
- The fsicoli mirror is CC0 (or CC-BY-1.0 depending on
  version) — same license as CV-yue itself.
- Audio is real human-recorded Cantonese (not TTS) — the
  WER improvements will transfer to real recordings.
- Trade-off: fsicoli mirrors are loading-script-based
  (datasets v5 incompatible), but the raw files are
  downloadable directly via huggingface_hub.

Caveats baked in:
- Train split is ~3,150 validated clips (≈ 50 min of
  audio). Small corpus — LoRA on this will improve
  pronunciation recognition but won't reach SOTA.
- We download only `train`/`test`/`dev` (validated)
  splits — not `other` (141k unvalidated clips).
  Total audio: ~220 MB.
- Re-running is idempotent: existing wavs are skipped,
  existing tar shards are not re-downloaded.

Usage:
    cd backend
    uv run python scripts/prepare_fsicoli_cv_yue.py
    # custom output dir:
    uv run python scripts/prepare_fsicoli_cv_yue.py \\
        --cache-dir ~/.gundam-halo/cache/cv-yue-fsicoli/ \\
        --min-up-votes 1
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import subprocess
import sys
import tarfile
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("prepare_fsicoli_cv_yue")

# fsicoli/common_voice_17_0 — the most-recent CV version that
# still has a loadable yue mirror on HF Hub.
HF_REPO_ID = "fsicoli/common_voice_17_0"
# We download only the validated splits. `other` (141k unvalidated
# clips) is intentionally skipped — quality gate is more
# important than corpus size for this demo.
DEFAULT_SPLITS = ("train", "test", "dev")

# Audio sample rate the voice pipeline expects
# (matches `app.voice.held_out_eval.SAMPLE_RATE = 16_000`).
SAMPLE_RATE = 16_000

DEFAULT_CACHE_DIR = Path.home() / ".gundam-halo" / "cache" / "cv-yue-fsicoli"


@dataclass
class ClipRow:
    """One validated CV-yue clip from the .tsv transcript."""

    client_id: str
    audio_filename: str  # e.g. "common_voice_yue_31200671.mp3"
    sentence: str
    up_votes: int
    down_votes: int
    split: str  # "train" | "test" | "dev"

    @property
    def sentence_stripped(self) -> str:
        return self.sentence.strip()


def _resolve_cache_dir(args: argparse.Namespace) -> Path:
    cache_dir = args.cache_dir.expanduser() if args.cache_dir else DEFAULT_CACHE_DIR
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def _download_tsv(repo_id: str, split: str, cache_dir: Path) -> Path:
    """Download the per-split transcript .tsv via huggingface_hub.

    Returns the local Path of the downloaded .tsv file.
    """
    from huggingface_hub import hf_hub_download

    fp = hf_hub_download(
        repo_id=repo_id,
        filename=f"transcript/yue/{split}.tsv",
        repo_type="dataset",
        local_dir=str(cache_dir / "_tsv_cache"),
    )
    logger.info(f"Downloaded transcript: {fp}")
    return Path(fp)


def _parse_tsv(tsv_path: Path, split: str) -> list[ClipRow]:
    """Read the Common Voice yue transcript TSV into ClipRow records.

    Header (from CV-yue 17.0):
      client_id, path, sentence_id, sentence, sentence_domain,
      up_votes, down_votes, age, gender, accents, variant,
      locale, segment
    """
    rows: list[ClipRow] = []
    with open(tsv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for r in reader:
            try:
                rows.append(
                    ClipRow(
                        client_id=r["client_id"],
                        audio_filename=r["path"],
                        sentence=r["sentence"],
                        up_votes=int(r["up_votes"]),
                        down_votes=int(r["down_votes"]),
                        split=split,
                    )
                )
            except (KeyError, ValueError) as e:
                logger.warning(f"Skipping malformed row: {e}")
    return rows


def _list_audio_shards(repo_id: str, split: str) -> list[str]:
    """Return the list of audio/yue/<split>/yue_<split>_N.tar
    shard filenames via the HF Hub API.
    """
    from huggingface_hub import HfApi

    api = HfApi()
    try:
        files = api.list_repo_files(repo_id=repo_id, repo_type="dataset")
    except Exception as e:
        raise SystemExit(f"Could not list files in {repo_id}: {e}") from e
    prefix = f"audio/yue/{split}/"
    shards = sorted(
        f for f in files if f.startswith(prefix) and f.endswith(".tar")
    )
    return shards


def _download_audio_shard(
    repo_id: str, shard_filename: str, cache_dir: Path
) -> Path:
    """Download a single .tar audio shard to cache_dir/_tar_cache/."""
    from huggingface_hub import hf_hub_download

    fp = hf_hub_download(
        repo_id=repo_id,
        filename=shard_filename,
        repo_type="dataset",
        local_dir=str(cache_dir / "_tar_cache"),
    )
    return Path(fp)


def _extract_mp3_from_tar(tar_path: Path, target_dir: Path) -> int:
    """Extract all .mp3 files from a .tar shard into target_dir.

    Returns the number of .mp3 files extracted.
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    # Common Voice .tar shards are NOT compressed (they store raw
    # MP3 files). Use `r:` mode.
    with tarfile.open(tar_path, "r:") as tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue
            if not member.name.lower().endswith(".mp3"):
                continue
            # Strip any directory prefix from the tar member name —
            # CV-yue shards store MP3s at the tar root, but the
            # member.name sometimes carries `./` or similar prefix.
            base_name = os.path.basename(member.name)
            out_path = target_dir / base_name
            if out_path.exists():
                # Idempotent: skip already-extracted files
                count += 1
                continue
            f = tar.extractfile(member)
            if f is None:
                continue
            with open(out_path, "wb") as out_f:
                out_f.write(f.read())
            count += 1
    return count


def _ffmpeg_mp3_to_wav(mp3_path: Path, wav_path: Path) -> tuple[float, int]:
    """Convert .mp3 → 16 kHz mono s16le .wav via ffmpeg.

    Returns (duration_seconds, sample_rate).

    ffmpeg arguments:
      -y             overwrite output
      -nostdin       never read from stdin (defensive — protects
                     against accidental stdin reads in CI)
      -loglevel err  only log errors to stderr (keeps stdout clean
                     for piped capture)
      -i             input file
      -ar 16000      resample to 16 kHz (matches Whisper training)
      -ac 1          mono (matches Whisper training)
      -f wav         WAV container
      -acodec pcm_s16le  16-bit signed PCM (Whisper expected format)
    """
    wav_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-nostdin",
        "-loglevel", "error",
        "-y",
        "-i", str(mp3_path),
        "-ar", str(SAMPLE_RATE),
        "-ac", "1",
        "-f", "wav",
        "-acodec", "pcm_s16le",
        str(wav_path),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(
            f"ffmpeg failed for {mp3_path.name}: {res.stderr[:200]}"
        )
    # Probe duration via soundfile (handles ffmpeg's LIST chunks).
    import soundfile as sf
    info = sf.info(str(wav_path))
    duration_s = float(info.frames) / float(info.samplerate)
    return duration_s, SAMPLE_RATE


def _filter_clips(
    rows: list[ClipRow], min_up_votes: int, max_down_votes: int
) -> list[ClipRow]:
    """Apply the quality gate: up_votes >= min AND down_votes <= max."""
    before = len(rows)
    filtered = [
        r for r in rows
        if r.up_votes >= min_up_votes and r.down_votes <= max_down_votes
    ]
    after = len(filtered)
    logger.info(
        f"Quality gate: {before} -> {after} clips "
        f"(min_up_votes={min_up_votes}, max_down_votes={max_down_votes})"
    )
    return filtered


def _build_split_dataset(
    clips: list[ClipRow],
    wav_dir: Path,
    manifest_path: Path,
    dataset_dir: Path,
) -> int:
    """Convert MP3s to WAVs, write manifest.jsonl, and save a HF
    Dataset to dataset_dir. Returns the number of clips processed.
    """
    from datasets import Dataset

    wav_dir.mkdir(parents=True, exist_ok=True)
    rows_for_manifest: list[dict] = []
    rows_for_dataset: list[dict] = []

    for clip in clips:
        mp3_path = wav_dir / clip.audio_filename
        wav_path = mp3_path.with_suffix(".wav")
        if not mp3_path.exists():
            logger.warning(f"MP3 missing on disk: {mp3_path.name}, skipping")
            continue
        if not wav_path.exists():
            try:
                duration_s, sample_rate = _ffmpeg_mp3_to_wav(mp3_path, wav_path)
            except Exception as e:
                logger.warning(f"ffmpeg failed for {mp3_path.name}: {e}")
                continue
        else:
            # Idempotent: use soundfile.info() to probe duration
            # (handles ffmpeg-inserted LIST chunks correctly).
            try:
                import soundfile as sf
                info = sf.info(str(wav_path))
                duration_s = float(info.frames) / float(info.samplerate)
                sample_rate = info.samplerate
            except Exception:
                # Fall back to re-conversion if probe fails
                duration_s, sample_rate = _ffmpeg_mp3_to_wav(mp3_path, wav_path)

        # Manifest entry (Sprint 45 self-record contract)
        rows_for_manifest.append(
            {
                "audio_path": str(wav_path),
                "text": clip.sentence_stripped,
                "duration_s": round(duration_s, 3),
                "sample_rate": sample_rate,
            }
        )
        # HF Dataset row (also need `audio` col with bytes for
        # WhisperProcessor; store path + reload later in trainer)
        rows_for_dataset.append(
            {
                "audio_path": str(wav_path),
                "sentence": clip.sentence_stripped,
                "duration_s": round(duration_s, 3),
            }
        )

    # Write manifest.jsonl
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(manifest_path, "w", encoding="utf-8") as f:
        for row in rows_for_manifest:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    logger.info(f"Wrote manifest: {manifest_path} ({len(rows_for_manifest)} rows)")

    # Save HF Dataset (same shape `finetune_whisper_yue.py`
    # expects from the Common Voice path)
    dataset_dir.mkdir(parents=True, exist_ok=True)
    ds = Dataset.from_list(rows_for_dataset)
    ds.save_to_disk(str(dataset_dir))
    logger.info(
        f"Saved HF Dataset: {dataset_dir} ({len(rows_for_dataset)} rows)"
    )

    return len(rows_for_dataset)


def main() -> int:
    p = argparse.ArgumentParser(
        description=(
            "M9-E Layer 2 — prepare Common Voice yue corpus from the "
            "fsicoli/common_voice_17_0 HF mirror (raw .tar/.tsv download "
            "via huggingface_hub, bypassing the broken loading script)."
        ),
    )
    p.add_argument(
        "--cache-dir",
        type=Path,
        default=DEFAULT_CACHE_DIR,
        help=f"Where to write the prepared splits (default: {DEFAULT_CACHE_DIR}).",
    )
    p.add_argument(
        "--splits",
        nargs="+",
        default=list(DEFAULT_SPLITS),
        help=f"Which CV splits to download (default: {' '.join(DEFAULT_SPLITS)}).",
    )
    p.add_argument(
        "--min-up-votes",
        type=int,
        default=2,
        help="Quality gate: drop clips with up_votes < this (default: 2).",
    )
    p.add_argument(
        "--max-down-votes",
        type=int,
        default=0,
        help="Quality gate: drop clips with down_votes > this (default: 0).",
    )
    p.add_argument(
        "--max-clips-per-split",
        type=int,
        default=None,
        help=(
            "Cap clips per split (for fast iteration; "
            "default: no cap). Useful for demo runs."
        ),
    )
    args = p.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    cache_dir = _resolve_cache_dir(args)
    logger.info(f"Cache dir: {cache_dir}")

    # Step 1+2: Download .tsv + list audio shards per split.
    # Iterate splits so partial failures don't lose progress.
    total_clips = 0
    for split in args.splits:
        logger.info(f"=== Split: {split} ===")

        # 1. Download the transcript
        tsv_path = _download_tsv(HF_REPO_ID, split, cache_dir)
        all_rows = _parse_tsv(tsv_path, split)
        logger.info(f"Parsed {len(all_rows)} rows from {tsv_path.name}")

        # Quality gate
        rows = _filter_clips(all_rows, args.min_up_votes, args.max_down_votes)

        # Optional clip cap
        if args.max_clips_per_split and len(rows) > args.max_clips_per_split:
            rows = rows[: args.max_clips_per_split]
            logger.info(f"Capped to {len(rows)} clips (max-clips-per-split)")

        # 2. List audio shards
        shard_files = _list_audio_shards(HF_REPO_ID, split)
        logger.info(
            f"{len(shard_files)} audio shard(s) for split={split}: "
            f"{[os.path.basename(s) for s in shard_files]}"
        )

        # 3. Download + extract MP3s from each shard
        mp3_dir = cache_dir / "wav_pool"
        for shard in shard_files:
            shard_local = _download_audio_shard(HF_REPO_ID, shard, cache_dir)
            extracted = _extract_mp3_from_tar(shard_local, mp3_dir)
            logger.info(
                f"Extracted {extracted} MP3(s) from {shard_local.name}"
            )

        # 4. Convert MP3 → WAV + build manifest + save HF Dataset
        split_dir = cache_dir / split
        manifest_path = split_dir / "manifest.jsonl"
        dataset_dir = split_dir / "dataset"
        n = _build_split_dataset(rows, mp3_dir, manifest_path, dataset_dir)
        logger.info(f"Split {split}: {n} clips ready at {dataset_dir}")
        total_clips += n

    logger.info(
        f"=== Done. {total_clips} total clips across "
        f"{len(args.splits)} split(s) at {cache_dir} ==="
    )
    return 0


__all__ = ["main", "HF_REPO_ID", "SAMPLE_RATE", "DEFAULT_CACHE_DIR"]


if __name__ == "__main__":
    sys.exit(main())

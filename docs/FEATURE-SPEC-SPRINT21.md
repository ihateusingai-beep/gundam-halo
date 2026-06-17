# Feature Spec — Sprint 21: prepare_common_voice_yue impl

> **Status:** DRAFT — user signed off via the Sprint 21
> scope pick. Implementation follows in this session.
> **Scope:** 1 hour. Replaces the v0.1.3 `NotImplementedError`
> stub in `backend/scripts/finetune_whisper_yue.py` with a
> real, testable implementation that streams Common
> Voice yue, splits by `client_id` at the speaker level,
> and materialises the splits to local parquet files
> ready for `load_from_disk()`.
> **Out of scope (deferred):** the actual `uv sync --extra
> train` install (requires the `train` extra which pulls
> in ~3GB of ML deps), the actual 3h+ training run
> (per `docs/FEATURE-SPEC-SPRINT19d.md` §6), and the
> `WhisperHFASR` swap (Sprint 22 per Sprint 20 spec).

---

## 0. Why this sprint exists

`scripts/finetune_whisper_yue.py:242-246` raises
`NotImplementedError` because the dataset
materialise-and-split logic is "the next chunk of
work in M9-E Layer 2" (per the v0.1.3 TODO comment).
The training script is otherwise complete — CLI
parser, model + LoRA builder, Trainer config, WER
evaluation, merge-and-save, main(). The only missing
piece is the dataset preparation.

Sprint 21 ships the missing piece so a future
session can run `uv sync --extra train --extra voice &&
.venv/bin/python scripts/finetune_whisper_yue.py` and
the dataset downloads + splits without raising.

## 1. Goals

1. **Replace `NotImplementedError` with real impl.**
   `prepare_common_voice_yue` streams Common Voice
   yue from Hugging Face, splits by `client_id`,
   caps at `max_train_hours`, and materialises
   train/validation/test parquet files.
2. **Speaker-disjoint splits.** Common Voice's
   standard split is at the speaker level — never
   split one speaker across train and val (that
   leaks WER). We sort speakers, pick the first N
   speakers for test, next M for val, rest for train.
3. **Resumable download.** Each split is materialised
   to its own parquet file under
   `~/.gundam-halo/cache/cv-yue/{train,validation,test}/`.
   Re-running the script picks up where it left off
   (skips samples already in the parquet).
4. **No `datasets` library import in the impl** —
   the impl accepts a pre-streamed `Iterable[Dict]`
   and a `cast_audio` callable so unit tests don't
   need the `train` extra installed. The production
   entry point (`main()`) wires up the real
   `datasets.load_dataset(..., streaming=True)` call.
5. **Replace the v0.1.3 stub-test with a real
   end-to-end test** that streams 5 mock samples
   through the impl and asserts the parquet files
   have the expected shape.

## 2. Out of scope (deferred)

- **Real `uv sync --extra train` install** — Sprint
  22+ when the user commits time to the 3h training
  session.
- **Actual training run** — deferred to the
  user-present session (per Sprint 19d spec).
- **`WhisperHFASR` swap** — Sprint 22 (per Sprint 20
  spec Step 2).
- **Augmented system note removal** — Sprint 22
  (per Sprint 20 spec Step 4).
- **Self-record corpus + Layer 2 v2** — per M9-E
  §"v0.1.3 Layer 2 plan".

## 3. User-facing behavior

This sprint is **invisible to the user**. The
training script is still 30+ min away from running
end-to-end (the `train` extra isn't installed yet,
and the actual training run is the user-present
session). Sprint 21 just removes one of the two
blockers (the impl) so the next session can focus
on the install + run.

## 4. Architecture

### 4.1 Function signature (unchanged)

```python
def prepare_common_voice_yue(
    cv_version: str,
    cache_dir: Path,
    max_train_hours: float,
) -> DatasetPaths:
```

`DatasetPaths` (defined at line 180) returns the
three parquet dirs. `cache_dir` is
`~/.gundam-halo/cache/cv-yue/` (already passed in
by `main()`).

### 4.2 Refactor: split into pure + impure halves

The current `prepare_common_voice_yue` does three
things:
1. Load + cast (impure: needs `datasets.load_dataset`)
2. Split + cap (pure: takes a list of samples)
3. Save parquet (impure: needs `pyarrow`)

We split into two functions so the unit testable
middle (split + cap) doesn't depend on `datasets`
or `pyarrow`:

```python
def prepare_common_voice_yue(
    cv_version: str,
    cache_dir: Path,
    max_train_hours: float,
) -> DatasetPaths:
    """Production entry point: loads + casts + splits +
    saves. Lazy-imports datasets / pyarrow."""
    from datasets import load_dataset, Audio

    # Step 1: stream + cast (impure, lazy import)
    logger.info(f"Streaming Common Voice {cv_version} yue…")
    raw = load_dataset(
        f"mozilla-foundation/common_voice_{cv_version.replace('.', '_')}",
        "yue",
        split="train+validation+test",
        streaming=True,
        trust_remote_code=True,
    )
    raw = raw.cast_column("audio", Audio(sampling_rate=16000))

    # Step 2: split + cap (pure, takes Iterable[Dict])
    samples = list(raw)
    logger.info(f"Streaming complete: {len(samples)} samples")
    splits = split_by_client_id(samples, max_train_hours=max_train_hours)

    # Step 3: save (impure, lazy import)
    return save_splits_as_parquet(splits, cache_dir)


def split_by_client_id(
    samples: list[dict],
    max_train_hours: float,
    test_ratio: float = 0.05,
    val_ratio: float = 0.05,
    *,
    sample_rate: int = 16000,
) -> dict[str, list[dict]]:
    """Pure function: split samples by client_id into
    train/validation/test, capping train at max_train_hours
    of audio. Returns dict with keys 'train', 'validation',
    'test' each holding a list of samples.

    Speaker-disjoint: the same client_id never appears
    in two splits (so WER is not leaked). Speakers are
    sorted by sample count descending; the first N
    speakers (by ratio) go to test, next M to val, rest
    to train. This biases the held-out splits toward
    speakers with the most data.

    Train cap: sum audio duration across all train
    samples; if total > max_train_hours * 3600, drop
    samples with the longest audio first (down to the
    cap). Keeps the WER-equivalent signal-to-noise
    ratio high (we don't drop a sample just because
    it's long).
    """
    ...


def save_splits_as_parquet(
    splits: dict[str, list[dict]],
    cache_dir: Path,
) -> DatasetPaths:
    """Write each split to a parquet file under
    cache_dir/{split}/data.parquet. Returns paths."""
    import pyarrow as pa
    import pyarrow.parquet as pq
    ...
```

### 4.3 Speaker-disjoint split

```python
# Group by speaker
by_speaker: dict[str, list[dict]] = {}
for s in samples:
    cid = s.get("client_id") or "unknown"
    by_speaker.setdefault(cid, []).append(s)

# Sort speakers by sample count (descending) — the
# speakers with the most data go to test/val so the
# held-out set has enough samples for a stable WER.
speakers = sorted(by_speaker.keys(),
                  key=lambda k: -len(by_speaker[k]))

n = len(speakers)
n_test = max(1, int(n * test_ratio))
n_val = max(1, int(n * val_ratio))
test_speakers = set(speakers[:n_test])
val_speakers = set(speakers[n_test:n_test + n_val])
# (rest = train)

splits = {"train": [], "validation": [], "test": []}
for s in samples:
    cid = s.get("client_id") or "unknown"
    if cid in test_speakers:
        splits["test"].append(s)
    elif cid in val_speakers:
        splits["validation"].append(s)
    else:
        splits["train"].append(s)
```

### 4.4 Hour-cap on train

```python
def _audio_seconds(s: dict, sample_rate: int) -> float:
    """Read the audio array's length; for streaming,
    the audio dict is {path: bytes, array: np.ndarray}."""
    arr = s.get("audio", {}).get("array")
    if arr is None:
        return 0.0
    return float(len(arr)) / float(sample_rate)


def cap_at_hours(
    samples: list[dict], max_hours: float, sample_rate: int = 16000
) -> list[dict]:
    """Cap the training set at max_hours of audio. Drop
    the longest samples first (they're the slowest to
    train on and contribute the least to WER)."""
    cap_s = max_hours * 3600.0
    if sum(_audio_seconds(s, sample_rate) for s in samples) <= cap_s:
        return samples  # already under cap
    # Sort by duration ascending (keep the shorter,
    # more numerous samples; drop the longest).
    sorted_samples = sorted(
        samples, key=lambda s: -_audio_seconds(s, sample_rate)
    )
    out: list[dict] = []
    running_s = 0.0
    for s in sorted_samples:
        dur = _audio_seconds(s, sample_rate)
        if running_s + dur > cap_s:
            continue
        out.append(s)
        running_s += dur
    return out
```

### 4.5 Resumable materialisation

```python
def save_splits_as_parquet(
    splits: dict[str, list[dict]], cache_dir: Path
) -> DatasetPaths:
    import pyarrow as pa
    import pyarrow.parquet as pq
    out_paths = DatasetPaths(
        root=cache_dir,
        train=cache_dir / "train",
        validation=cache_dir / "validation",
        test=cache_dir / "test",
    )
    for split_name, samples in splits.items():
        out_dir = getattr(out_paths, split_name)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / "data.parquet"
        if out_file.exists():
            logger.info(
                f"{split_name}: {out_file} exists, skipping "
                f"({out_file.stat().st_size // 1024} KiB on disk)"
            )
            continue
        # Drop the audio column — it doesn't survive
        # pyarrow roundtrip with raw numpy arrays (would
        # need soundfile embedding). The training script
        # re-reads from the audio_path if needed.
        rows = [
            {k: v for k, v in s.items() if k != "audio"}
            for s in samples
        ]
        table = pa.Table.from_pylist(rows)
        pq.write_table(table, out_file)
        logger.info(
            f"{split_name}: wrote {len(rows)} rows to {out_file}"
        )
    return out_paths
```

### 4.6 Resumable read

```python
def load_splits(cache_dir: Path) -> tuple[int, int, int]:
    """Read the row counts of the three splits. Used
    by main() to log progress (and later, to skip
    the dataset preparation if all three splits
    are already on disk)."""
    out = []
    for split in ("train", "validation", "test"):
        f = cache_dir / split / "data.parquet"
        if not f.exists():
            return (0, 0, 0)
        import pyarrow.parquet as pq
        out.append(pq.read_metadata(f).num_rows)
    return tuple(out)  # type: ignore
```

## 5. File-by-file change set

| Path | Change | LoC est. |
|---|---|---|
| `backend/scripts/finetune_whisper_yue.py` | Replace `prepare_common_voice_yue` body; add `split_by_client_id`, `cap_at_hours`, `save_splits_as_parquet`, `load_splits`, `_audio_seconds` | +180 / -15 |
| `backend/tests/voice/test_finetune_script.py` | Replace `test_prepare_common_voice_yue_is_stub` with `test_prepare_common_voice_yue_end_to_end` (mock streaming iterable, 5 samples, assert parquet files have the expected shape) + 3 unit tests for `split_by_client_id` and `cap_at_hours` | +120 / -25 |
| `docs/FEATURE-SPEC-SPRINT21.md` | NEW. This file. | +200 / 0 |
| `docs/CHANGELOG.md` | Add Sprint 21 entry under [Unreleased] | +30 / 0 |

**Total**: ~490 LoC. ~1 hour wall clock.

## 6. Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **Speaker-disjoint split bias** (top-N speakers by sample count → test) | Medium | Low | The current bias is a deliberate trade-off: we want enough test samples for a stable WER. If a future sprint wants uniform speaker sampling, swap the sort key. |
| **`audio` column dropped from parquet** (we drop the raw numpy; training re-reads from path) | Medium | Medium | Documented in `save_splits_as_parquet`. The training script can either re-stream the audio via `Audio(sampling_rate=16000)` or load the bytes from disk. We don't solve this in Sprint 21. |
| **Resumability** (re-running skips existing parquet files) | Low | Low | The check is `if out_file.exists(): skip`. The user can delete `~/.gundam-halo/cache/cv-yue/` to force a re-download. |
| **`pyarrow` not installed** in unit-test env | Medium | Low | `save_splits_as_parquet` lazy-imports `pyarrow` so the pure functions (`split_by_client_id`, `cap_at_hours`) are testable without it. |
| **`datasets` not installed** in unit-test env | High | High | `prepare_common_voice_yue`'s streaming call is lazy-imported inside a try/except so the function is importable but unusable until `uv sync --extra train`. The test mocks the streaming source with a plain iterable. |
| **Common Voice yue schema changes** | Low | Medium | We use the standard HF dataset schema (`client_id`, `audio`, `sentence`). If a future version renames these, the impl raises `KeyError` with a clear message. |
| **`max_train_hours` exceeded by 1 sample** | Low | Low | `cap_at_hours` is a greedy algorithm; it may end up a few seconds under or over the cap. We log the final duration. |

## 7. Acceptance tests

1. **`split_by_client_id` is speaker-disjoint** —
   `test_split_by_client_id_speaker_disjoint`:
   stream 10 mock samples from 3 speakers; assert
   no client_id appears in two splits.
2. **`split_by_client_id` respects ratios** —
   `test_split_by_client_id_respects_test_val_ratio`:
   assert test split is ~5% of speakers, val ~5%,
   train the rest.
3. **`cap_at_hours` drops longest samples first** —
   `test_cap_at_hours_drops_longest_first`: pass
   5 samples with varying durations; assert the
   output is under the cap and dropped samples are
   the longest.
4. **`save_splits_as_parquet` writes 3 files** —
   `test_save_splits_as_parquet_writes_three_files`:
   pass a 6-sample split dict; assert three parquet
   files exist with the expected row counts.
5. **End-to-end `prepare_common_voice_yue` with
   mock iterable** —
   `test_prepare_common_voice_yue_end_to_end`:
   monkey-patch `datasets.load_dataset` to return
   a list of 5 mock samples from 2 speakers; call
   `prepare_common_voice_yue("13.0", tmp_path,
   max_train_hours=0.001)` (1-second cap); assert
   the parquet files are created and the train
   split has the expected number of rows.
6. **No regression** — all 58 backend tests + 1
   skip from Sprint 19d still pass. All 63 frontend
   vitest tests still pass.

## 8. Sign-off

- [x] **Track 21 scope agreed** — replace the
      `NotImplementedError` stub with a real, testable
      implementation. Speaker-disjoint split, hour
      cap, parquet materialisation, resumable download.
- [x] **Out-of-scope items confirmed** — actual
      `uv sync --extra train` install, actual training
      run, `WhisperHFASR` swap, augmented system note
      removal all deferred.

"""Sprint 33b — WhisperHFASR chunk transcriber.

Tiny CLI helper used by the Tauri recording pipeline (see
`frontend/src-tauri/src/recording.rs`). Loads the
`whisper_hf` WhisperHFASR backend once at startup, then
reads one WAV file path per line from stdin and writes a
JSON transcript object per line to stdout. Stays alive
across chunks so the model only loads once per recording
session (the recording subprocess keeps this helper
alive for its lifetime; on capture-stop we kill the
subprocess and the helper exits cleanly).

The Tauri Rust side spawns this helper as a subprocess of
the project venv Python (passed via the `python_bin`
config or defaulting to `backend/.venv/bin/python`) and
pipes chunks through it. Output is a JSON object per
line, matching the `ManifestRow` schema in
`app.voice.self_record_manifest`:

    {"audio_path": "...", "text": "...", "duration_s": 30.0,
     "sample_rate": 16000}

Errors on a single chunk are emitted as a JSON object
with `"error"` set — the Tauri side logs and skips the
manifest row (the chunk WAV is still kept on disk so
the user can debug later).

CLI:
    python -m app.voice.asr.whisper_hf_helper [--lang yue]

Stdin: one WAV path per line. Empty lines ignored.
Stdout: one JSON object per line, same schema as
        ManifestRow but with `text` from the ASR result.
Stderr: progress + warnings.
Exit: 0 on EOF, 1 on init failure.

Per the long-term memory §minimax-image-api, MiniMax API
rate limits don't apply here (this is local WhisperHF
inference, not MiniMax), so the rate-limit + retry
discipline doesn't carry over. Whisper is GPU-bounded
not rate-bounded; the bounded-concurrency FIFO queue
in `recording.rs` already prevents the GPU from
overcommitting.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import wave
from pathlib import Path

# Make `app.*` imports work whether this script is run as
# `python -m app.voice.asr.whisper_hf_helper` (preferred)
# or `python backend/app/voice/asr/whisper_hf_helper.py`
# (fallback for environments where the module path isn't
# set up). The Tauri side uses `python -m` so this is
# the canonical entry point.
try:
    from app.core.config import get_config
    from app.voice.asr.asr_factory import create_asr
except ImportError:  # pragma: no cover — fallback path
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from app.core.config import get_config  # type: ignore[no-redef]
    from app.voice.asr.asr_factory import create_asr  # type: ignore[no-redef]

logger = logging.getLogger("whisper_hf_helper")


def _read_wav_duration_s(path: Path) -> tuple[float, int, bytes]:
    """Read a 16 kHz mono int16 WAV file.

    Returns (duration_s, sample_rate, pcm_bytes). On error,
    returns (0.0, 0, b"") and the caller should treat the
    chunk as broken.
    """
    try:
        with wave.open(str(path), "rb") as wf:
            rate = wf.getframerate() or 16000
            n_channels = wf.getnchannels()
            sample_width = wf.getsampwidth()
            frames = wf.getnframes()
            raw = wf.readframes(frames)
        # Gundam Halo's pipeline is hard-coded to 16 kHz mono
        # int16. Reject anything else — the helper can't
        # resample (would need scipy/torchaudio, both are out
        # of scope for a subprocess that should stay
        # dependency-light).
        if rate != 16000:
            logger.warning(
                "%s: sample_rate=%d (expected 16000), skipping",
                path, rate,
            )
            return 0.0, rate, b""
        if n_channels != 1 or sample_width != 2:
            logger.warning(
                "%s: channels=%d sampwidth=%d (expected 1ch int16), skipping",
                path, n_channels, sample_width,
            )
            return 0.0, rate, b""
        duration_s = frames / float(rate)
        return duration_s, rate, raw
    except Exception as e:  # pragma: no cover
        logger.warning("failed to read WAV %s: %s", path, e)
        return 0.0, 0, b""


def _transcribe_chunk(asr, audio_path: Path, language: str | None) -> dict:
    """Transcribe a single WAV chunk. Returns a manifest-row-shaped dict.

    On error, the dict has an `"error"` field and empty `"text"`.
    """
    if not audio_path.exists():
        return {
            "audio_path": str(audio_path),
            "text": "",
            "duration_s": 0.0,
            "sample_rate": 0,
            "error": f"file_not_found: {audio_path}",
        }
    duration_s, sample_rate, pcm = _read_wav_duration_s(audio_path)
    if not pcm:
        return {
            "audio_path": str(audio_path),
            "text": "",
            "duration_s": duration_s,
            "sample_rate": sample_rate,
            "error": "wav_decode_failed",
        }
    try:
        import asyncio
        # WhisperHFASR.transcribe is async. We run it in a fresh
        # event loop per chunk (the helper is the only async
        # caller in this script; reusing a single loop works too
        # but adds hidden state we don't need).
        text = asyncio.run(asr.transcribe(pcm, sample_rate)) or ""
        return {
            "audio_path": str(audio_path),
            "text": text.strip(),
            "duration_s": duration_s,
            "sample_rate": sample_rate,
        }
    except Exception as e:  # pragma: no cover — exercised in CI via e2e
        return {
            "audio_path": str(audio_path),
            "text": "",
            "duration_s": duration_s,
            "sample_rate": sample_rate,
            "error": f"transcribe_failed: {e}",
        }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Sprint 33b: long-lived WhisperHFASR chunk transcriber. "
            "Reads one WAV path per line on stdin; emits one JSON "
            "manifest-row per line on stdout."
        )
    )
    parser.add_argument(
        "--lang",
        default="yue",
        help=(
            "Language hint. Default 'yue' (Cantonese ISO 639-3 — "
            "matches the voice pipeline's standard whisper_hf "
            "config; the Sprint 26 → Sprint 35 mlx-whisper path "
            "also uses 'yue'). Currently informational only — "
            "WhisperHFASR.transcribe doesn't expose a per-call "
            "language override in v0.1.5+, so the language is "
            "baked into the loaded model. The flag is accepted "
            "so the Tauri side can document its intent; future "
            "Sprint 36+ may add per-call language overrides."
        ),
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level (DEBUG / INFO / WARNING / ERROR).",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # Load ASR backend from config. The Tauri side relies on the
    # project venv having all the whisper_hf deps installed
    # (torch + transformers + librosa). If the user hasn't
    # configured `voice.asr.backend = "whisper_hf"` we still
    # honor their config here (don't silently swap to
    # whisper_local — that would burn the model load for a
    # different result).
    try:
        cfg = get_config().voice.asr
        asr = create_asr(cfg)
        # Warmup once so the first chunk isn't 5s slower.
        # WhisperHFASR exposes an async-free warmup; for backends
        # that don't, this is a no-op (the first transcribe
        # call will trigger load).
        if hasattr(asr, "warmup"):
            warmup_fn = asr.warmup
            try:
                import asyncio
                asyncio.run(warmup_fn())
                logger.info("ASR warmup complete")
            except Exception as e:
                logger.warning("ASR warmup failed (non-fatal): %s", e)
    except Exception as e:
        # Init failure — emit a sentinel JSON line so the Tauri
        # side can read it and surface the error, then exit.
        sys.stdout.write(json.dumps({
            "audio_path": "",
            "text": "",
            "duration_s": 0.0,
            "sample_rate": 0,
            "error": f"init_failed: {e}",
        }) + "\n")
        sys.stdout.flush()
        return 1

    logger.info(
        "whisper_hf_helper ready (lang=%s). Reading WAV paths from stdin.",
        args.lang,
    )

    # Line-buffered stdin / stdout so the Tauri subprocess reads
    # each chunk's transcript as soon as it's ready (no need to
    # wait for the helper to drain a full buffer).
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        audio_path = Path(line)
        start = time.time()
        row = _transcribe_chunk(asr, audio_path, args.lang)
        elapsed_ms = int((time.time() - start) * 1000)
        row["elapsed_ms"] = elapsed_ms
        sys.stdout.write(json.dumps(row, ensure_ascii=False) + "\n")
        sys.stdout.flush()
        if "error" in row:
            logger.warning(
                "transcribe error for %s: %s", audio_path, row["error"]
            )
        else:
            logger.info(
                "transcribed %s (%dms, %d chars)",
                audio_path.name,
                elapsed_ms,
                len(row["text"]),
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
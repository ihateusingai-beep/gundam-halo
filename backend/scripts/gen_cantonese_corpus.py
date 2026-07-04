"""M9-E Layer 2 — Edge TTS Cantonese corpus + held-out generator.

Demo-grade corpus for the personalised fine-tune pipeline. Uses
Microsoft Edge TTS (zh-HK-HiuMaanNeural — Hong Kong Cantonese) to
synthesize a small set of distinct Cantonese phrases, then pipes
the MP3 through ffmpeg to produce 16 kHz mono s16le WAVs (the
exact format the voice pipeline expects per
`app.voice.held_out_eval.SAMPLE_RATE = 16_000`).

Output structure (matches Sprint 45 self-record contract):

    ~/.gundam-halo/recordings/
        yue-self-<YYYY-MM-DD>/
            chunk-001.wav      # training audio
            chunk-001.txt      # (optional — chunk text mirror)
            ...
            manifest.jsonl     # one JSON object per line, schema:
                                #   {audio_path, text, duration_s, sample_rate}
        held-out-<YYYY-MM-DD>.wav    # eval set (held out from training)
        held-out-<YYYY-MM-DD>.txt    # ground-truth transcript

Sprint 40 orchestrator picks the **latest** held-out-{wav,txt} via
`latest_heldout_wav()`, and the **latest** `yue-self-<date>/` via
`_latest_self_record_corpus()`.

Why Edge TTS, not Common Voice:
- Common Voice yue is ~700 MB download + ~50 h of audio. For a
  demo-grade proof that the pipeline works (orchestrator +
  finetune + eval + backend swap), that's overkill.
- Edge TTS zh-HK voice is high-quality Hong Kong Cantonese — the
  same voice the production app uses for TTS output (see
  `_gen_hello_fixture.py` — already pulls this voice for the M9-A
  smoke).
- Phrase selection is hand-curated for diversity: verbs, nouns,
  particles, numbers, and the 4×6 Cantonese particles
  (嘅, 喎, 嚟, 啦, 唔, 睇).

Caveats baked in:
- Synthetic audio will be cleaner than real recordings (no
  breath noise, no mic variation) — WER improvements transfer
  partially to real recordings.
- This is a **demo-grade** corpus. Per user direction on
  2026-07-02: user will eventually use the Tauri record card
  for real self-record data; this script exercises the same
  downstream pipeline in the meantime.

Usage:
    cd backend && uv run python scripts/gen_cantonese_corpus.py
    cd backend && uv run python scripts/gen_cantonese_corpus.py --date 2026-07-02
    cd backend && uv run python scripts/gen_cantonese_corpus.py --heldout-text "今日天氣好好"
"""
from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sys
from datetime import date
from pathlib import Path

import edge_tts

# Default phrases — hand-picked for Cantonese diversity. Each tuple
# is (id, cantonese_text, voice_kwargs).
# - 8 training phrases (chunk-001..008) — diverse grammar
# - 1 held-out phrase (text kept separate so user can override)
DEFAULT_TRAINING_PHRASES: list[tuple[str, str]] = [
    ("001", "今日天氣好好啊"),
    ("002", "我哋去食飯喇"),
    ("003", "你呢個點樣做嘅"),
    ("004", "佢唔識講英文"),
    ("005", "畀我睇吓嗰本書"),
    ("006", "幾多錢一公斤呀"),
    ("007", "我聽日返廣州"),
    ("008", "香港人鍾意飲凍奶茶"),
]

DEFAULT_HELDOUT_TEXT = "你食咗飯未呀"

VOICE = "zh-HK-HiuMaanNeural"

# Sprint 56 R1: halo_home() + resolve_halo_home() moved to
# `scripts/_script_lib.py` (single source of truth for the
# ~/.gundam-halo path across all 8 scripts in this dir).
from _script_lib import resolve_halo_home  # noqa: F401
from app.paths import halo_home as _halo_home_default


def _resolve_halo_home(args: argparse.Namespace) -> Path:
    """Back-compat wrapper — original signature + existence check.

    Sprint 56 R1 keeps this thin shim so the rest of the script can
    keep using `_resolve_halo_home(args)` unchanged. The existence
    check matches the pre-Sprint-56 behaviour: refuse to auto-create
    an empty halo_home (recordings dir must pre-exist).
    """
    halo = resolve_halo_home(args)
    if not halo.exists():
        # Don't auto-create — caller may want a different layout.
        raise SystemExit(f"halo_home does not exist: {halo}")
    return halo


DEFAULT_HALO_HOME = _halo_home_default()
# Back-compat: callers that still reference `DEFAULT_HALO_HOME`
# get the canonical Path; `app.paths.halo_home()` honours $HALO_HOME
# if set in the environment.


SAMPLE_RATE = 16000
# Sprint 56 R2: route through canonical `app.voice.audio_io`.
# Note: the canonical impl raises `RuntimeError` on ffmpeg
# missing — converted to `SystemExit` below for compat with the
# pre-Sprint-56 behaviour (existing scripts handled the exit
# via SystemExit not RuntimeError).
from app.voice.audio_io import (
    ffmpeg_to_wav as _ffmpeg_to_wav_canonical,
    SAMPLE_RATE as _AUDIO_IO_SAMPLE_RATE,
)


def _ffmpeg_to_wav(mp3_path: Path, wav_path: Path) -> tuple[float, int]:
    """Convert mp3 → 16 kHz mono s16le WAV via ffmpeg.

    Sprint 56 R2: thin shim over `app.voice.audio_io.ffmpeg_to_wav`.
    Kept the same signature so call-sites don't change. Translates
    RuntimeError to SystemExit to match pre-Sprint-56 behaviour
    (existing scripts called `subprocess.run(check=True)` whose
    failure raises `subprocess.CalledProcessError` and the script
    let it propagate as a fatal error — SystemExit is just a
    slightly louder exit-style).
    """
    try:
        return _ffmpeg_to_wav_canonical(mp3_path, wav_path)
    except RuntimeError as e:
        raise SystemExit(str(e)) from None


async def _synth_mp3(text: str, mp3_path: Path) -> None:
    communicate = edge_tts.Communicate(text, VOICE)
    with mp3_path.open("wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])


def _gen_phrase(phrase_id: str, text: str, wav_path: Path, mp3_dir: Path) -> dict:
    """Synth one phrase → write WAV → return manifest row dict.

    Side effects: writes `{phrase_id}.wav` to `wav_path` and a
    throwaway `{phrase_id}.mp3` to `mp3_dir` (cleaned up at end).
    """
    mp3_path = mp3_dir / f"{phrase_id}.mp3"
    asyncio.run(_synth_mp3(text, mp3_path))
    duration_s, sample_rate = _ffmpeg_to_wav(mp3_path, wav_path)
    return {
        "audio_path": str(wav_path.resolve()),
        "text": text,
        "duration_s": round(duration_s, 3),
        "sample_rate": sample_rate,
    }


def _write_manifest(manifest_path: Path, rows: list[dict]) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _build_self_record(halo_home: Path, date_str: str, phrases: list[tuple[str, str]]) -> Path:
    """Generate yue-self-<date>/{chunks.wav + manifest.jsonl}.

    Returns the corpus dir path.
    """
    corpus_dir = halo_home / "recordings" / f"yue-self-{date_str}"
    chunks_dir = corpus_dir  # chunks live at root of corpus dir
    corpus_dir.mkdir(parents=True, exist_ok=True)

    # Use a sibling scratch dir for the temporary MP3s.
    mp3_dir = corpus_dir / "_mp3_scratch"
    mp3_dir.mkdir(exist_ok=True)

    rows: list[dict] = []
    try:
        for phrase_id, text in phrases:
            wav_path = chunks_dir / f"chunk-{phrase_id}.wav"
            print(f"  synth chunk-{phrase_id}: {text!r}")
            row = _gen_phrase(phrase_id, text, wav_path, mp3_dir)
            # Drop the throwaway mp3 right after each chunk to keep
            # the scratch dir small (5-10 phrases × ~30 KB each).
            mp3_for_phrase = mp3_dir / f"{phrase_id}.mp3"
            if mp3_for_phrase.exists():
                mp3_for_phrase.unlink()
            # Also write a sibling .txt mirror — Tauri record
            # pipeline follows the same convention.
            (chunks_dir / f"chunk-{phrase_id}.txt").write_text(text, encoding="utf-8")
            rows.append(row)
    finally:
        if mp3_dir.exists():
            shutil.rmtree(mp3_dir, ignore_errors=True)

    manifest_path = corpus_dir / "manifest.jsonl"
    _write_manifest(manifest_path, rows)
    print(f"  manifest: {manifest_path} ({len(rows)} chunks)")
    return corpus_dir


def _build_held_out(halo_home: Path, date_str: str, text: str) -> tuple[Path, Path]:
    """Generate held-out-<date>.{wav,txt} (eval set).

    Uses a separate MP3 scratch dir under recordings/.
    """
    recordings = halo_home / "recordings"
    recordings.mkdir(parents=True, exist_ok=True)
    wav_path = recordings / f"held-out-{date_str}.wav"
    txt_path = recordings / f"held-out-{date_str}.txt"
    mp3_dir = recordings / "_heldout_mp3_scratch"
    mp3_dir.mkdir(exist_ok=True)

    try:
        mp3 = mp3_dir / "heldout.mp3"
        print(f"  synth held-out: {text!r}")
        _gen_phrase("heldout", text, wav_path, mp3_dir)
        if mp3.exists():
            mp3.unlink()
    finally:
        if mp3_dir.exists():
            shutil.rmtree(mp3_dir, ignore_errors=True)

    txt_path.write_text(text, encoding="utf-8")
    print(f"  txt: {txt_path}")
    return wav_path, txt_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Edge TTS Cantonese corpus + held-out generator")
    p.add_argument(
        "--date",
        default=date.today().isoformat(),
        help="Date slug embedded in corpus paths (default: today UTC).",
    )
    p.add_argument(
        "--halo-home",
        type=Path,
        default=None,
        help=f"HALO_HOME root (default: {DEFAULT_HALO_HOME}).",
    )
    p.add_argument(
        "--heldout-text",
        default=DEFAULT_HELDOUT_TEXT,
        help="Cantonese text for held-out-<date>.txt (default: %(default)s).",
    )
    p.add_argument(
        "--skip-self-record",
        action="store_true",
        help="Skip the yue-self-<date>/ training corpus generation.",
    )
    p.add_argument(
        "--skip-held-out",
        action="store_true",
        help="Skip the held-out-<date>.wav/txt generation.",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    halo_home = _resolve_halo_home(args)
    date_str = args.date

    print(f"[gen_cantonese_corpus] halo_home={halo_home}, date={date_str}")

    if not args.skip_self_record:
        corpus_dir = _build_self_record(halo_home, date_str, DEFAULT_TRAINING_PHRASES)
        print(f"[gen_cantonese_corpus] self-record corpus: {corpus_dir}")
    if not args.skip_held_out:
        wav, txt = _build_held_out(halo_home, date_str, args.heldout_text)
        print(f"[gen_cantonese_corpus] held-out: {wav}")
        print(f"[gen_cantonese_corpus] held-out transcript: {txt}")
    print("[gen_cantonese_corpus] done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
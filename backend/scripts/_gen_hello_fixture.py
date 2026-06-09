"""Generate a 16kHz mono PCM WAV fixture for the M9-A voice smoke.

Uses Edge TTS to synthesize a Cantonese phrase, then pipes the MP3
through ffmpeg to produce a 16kHz mono int16 WAV — exactly the format
the voice pipeline expects (silero_vad.py and whisper_local.py).

Phrase: "你好，請問你叫什麼名字？" (Cantonese-leaning, ~2 seconds)

Output: backend/tests/voice/fixtures/hello.wav
"""
from __future__ import annotations

import asyncio
import shutil
import subprocess
import sys
from pathlib import Path


VOICE = "zh-HK-HiuMaanNeural"
TEXT = "你好，請問你叫什麼名字？"
SCRIPT_DIR = Path(__file__).resolve().parent
FIXTURE_DIR = SCRIPT_DIR.parent / "tests" / "voice" / "fixtures"
OUT_WAV = FIXTURE_DIR / "hello.wav"


async def synth_mp3() -> Path:
    import edge_tts

    tmp_mp3 = FIXTURE_DIR / "_hello.mp3"
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    communicate = edge_tts.Communicate(TEXT, VOICE)
    await communicate.save(str(tmp_mp3))
    return tmp_mp3


def mp3_to_wav(mp3_path: Path, wav_path: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found on PATH")
    cmd = [
        ffmpeg, "-y", "-loglevel", "error",
        "-i", str(mp3_path),
        "-ar", "16000",       # 16 kHz
        "-ac", "1",           # mono
        "-sample_fmt", "s16", # signed 16-bit (matches voice_ws.py frame format)
        "-f", "wav",
        str(wav_path),
    ]
    subprocess.run(cmd, check=True)


def main() -> int:
    print(f"Synth: voice={VOICE}, text={TEXT!r}")
    mp3 = asyncio.run(synth_mp3())
    print(f"  mp3: {mp3} ({mp3.stat().st_size} bytes)")
    mp3_to_wav(mp3, OUT_WAV)
    print(f"  wav: {OUT_WAV} ({OUT_WAV.stat().st_size} bytes)")
    mp3.unlink()
    return 0


if __name__ == "__main__":
    sys.exit(main())

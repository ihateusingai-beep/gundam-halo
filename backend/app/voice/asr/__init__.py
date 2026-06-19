"""ASR (automatic speech recognition) sub-module.

ASR takes a complete utterance (the audio buffered between VAD
`speech_start` and `speech_end` events) and returns transcribed text.

In M1 we ship the local `openai-whisper` Python package backend
(tiny/base/small/medium/large). M2+ candidates: whisper.cpp, FunASR,
Groq cloud Whisper as a fallback.

Sprint 32 P0-1: each ASR backend class is decorated with
`@register_asr("name")` from `app.core.registry`. We eagerly
import `whisper_local` (the default, no extra deps) and wrap
the other two in `try/except ImportError` so users without
the `voice-yuesub` / `voice-hf` extras still see the
registry populated for whatever backends they DO have
installed. `asr_factory.create_asr()` then looks up the
backend via `AsrRegistry.get(name)` — see `asr_factory.py`.
"""
from app.voice.asr import whisper_local  # noqa: F401  (registers WhisperLocalASR)

# Optional backends — fail-open if the extra isn't installed.
try:
    from app.voice.asr import yuesub  # noqa: F401  (registers YuesubASR if voice-yuesub extra is installed)
except ImportError:
    pass

try:
    from app.voice.asr import whisper_hf  # noqa: F401  (registers WhisperHFASR if voice-hf extra is installed)
except ImportError:
    pass


"""TTS (text-to-speech) sub-module — M2.

TTS takes a chunk of agent text (typically one sentence) and returns
audio bytes for the client to play.

M1: interface only. M2: ship Edge TTS (free, no API key).

Sprint 32 P0-1: each TTS backend is decorated with
`@register_tts("name")` from `app.core.registry`. EdgeTTS is
eagerly imported here (no extra Python deps — edge-tts is
in the base venv). Future backends (pyttsx3, azure) can
opt in the same way.
"""
from app.voice.tts import edge_tts  # noqa: F401  (registers EdgeTTS)


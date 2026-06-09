"""ASR (automatic speech recognition) sub-module.

ASR takes a complete utterance (the audio buffered between VAD
`speech_start` and `speech_end` events) and returns transcribed text.

In M1 we ship the local `openai-whisper` Python package backend
(tiny/base/small/medium/large). M2+ candidates: whisper.cpp, FunASR,
Groq cloud Whisper as a fallback.
"""

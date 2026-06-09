"""Voice + Live2D interaction layer (ARCHITECTURE §15).

This package is the M1 deliverable: voice input pipeline skeleton
(VAD → ASR → Message → Agent → text reply). TTS and Live2D are
interfaces only in M1; full implementations come in M2 / M3.

Why a separate package from `agents/`, `tools/`, etc.?
- Voice is orthogonal to the agent loop — it's a NEW input channel.
- The factories mirror Open-LLM-VTuber's `vad/`, `asr/`, `tts/`
  pattern so we can borrow engine swap patterns if needed.
- Tauri client and Telegram both produce a `Message(role=user)`; this
  module is the only place that knows about audio bytes.
"""

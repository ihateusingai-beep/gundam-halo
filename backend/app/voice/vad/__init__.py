"""VAD (voice activity detection) sub-module.

VAD answers one question: is the user currently speaking?
It operates on ~250ms audio frames and emits `VADEvent`s with
`is_speech=True/False` and a probability score.

In M1 we ship the Silero VAD v5 ONNX backend (port of the pattern from
Open-LLM-VTuber, MIT). The interface is the public surface — swap in
webrtcvad or pyannote later without touching call sites.

Sprint 32 P0-1: each VAD backend is decorated with
`@register_vad("name")` from `app.core.registry`. Both
SileroVAD and FsmnVAD are eagerly imported here (they have
no extra Python deps that could fail at import time — the
fsmn ONNX model is loaded lazily by the class init).
`vad_factory.create_vad()` looks up the backend via
`VadRegistry.get(name)`.
"""
from app.voice.vad import silero_vad, fsmn_vad  # noqa: F401  (registers both)


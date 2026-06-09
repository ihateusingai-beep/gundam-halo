"""VAD (voice activity detection) sub-module.

VAD answers one question: is the user currently speaking?
It operates on ~250ms audio frames and emits `VADEvent`s with
`is_speech=True/False` and a probability score.

In M1 we ship the Silero VAD v5 ONNX backend (port of the pattern from
Open-LLM-VTuber, MIT). The interface is the public surface — swap in
webrtcvad or pyannote later without touching call sites.
"""

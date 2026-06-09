"""Fake VAD for tests — always reports is_speech=False.

Used in pipeline tests to bypass Silero (which needs the ONNX model
on disk). The pipeline doesn't care about VAD accuracy in M1 tests
because we feed it frames directly through `feed_frame()` — we just
need a no-op VAD that doesn't crash.
"""

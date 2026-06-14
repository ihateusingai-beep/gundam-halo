"""Sprint 17b: Cantonese / OpenCC post-ASR corrector.

Placeholder for Track C. The full implementation lifts yuesub-api's
`Corrector` (regex rules + OpenCC t2s + optional BERT masked-LM
perplexity selection) into an async-friendly wrapper that
`YuesubASR.transcribe()` can call between the ASR step and the
wake-phrase detector.

See docs/FEATURE-SPEC-SPRINT17b.md §5.1 for the design and
yuesub-api's `corrector/Corrector.py` for the reference impl.
"""
from __future__ import annotations

from typing import Literal, Optional


class Corrector:
    """Placeholder; Track C will replace this with the lifted
    implementation from yuesub-api.

    Args:
        corrector: One of "opencc" | "bert". The yuesub-api
            `Corrector` accepts these literal strings; "none"
            is handled by the caller passing `corrector=None`
            rather than instantiating this class.
    """

    def __init__(self, corrector: Literal["opencc", "bert"] = "opencc") -> None:
        if corrector not in ("opencc", "bert"):
            raise ValueError(
                f"corrector must be 'opencc' or 'bert', got {corrector!r}"
            )
        self.corrector = corrector
        # Track C will populate these:
        #   self.converter = opencc.OpenCC("s2hk")          # for "opencc"
        #   self.regular_errors: list[tuple[re.Pattern, str]]
        #   self.bert_model = BertModel(...)                # for "bert"
        #   self.t2s_char_dict, self.char_jyutping_dict, ...
        raise NotImplementedError(
            "Sprint 17b Track C placeholder. The real Corrector "
            "implementation is in app/voice/corrector/corrector.py "
            "(yet to be written). For now, the yuesub ASR will "
            "raise this error if you set corrector='bert' or "
            "corrector='opencc' in config.toml."
        )

    def correct(self, text: str) -> str:
        raise NotImplementedError("Track C placeholder")


__all__ = ["Corrector"]

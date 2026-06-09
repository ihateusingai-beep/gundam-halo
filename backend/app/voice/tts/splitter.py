"""Sentence splitter for TTS streaming.

We split agent text into sentences so we can start playing the first
sentence while the agent is still producing the rest. pysbd handles
this robustly across languages.

Edge cases handled:
- English: ". " / "? " / "! " + common abbreviations
- Chinese: 。！？ + 「」 quotes
- Mixed: when text contains both, pysbd picks the dominant language
- Empty / whitespace-only input → empty list
- Very long single sentence (>max_chars): split on commas / spaces
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache

logger = logging.getLogger(__name__)


# Map our agent `language` codes to pysbd language codes.
# pysbd supports: en, de, es, fr, it, nl, pl, pt, ru, ja, zh, am, ar, hi, etc.
_PYSBD_LANG_MAP = {
    "en": "en",
    "zh": "zh",
    "zh-hk": "zh",
    "zh-cn": "zh",
    "yue": "zh",  # Cantonese — pysbd treats as zh
    "ja": "ja",
    "ko": None,  # pysbd has limited Korean support; fall back to manual split
    "es": "es",
    "fr": "fr",
    "de": "de",
    "auto": "en",  # default to English splitter; will mis-split CJK but safely
}


@lru_cache(maxsize=4)
def _get_segmenter(language: str):
    """Cache pysbd.Segmenter instances (one per language)."""
    import pysbd

    return pysbd.Segmenter(language=language, clean=False)


def _detect_language(text: str) -> str:
    """Cheap heuristic: if text has CJK chars, use 'zh' splitter.

    pysbd's `en` splitter is bad for CJK (it splits on spaces, which
    Chinese doesn't have). For mixed text we go with the dominant
    script. This is good enough for v1.
    """
    cjk_count = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    if cjk_count > len(text) * 0.3:
        return "zh"
    return "en"


def _hard_split(text: str, max_chars: int) -> list[str]:
    """Last-resort splitter: cut on commas/spaces if a sentence is too long.

    Used when pysbd isn't available or returns one giant blob.
    """
    if len(text) <= max_chars:
        return [text]
    out: list[str] = []
    remaining = text
    while len(remaining) > max_chars:
        # Find the best break point in the first max_chars window
        window = remaining[:max_chars]
        # Prefer Chinese punctuation, then ASCII punctuation, then space
        best_idx = -1
        for punct in ["。", "，", "、", "；", ".", ",", ";", " "]:
            idx = window.rfind(punct)
            if idx > max_chars * 0.5:
                best_idx = idx + 1
                break
        if best_idx <= 0:
            best_idx = max_chars
        out.append(remaining[:best_idx].strip())
        remaining = remaining[best_idx:].strip()
    if remaining:
        out.append(remaining)
    return out


def split_sentences(
    text: str,
    *,
    language: str | None = None,
    max_chars: int = 80,
) -> list[str]:
    """Split *text* into a list of sentence strings.

    Args:
        text: input text (typically the agent's reply)
        language: optional language hint ("en", "zh", "auto").
                  If None or "auto", we detect from the text.
        max_chars: cap single-sentence length. If pysbd returns a
                   sentence longer than this, we hard-split it.

    Returns:
        Non-empty list of trimmed sentence strings. Never returns the
        input unchanged if it's longer than max_chars * 2.
    """
    text = (text or "").strip()
    if not text:
        return []

    # Decide splitter language
    if not language or language == "auto":
        language = _detect_language(text)
    pysbd_lang = _PYSBD_LANG_MAP.get(language.lower())

    sentences: list[str] = []
    if pysbd_lang:
        try:
            seg = _get_segmenter(pysbd_lang)
            sentences = [s.strip() for s in seg.segment(text) if s.strip()]
        except Exception as e:
            logger.warning(f"pysbd split failed for {language!r}: {e}")
            sentences = []

    if not sentences:
        # Fallback: regex-based split on common sentence terminators
        # Keep the terminator attached to the sentence.
        parts = re.split(r"(?<=[。！？.!?])\s*", text)
        sentences = [p.strip() for p in parts if p.strip()]

    if not sentences:
        sentences = [text]

    # Hard-cap long sentences
    capped: list[str] = []
    for s in sentences:
        if len(s) > max_chars:
            capped.extend(_hard_split(s, max_chars))
        else:
            capped.append(s)

    return capped


__all__ = ["split_sentences"]

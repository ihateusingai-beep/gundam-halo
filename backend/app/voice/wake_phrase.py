"""Wake phrase detection — text-level only (Sprint 16).

The voice pipeline feeds ASR transcripts into this module before
invoking the agent. If the transcript starts with a wake phrase
("Unicorn", "NTD", "gundam", "獨角獸", "高達" by default — see
`VoiceConfig.wake_phrases`), the prefix is stripped from the text
the agent sees and a `wake_triggered: True` flag is returned.

This is a **permissive** mode: even when the transcript doesn't start
with a wake phrase, the agent is still invoked. The flag is just a
confidence marker for the UI / MissionLog. A future "strict mode"
toggle (in Settings → Voice) will gate the agent on the flag; for
now permissive is the only mode.

Why text-level (not native wake-word):
  - Native wake-word detection requires always-on mic capture +
    on-device keyword spotting. Sprint 17 candidate, leveraging
    `~/workspace/yuesub-api` (SenseVoice + fsmn-vad).
  - Text-level detection is the next-best UX without the always-on
    mic permission. The user must still hold the mic button, but
    the transcript can contain the wake phrase anywhere in the
    first ~32 chars and we'll treat it as a command.

Why permissive (vs strict):
  - User explicitly chose permissive (2026-06-14 sign-off). Avoids
    breaking the existing text-input path where users have been
    typing instructions without a wake phrase.
  - The flag is surfaced in `agent.message.wake_triggered` and in
    the MissionLog, so users still get visible feedback when a
    wake phrase was matched.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import List, Optional


@dataclass(slots=True, frozen=True)
class WakeMatch:
    """Result of `detect_wake_phrase`.

    `matched` is True if a wake phrase was found.
    `phrase` is the canonical wake phrase that matched (one of
        the user-configured list, in its original casing).
    `stripped` is the user's transcript with the leading wake
        phrase + any leading punctuation / whitespace removed.
        Always present (== input text when matched=False).
    """

    matched: bool
    phrase: str
    stripped: str


def _normalize(text: str) -> str:
    """Lower-case + Unicode-normalize so 'Unicorn', 'unicorn', and
    'UNICORN' all match. NFKC normalization collapses full-width
    characters / compatibility forms."""
    return unicodedata.normalize("NFKC", text).lower().strip()


# The prefix scan is bounded: we only look at the first 64 chars
# of the transcript. ASR transcripts with a wake phrase embedded
# at the start should fit easily. We then strip everything up to
# (and including) the first wake-phrase match, plus leading
# punctuation / whitespace.
_PREFIX_SCAN_CHARS = 64


def _build_phrase_pattern(phrases: List[str]) -> re.Pattern[str]:
    """Build a case-insensitive alternation pattern from the user's
    configured wake phrases. Multi-character phrases are matched
    as word boundaries when possible; we use a simple alternation
    anchored to the start of the string."""
    if not phrases:
        # Match nothing.
        return re.compile(r"(?!)")
    # Sort longest first so '高達' wins over '高' if both are listed.
    sorted_phrases = sorted(set(phrases), key=len, reverse=True)
    escaped = [re.escape(p) for p in sorted_phrases]
    body = "|".join(escaped)
    # Anchor to the start: the wake phrase must be the user's first
    # word, not a mid-sentence occurrence. A leading "Unicorn" in
    # "open Unicorn for me" is NOT a wake — the user wasn't talking
    # to the agent.
    return re.compile(rf"(?i)^({body})")


def detect_wake_phrase(
    text: str,
    phrases: List[str],
) -> WakeMatch:
    """Detect a leading wake phrase in `text` and return a WakeMatch.

    No side effects, no I/O, no LLM call. Pure string match. Cost is
    O(N) where N is min(len(text), _PREFIX_SCAN_CHARS) — typically
    tens of microseconds.
    """
    if not text or not phrases:
        return WakeMatch(matched=False, phrase="", stripped=(text or "").strip())

    # Normalize the head once so that:
    #   - case differences fold ("Unicorn" == "unicorn")
    #   - full-width / compatibility forms fold ("Ｕｎｉｃｏｒｎ" → "Unicorn")
    # The stripped tail is taken from the ORIGINAL text (so the
    # agent sees the user's actual characters, not a normalized form).
    head = text[:_PREFIX_SCAN_CHARS]
    head_norm = _normalize(head)
    pattern = _build_phrase_pattern(phrases)
    m = pattern.search(head_norm)
    if not m:
        return WakeMatch(matched=False, phrase="", stripped=text.strip())

    # Determine which canonical phrase matched. We use a case-
    # insensitive comparison against the user's list so that
    # 'unicorn' matches 'Unicorn' but we record the user's
    # canonical entry (preserving their casing) in the result.
    matched_text = m.group(1)
    matched_norm = _normalize(matched_text)
    canonical = next(
        (p for p in phrases if _normalize(p) == matched_norm),
        matched_text,
    )

    # Find the corresponding position in the ORIGINAL text. The
    # NFKC normalization is mostly character-width-preserving, so
    # we can match by exact slice width. For full-width chars, the
    # slice covers the original (wider) characters.
    # We iterate to find the slice whose normalized form equals
    # the match.
    raw_end = _find_original_end(text, matched_text, head)
    tail = text[raw_end:]

    # Strip leading separators + common Chinese filler prefixes.
    tail = re.sub(
        r"^[\s,，。.;；:：!！?？、\-—_~·…]+",
        "",
        tail,
    )
    # A handful of "high-frequency filler" words that follow
    # wake phrases in casual speech. We strip at most one of
    # these so a sentence like "Unicorn 幫我 ..." becomes
    # "幫我 ..." (still a valid command) but "獨角獸 開" doesn't
    # get double-stripped.
    tail = re.sub(
        r"^(幫我|幫我哋|幫忙|請|麻烦|麻煩|拜託|拜讬)\s*",
        "",
        tail,
    )

    return WakeMatch(
        matched=True,
        phrase=canonical,
        stripped=tail.strip(),
    )


def _find_original_end(text: str, matched: str, head: str) -> int:
    """Return the index in `text` just after the substring that
    normalized to `matched`. We scan char-by-char through `head`
    collecting characters until the running normalized prefix equals
    the match."""
    # Quick path: ASCII-folded match — the byte slice should match.
    if not matched:
        return 0
    running = ""
    for i, ch in enumerate(text):
        if i >= _PREFIX_SCAN_CHARS:
            break
        running += ch
        if _normalize(running) == _normalize(matched):
            return i + 1
    # Fallback: if we never matched (shouldn't happen), return the
    # length of `matched` in the original text.
    return len(matched)


def first_wake_phrase(phrases: List[str]) -> Optional[str]:
    """Return the first non-empty phrase in the list, or None.
    Used by the UI as a default hint ('Listening for **Unicorn**')."""
    for p in phrases:
        if p.strip():
            return p
    return None

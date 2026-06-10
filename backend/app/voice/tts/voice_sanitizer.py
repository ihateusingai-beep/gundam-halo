"""Voice-text sanitizer — strip LLM reasoning, skip empty markdown
fences, and otherwise normalize the agent's reply before it hits the
sentence splitter + TTS.

This is the M9-D fix for two regression paths observed in M9-C:

  1. The MiniMax-M2 model wraps its internal planning in
     `<think>…</think>` blocks. The current pipeline forwards
     those to TTS, so the user *hears* the model think out loud
     before the actual reply. We strip the blocks here.

  2. When the agent quotes a file path, a command, or anything
     fenced in triple-backticks, pysbd's `zh`/`en` segmenter
     cuts on the boundary right after the first fence line and
     yields a sentence consisting of bare ` ``` `. Edge TTS
     returns 0 bytes for that "sentence" and logs
     `TTS stream failed for '\\`\\`\\`': No audio was received`.
     The audio the user hears becomes fragmented. We rewrite
     fenced code blocks into a single voice-friendly summary
     so they pass through the segmenter without empty chunks.

Design:

  - **Server-side**: this runs in `HaloResponder.respond_stream`,
    not in the frontend. The frontend is free to *display* the
    reasoning or the original markdown (debug panel, log
    scrollback); the server decides what gets *spoken*.

  - **Pure functions** (`strip_reasoning`, `sanitize_for_tts`)
    so the test suite can exercise the rules without spinning
    up the responder. The M9-D acceptance criteria is exactly
    this: `pytest tests/voice/test_sanitize.py` covers the
    known M9-C fixtures.

  - **Conservative**: when in doubt, we pass the text through
    untouched. The strip only removes content that matches a
    tight pattern; the markdown rewrite only applies when we
    can detect a real fenced block.
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. Reasoning strip
# ---------------------------------------------------------------------------

# Match `<think>…</think>` blocks. Non-greedy, multiline. The pattern
# matches the *outer* fences, so consecutive blocks (`<think>a</think>
# <think>b</think>`) are both caught.
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)

# Defensive: Anthropic-style tool calls embedded in visible text. Most
# OpenAI-compatible paths use the `tool_calls` field rather than
# emitting `<tool_call>` in content, but some models do this when they
# are unsure of the schema.
_TOOL_CALL_RE = re.compile(r"<tool_call>.*?</tool_call>", re.DOTALL | re.IGNORECASE)

# Bare "Reasoning:" / "Reasoning steps:" prefix + body up to the next
# blank line OR the end of the input. We don't try to be smart about
# multi-paragraph reasoning prose — if the model opens with one of
# these labels, the user does not want to hear it.
_REASONING_PREFIX_RE = re.compile(
    r"(?im)^(?:reasoning|reasoning steps?|my reasoning|internal reasoning|推理)"
    r"\s*[:：]\s*"
    r"(?P<body>.*?)"
    r"(?=\n\s*\n|\Z)",
    re.DOTALL,
)


def strip_reasoning(text: str) -> str:
    """Remove LLM reasoning blocks from *text*.

    Strips, in order:
      - `<think>…</think>` blocks (MiniMax-M2 / Qwen / DeepSeek style)
      - `<tool_call>…</tool_call>` blocks (defensive, Anthropic-style)
      - Leading "Reasoning: …" prose blocks

    Returns the input with leading/trailing whitespace collapsed.
    If nothing matched, returns *text* unchanged.
    """
    if not text:
        return text

    out = _THINK_RE.sub("", text)
    out = _TOOL_CALL_RE.sub("", out)

    m = _REASONING_PREFIX_RE.match(out)
    if m:
        out = out[m.end():]

    # Collapse any triple+ newlines left behind by removed blocks.
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


# ---------------------------------------------------------------------------
# 2. Markdown fence rewrite
# ---------------------------------------------------------------------------

# Match a fenced code block: opening fence (3+ backticks OR 3+ tildes)
# optional info string, body, closing fence of the same character class.
# Note: we don't enforce "same length" on the closing fence — that's a
# nice-to-have, not required, and it would need a backreference. We
# use a simple capture group numbered for the body, and re-match the
# fence character class on the close.
_FENCE_RE = re.compile(
    r"(?P<all>"
    r"(?P<open>(?P<och>```+|~~~+))[^\n]*\n"  # opening fence + info string
    r"(?P<body>.*?)"                          # body (non-greedy)
    r"\n?(?P=och)+"                           # closing fence, same char
    r")",
    re.DOTALL,
)


def _fence_rewrite(match: re.Match) -> str:
    """Replace one fenced code block with a single voice-friendly
    summary sentence."""
    body = match.group("body").strip()
    if not body:
        return ""  # empty fence — drop entirely
    # Compact the body: collapse internal newlines to spaces, drop
    # repeated whitespace, cap length. This keeps the spoken reply
    # short while still surfacing the content.
    compact = re.sub(r"\s+", " ", body).strip()
    if len(compact) > 200:
        compact = compact[:197] + "..."
    return f"[Code: {compact}]"


def _rewrite_fences(text: str) -> str:
    """Replace fenced code blocks with `[Code: ...]` summaries.

    Inline code (single backticks) is left as-is — it's typically
    a short token that the segmenter handles fine.
    """
    if "```" not in text and "~~~" not in text:
        return text
    out, n = _FENCE_RE.subn(_fence_rewrite, text)
    if n:
        logger.debug(f"voice sanitiser rewrote {n} fenced code block(s)")
    return out


# ---------------------------------------------------------------------------
# 3. Entry point
# ---------------------------------------------------------------------------


def sanitize_for_tts(text: str) -> str:
    """Apply the M9-D voice-text sanitisation pipeline.

    Order matters:
      1. Strip reasoning blocks (so the segmenter doesn't see them).
      2. Rewrite fenced code blocks to `[Code: ...]` summaries.
      3. Collapse the whitespace that step 2 may have left behind.

    This is the function `HaloResponder.respond_stream` calls
    between `parse_emotion` and `split_sentences`.
    """
    if not text:
        return text
    out = strip_reasoning(text)
    out = _rewrite_fences(out)
    out = re.sub(r"[ \t]+\n", "\n", out)  # trailing whitespace on lines
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


__all__ = [
    "sanitize_for_tts",
    "strip_reasoning",
]

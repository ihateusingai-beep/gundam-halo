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
     `TTS stream failed for '\`\`\`': No audio was received`.
     The audio the user hears becomes fragmented. We rewrite
     fenced code blocks into a single voice-friendly summary
     so they pass through the segmenter without empty chunks.

Sprint 17a adds cross-sentence `<think>` sanitization. The LLM may
open a `<think>` block in one sentence and close it in the next
(this happens with sentence-streamed agents that buffer 1-3
sentences at a time). The single-shot non-greedy regex on its
own cannot suppress the open-tag body — we need a per-turn
state flag threaded through each `sanitize_for_tts()` call.
See `SanitizerState` and the `state` parameter below.

Design:

  - **Server-side**: this runs in `HaloResponder.respond_stream`,
    not in the frontend. The frontend is free to *display* the
    reasoning or the original markdown (debug panel, log
    scrollback); the server decides what gets *spoken*.

  - **Pure-ish functions** (`strip_reasoning`, `sanitize_for_tts`).
    Sprint 17a threads a `SanitizerState` object through both
    functions so the `<think>` state can survive across calls.
    The state is allocated **per turn** by `voice_ws.py`; tests
    pass a fresh `SanitizerState()` per case for hermeticity.
    The state default is `None` (a fresh state is created on
    demand) for backwards-compat with one-shot callers like the
    test suite.

  - **Conservative**: when in doubt, we pass the text through
    untouched. The strip only removes content that matches a
    tight pattern; the markdown rewrite only applies when we
    can detect a real fenced block.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Sprint 17a: per-turn sanitizer state
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class SanitizerState:
    """Per-turn state carried across `sanitize_for_tts()` calls.

    Attributes:
        think_open: True after we have seen the opening `<think>`
            tag of a reasoning block but not yet the matching
            `</think>`. While True, the next call to
            `strip_reasoning()` short-circuits and returns "" until
            the close tag is found, after which the state is
            cleared and the text AFTER the close tag is returned.

    `voice_ws._emit_agent_response_streaming` allocates one
    `SanitizerState` per turn and passes it into every
    `sanitize_for_tts(text, state)` call. The state is discarded
    when the turn ends (or is cancelled), so there is no leak
    between turns.

    Mutable on purpose: we need to flip `think_open` from True
    back to False when the close tag is found. Slots keeps the
    object tiny (one bool) so the per-turn allocation is free.
    """

    think_open: bool = False


# ---------------------------------------------------------------------------
# 1. Reasoning strip
# ---------------------------------------------------------------------------

# Match `<think>…</think>` blocks. Non-greedy, multiline. The pattern
# matches the *outer* fences, so consecutive blocks (`<think>a</think>
# <think>b</think>`) are both caught.
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)

# Match a stray `<think>` opening tag (no close tag in the same
# sentence). Used for cross-sentence state: if we see an open tag
# without a matching close, we set `state.think_open = True` and
# suppress everything until the close arrives.
_THINK_OPEN_RE = re.compile(r"<think>", re.IGNORECASE)

# Match a stray `</think>` closing tag with no preceding open tag
# in the same sentence. The body AFTER this tag is real reply text
# and should be returned; the body BEFORE is reasoning and should
# be suppressed.
_THINK_CLOSE_RE = re.compile(r"</think>", re.IGNORECASE)

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


def strip_reasoning(text: str, state: SanitizerState | None = None) -> str:
    """Remove LLM reasoning blocks from *text*.

    Strips, in order:
      - `<think>…</think>` blocks (MiniMax-M2 / Qwen / DeepSeek style)
      - `<tool_call>…</tool_call>` blocks (defensive, Anthropic-style)
      - Leading "Reasoning: …" prose blocks

    Sprint 17a: the optional `state` argument is the per-turn
    `SanitizerState`. If the previous call left `state.think_open`
    set, this call is a no-op (returns "") until a `</think>` tag
    is found, at which point `state.think_open` is cleared and
    the text after the close tag is returned. Callers in
    `voice_ws.py` allocate one state per turn; the test suite
    passes a fresh state per case.

    Returns the input with leading/trailing whitespace collapsed.
    If nothing matched, returns *text* unchanged.
    """
    if not text:
        return text

    # Lazy-init the state so one-shot callers (legacy tests) work
    # without thinking about threading.
    if state is None:
        state = SanitizerState()

    # ---- Cross-sentence <think> (Sprint 17a) ----
    # If a previous call left the block open, we're inside a
    # reasoning section right now. Look only for the close tag.
    if state.think_open:
        m = _THINK_CLOSE_RE.search(text)
        if not m:
            # Still inside the block; drop the entire chunk.
            return ""
        # Close tag found — clear the flag and return the text
        # AFTER the close tag (reasoning body is suppressed).
        state.think_open = False
        return text[m.end():].strip()

    # ---- Standard in-sentence reasoning strip ----
    # Walk the text left-to-right tracking <think> open/close
    # boundaries manually. The non-greedy `_THINK_RE` would happily
    # chew through any stray `<think>` to the next `</think>` (or
    # end-of-string), which is wrong for our use case: we want
    # to detect when the block is *unclosed* and defer the body
    # to the next call.
    out_parts: list[str] = []
    cursor = 0
    n = len(text)
    while cursor < n:
        open_m = _THINK_OPEN_RE.search(text, cursor)
        if not open_m:
            # No more opens in this chunk. Append the tail and
            # we're done.
            out_parts.append(text[cursor:])
            break
        # Append the prefix between cursor and the open tag.
        out_parts.append(text[cursor:open_m.start()])
        # Look for the matching close tag starting AT the open.
        close_m = _THINK_CLOSE_RE.search(text, open_m.end())
        if not close_m:
            # Open tag with no close in this chunk — record state
            # and stop. The body is in the next sentence(s).
            state.think_open = True
            # The text AFTER the open tag is also reasoning and
            # should be suppressed. The out_parts so far are the
            # safe text we want to keep.
            break
        # Skip past the entire `<think>…</think>` block and
        # continue scanning from the close tag's end.
        cursor = close_m.end()
    out = "".join(out_parts)

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


def sanitize_for_tts(text: str, state: SanitizerState | None = None) -> str:
    """Apply the M9-D voice-text sanitisation pipeline.

    Order matters:
      1. Strip reasoning blocks (so the segmenter doesn't see them).
         Cross-sentence `<think>` state is read from / written to
         `state` (Sprint 17a).
      2. Rewrite fenced code blocks to `[Code: ...]` summaries.
      3. Collapse the whitespace that step 2 may have left behind.

    This is the function `HaloResponder.respond_stream` calls
    between `parse_emotion` and `split_sentences`. `voice_ws.py`
    allocates a fresh `SanitizerState` per turn and passes it
    into every call within the turn.

    Tests may call this with `state=None` for hermetic one-shot
    use — the function lazily creates a throwaway state.
    """
    if not text:
        return text
    if state is None:
        state = SanitizerState()
    out = strip_reasoning(text, state)
    # If we're mid-think-block, skip fence rewriting too — the
    # entire chunk is reasoning and should be suppressed.
    if state.think_open:
        return ""
    out = _rewrite_fences(out)
    out = re.sub(r"[ \t]+\n", "\n", out)  # trailing whitespace on lines
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


__all__ = [
    "sanitize_for_tts",
    "strip_reasoning",
    "SanitizerState",
]

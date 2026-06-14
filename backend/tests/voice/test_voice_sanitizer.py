"""Tests for the M9-D voice-text sanitiser.

The sanitiser has two responsibilities:

  1. Strip LLM reasoning blocks (`<think>…</think>`,
     `<tool_call>…</tool_call>`, leading "Reasoning:" prose) so
     the user doesn't hear the model think out loud.
  2. Rewrite fenced code blocks into `[Code: ...]` summaries
     so the sentence splitter + TTS never see bare fence lines
     (which would produce 0-byte TTS chunks and log
     `TTS stream failed for '\\`\\`\\`': No audio was received`).

These tests exercise the rules directly. The M9-D acceptance
criteria (`docs/tickets/M9-D.md`) is: re-run M9-C live, then
`grep -E "<think>|TTS stream failed" /tmp/m9c_<ts>/transcript.txt`
returns nothing.
"""
from __future__ import annotations

from app.voice.tts.voice_sanitizer import (
    SanitizerState,
    sanitize_for_tts,
    strip_reasoning,
)


# ---------------------------------------------------------------------------
# 1. Reasoning strip
# ---------------------------------------------------------------------------


def test_strip_think_block():
    text = (
        "<think>The user wants the first line of the README. "
        "I should reply in Cantonese.</think>\n"
        "README.md 嘅第一行係：「# Gundam Halo — Backend」。"
    )
    out = strip_reasoning(text)
    assert "<think>" not in out
    assert "</think>" not in out
    assert "I should reply" not in out
    assert "README.md 嘅第一行" in out


def test_strip_multiple_think_blocks():
    text = (
        "<think>reasoning 1</think>answer 1\n\n"
        "<think>reasoning 2</think>answer 2"
    )
    out = strip_reasoning(text)
    assert "reasoning" not in out
    assert "answer 1" in out
    assert "answer 2" in out


def test_strip_think_block_is_case_insensitive():
    text = "<THINK>loud</THINK>hi"
    assert strip_reasoning(text) == "hi"


def test_strip_tool_call_block_defensive():
    text = "before<tool_call>{\"name\": \"file_read\"}</tool_call>after"
    out = strip_reasoning(text)
    assert "before" in out
    assert "after" in out
    assert "file_read" not in out


def test_strip_reasoning_prefix():
    text = (
        "Reasoning: I need to read the file first because the user\n"
        "asked about the contents of README.md.\n\n"
        "The first line is `# Gundam Halo — Backend`."
    )
    out = strip_reasoning(text)
    assert "Reasoning:" not in out
    assert "I need to read" not in out
    assert "The first line" in out


def test_strip_reasoning_chinese_colon():
    """Models sometimes use a full-width `：`."""
    text = "推理：用 file_read 工具。\n\nThe first line is X."
    out = strip_reasoning(text)
    assert "推理" not in out
    assert "The first line" in out


def test_strip_reasoning_preserves_unrelated_text():
    text = "I think this is fine."  # "think" is inside a word, not <think>
    out = strip_reasoning(text)
    assert out == text


def test_strip_collapses_excess_newlines():
    text = "<think>a</think>\n\n\n\n\n<think>b</think>\n\n\nfinal"
    out = strip_reasoning(text)
    assert "\n\n\n" not in out


def test_strip_empty_input():
    assert strip_reasoning("") == ""
    assert strip_reasoning(None) is None  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 2. Markdown fence rewrite
# ---------------------------------------------------------------------------


def test_rewrite_single_fenced_block():
    text = (
        '我讀到 README 嗰行係：\n\n'
        '```\n'
        '# Gundam Halo — Backend\n'
        '```\n\n'
        '希望幫到你。'
    )
    out = sanitize_for_tts(text)
    assert "```" not in out
    assert "[Code:" in out
    assert "# Gundam Halo — Backend" in out
    assert "我讀到 README" in out
    assert "希望幫到你" in out


def test_rewrite_fenced_block_with_language_hint():
    text = (
        "Shell 結果：\n\n"
        "```bash\n"
        "echo hello\n"
        "```\n\n"
        "搞掂。"
    )
    out = sanitize_for_tts(text)
    assert "echo hello" in out
    assert "```" not in out
    assert "bash" not in out  # info string stripped — TTS would mangle it


def test_rewrite_empty_fence():
    text = "intro\n\n```\n```\n\noutro"
    out = sanitize_for_tts(text)
    assert "```" not in out
    # empty fence → no [Code: …] inserted
    assert "intro" in out
    assert "outro" in out
    assert "[Code:" not in out


def test_rewrite_truncates_long_fence():
    long_body = "x" * 500
    text = f"intro\n\n```\n{long_body}\n```\n\noutro"
    out = sanitize_for_tts(text)
    assert "```" not in out
    # 200-char cap + "..." suffix → [Code: xxx...xxx...]
    assert "[Code:" in out
    assert "..." in out


def test_rewrite_collapses_internal_whitespace():
    text = "intro\n\n```\n  foo   bar\n\n  baz  \n```\n\noutro"
    out = sanitize_for_tts(text)
    assert "```" not in out
    assert "foo bar baz" in out


def test_no_fence_unchanged():
    text = "普通嘅句子。\n冇 code fence。\n試下。"
    out = sanitize_for_tts(text)
    assert out == text


def test_inline_backticks_left_alone():
    """Single-backtick inline code is fine; only triple-fence blocks
    need rewriting."""
    text = "Use `file_read` to read the file."
    out = sanitize_for_tts(text)
    assert "file_read" in out
    # Inline backticks preserved (they're single, not 3+)
    assert "`file_read`" in out


# ---------------------------------------------------------------------------
# 3. Combined: the M9-C regression fixture
# ---------------------------------------------------------------------------


M9C_REGRESSION_INPUT = (
    "<think>\n"
    "The user asked for the first line of the README.md file. "
    "The first line is:\n\n"
    "# Gundam Halo — Backend\n\n"
    "I should reply in Cantonese as requested.\n"
    "</think>\n\n"
    "README.md 嘅第一行係：\n\n"
    "```\n"
    "# Gundam Halo — Backend\n"
    "```\n"
)


def test_full_m9c_regression_fixture():
    out = sanitize_for_tts(M9C_REGRESSION_INPUT)
    # No leaked reasoning
    assert "<think>" not in out
    assert "I should reply" not in out
    # No bare fences
    assert "```" not in out
    # Content preserved as a `[Code: …]` summary
    assert "README.md 嘅第一行係" in out
    assert "[Code:" in out
    assert "# Gundam Halo — Backend" in out


def test_full_sanitize_with_emotion_tag():
    """The `[EMO:calm]` tag should survive the sanitisation so
    HaloResponder's emotion parser still sees it."""
    text = "[EMO:calm] " + M9C_REGRESSION_INPUT
    out = sanitize_for_tts(text)
    assert out.startswith("[EMO:calm]")


def test_full_sanitize_idempotent():
    """Running sanitise twice should not further modify the text."""
    once = sanitize_for_tts(M9C_REGRESSION_INPUT)
    twice = sanitize_for_tts(once)
    assert once == twice


# ---------------------------------------------------------------------------
# 4. Sprint 17a: cross-sentence `<think>` state threading
# ---------------------------------------------------------------------------
#
# The LLM may open a `<think>` block in one sentence and close it
# in the next. The single-shot non-greedy `_THINK_RE` cannot
# suppress the body of an unclosed block — it just leaves the
# open-tag text in the output. `strip_reasoning()` and
# `sanitize_for_tts()` therefore accept a `SanitizerState` and
# thread it across calls. The test cases below exercise the
# cross-sentence paths and the state-cleanup guarantees.


def test_think_block_open_then_close_across_sentences():
    """`<think>` opens in sentence 1, closes in sentence 2.

    Sentence 1 should be empty (open tag, no body to keep).
    Sentence 2 should contain the text AFTER the close tag
    (the body between open and close is reasoning, suppressed).
    """
    state = SanitizerState()
    s1 = strip_reasoning("<think>The user wants X.", state)
    assert s1 == ""
    assert state.think_open is True

    # Real-world pattern: sentence 2 carries the answer
    # followed by the close tag. Body between open (in
    # sentence 1) and close (in sentence 2) is reasoning and
    # is suppressed; only the text AFTER the close tag is
    # returned.
    s2 = strip_reasoning("</think>Y is the answer.", state)
    assert s2 == "Y is the answer."
    assert "</think>" not in s2
    assert state.think_open is False


def test_think_block_open_across_three_sentences():
    """`<think>` opens in sentence 1, stays open through 2, closes in 3."""
    state = SanitizerState()
    assert strip_reasoning("<think>planning", state) == ""
    assert state.think_open is True
    assert strip_reasoning("still planning", state) == ""
    assert state.think_open is True
    out = strip_reasoning("done now.</think>real reply text", state)
    assert out == "real reply text"
    assert state.think_open is False


def test_think_state_resets_between_independent_calls():
    """A fresh SanitizerState is a hermetic starting point.

    Two independent strip_reasoning() calls in sequence (each
    with a fresh state) should both see the close tag in the
    same chunk and behave like the legacy single-shot path.
    """
    state_a = SanitizerState()
    state_b = SanitizerState()
    # State A handles a complete in-sentence block.
    assert strip_reasoning("<think>r</think>plain", state_a) == "plain"
    assert state_a.think_open is False
    # State B handles an open block; same text on its own would
    # have been suppressed had state_b inherited state_a.
    assert strip_reasoning("<think>r</think>plain", state_b) == "plain"
    assert state_b.think_open is False


def test_sanitize_for_tts_with_cross_sentence_state():
    """sanitize_for_tts() also threads the state."""
    state = SanitizerState()
    assert sanitize_for_tts("<think>reasoning", state) == ""
    assert state.think_open is True
    out = sanitize_for_tts("more reasoning</think>visible answer", state)
    assert out == "visible answer"
    assert state.think_open is False


def test_sanitize_for_tts_drops_chunks_while_think_open():
    """While the state has think_open=True, sanitize_for_tts
    returns "" for any chunk (not just strip_reasoning's
    narrow path). This prevents a stray `<think>…` body from
    leaking via the fence-rewrite step."""
    state = SanitizerState()
    # First chunk opens the block.
    assert sanitize_for_tts("<think>step 1", state) == ""
    # Second chunk contains a code fence — but we're mid-block,
    # so the whole chunk is suppressed.
    assert sanitize_for_tts("```\nsecret\n```", state) == ""
    assert state.think_open is True
    # Third chunk closes the block.
    out = sanitize_for_tts("ok now.</think>final answer", state)
    assert out == "final answer"
    assert state.think_open is False


def test_state_none_still_works_legacy_compat():
    """Calling strip_reasoning(text) with no state argument
    should not break (Sprint 16 callers + one-shot tests)."""
    assert strip_reasoning("<think>r</think>ok") == "ok"
    assert sanitize_for_tts("<think>r</think>ok") == "ok"


def test_think_open_with_no_body_then_close_in_same_chunk():
    """Edge case: `<think></think>` and then more text in the
    same chunk. The close is right after the open, so the
    in-sentence path catches it (no state needed)."""
    state = SanitizerState()
    out = strip_reasoning("<think></think>real text", state)
    assert out == "real text"
    assert state.think_open is False

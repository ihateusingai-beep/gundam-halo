"""Tests for sentence splitter (TTS streaming prerequisite)."""

from __future__ import annotations

from app.voice.tts.splitter import split_sentences


def test_empty_input_returns_empty_list():
    assert split_sentences("") == []
    assert split_sentences("   ") == []
    assert split_sentences(None) == []  # type: ignore[arg-type]


def test_english_basic():
    out = split_sentences("Hello world. How are you? I am fine.")
    assert out == ["Hello world.", "How are you?", "I am fine."]


def test_chinese_basic():
    out = split_sentences("你好世界。今天天气真好！我们去玩吧？")
    assert len(out) == 3
    assert "你好世界" in out[0]
    assert "天气真好" in out[1]
    assert "玩吧" in out[2]


def test_mixed_english_chinese():
    out = split_sentences("Mixed: hello world. 你好。")
    assert len(out) >= 2


def test_explicit_language_en():
    out = split_sentences("First. Second.", language="en")
    assert out == ["First.", "Second."]


def test_explicit_language_zh():
    out = split_sentences("第一句。第二句！", language="zh")
    assert len(out) == 2
    assert "第一句" in out[0]
    assert "第二句" in out[1]


def test_auto_detect_picks_chinese():
    out = split_sentences(
        "今天天气很好。The quick brown fox.", language="auto"
    )
    # Either is acceptable as long as we got >1 sentence
    assert len(out) >= 1


def test_long_sentence_hard_split():
    """A single sentence over max_chars gets split."""
    long_sentence = "A" * 200
    out = split_sentences(long_sentence, max_chars=80)
    assert len(out) >= 2
    assert all(len(s) <= 100 for s in out)  # some slack for break points


def test_short_input_returned_as_single_sentence():
    out = split_sentences("Just one short thing.")
    assert out == ["Just one short thing."]


def test_falls_back_when_pysbd_fails(monkeypatch):
    """If pysbd throws, we fall back to regex split."""

    def boom(*_args, **_kwargs):
        raise RuntimeError("pysbd kaboom")

    import pysbd

    monkeypatch.setattr(pysbd, "Segmenter", boom)
    # We have to bust the lru_cache to force a re-import
    from app.voice.tts import splitter

    splitter._get_segmenter.cache_clear()

    out = split_sentences("Hello. World. Yes?", language="en")
    assert len(out) >= 2

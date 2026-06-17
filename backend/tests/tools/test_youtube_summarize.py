"""Tests for YouTubeSummarizeTool (Sprint 27 Track 27.2).

Per `docs/FEATURE-SPEC-SPRINT27.md` §4.2 Track 27.2.

Test categories:
  1. Schema + name
  2. URL parsing (4 formats: watch, youtu.be, shorts, embed)
  3. Transcript fetch (mocked youtube-transcript-api)
  4. Transcript format + cap
  5. oEmbed fallback (when transcript dep missing or fails)
  6. Error paths (invalid URL, no video ID, etc.)
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.tools.youtube_summarize import (
    OEMBED_URL,
    YouTubeSummarizeError,
    YouTubeSummarizeTool,
    _extract_video_id,
    _format_transcript_for_llm,
)


# ---------------------------------------------------------------------------
# 1. Schema + name
# ---------------------------------------------------------------------------


class TestSchema:
    def test_name(self):
        assert YouTubeSummarizeTool().name == "youtube_summarize"

    def test_required_param(self):
        assert "url" in YouTubeSummarizeTool().parameters["required"]


# ---------------------------------------------------------------------------
# 2. URL parsing
# ---------------------------------------------------------------------------


class TestURLExtraction:
    def test_watch_url(self):
        assert _extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_short_url(self):
        assert _extract_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_shorts_url(self):
        assert _extract_video_id("https://www.youtube.com/shorts/abc123XYZ") == "abc123XYZ"

    def test_embed_url(self):
        assert _extract_video_id("https://www.youtube.com/embed/xyz789") == "xyz789"

    def test_nocookie_url(self):
        assert _extract_video_id("https://www.youtube-nocookie.com/embed/abc") == "abc"

    def test_invalid_url(self):
        assert _extract_video_id("https://example.com") is None

    def test_empty_url(self):
        assert _extract_video_id("") is None

    def test_url_with_extra_query_params(self):
        # watch?v=ID&t=42s&list=PL123 should still extract ID
        assert _extract_video_id(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=42s"
        ) == "dQw4w9WgXcQ"


# ---------------------------------------------------------------------------
# 3. Transcript format + cap
# ---------------------------------------------------------------------------


class TestTranscriptFormat:
    def test_format_basic(self):
        transcript = [
            {"text": "Hello", "start": 0.0, "duration": 1.0},
            {"text": "world", "start": 1.0, "duration": 1.0},
        ]
        out = _format_transcript_for_llm(transcript, max_chars=100)
        assert "Hello" in out
        assert "world" in out

    def test_format_caps_at_max_chars(self):
        # 1000 entries of 100 chars each = 100,000 chars total
        transcript = [
            {"text": "A" * 100, "start": float(i), "duration": 1.0}
            for i in range(1000)
        ]
        out = _format_transcript_for_llm(transcript, max_chars=500)
        # Output should be capped at ~500 chars
        assert len(out) <= 510  # allow for trailing "..."

    def test_format_skips_empty_text(self):
        transcript = [
            {"text": "", "start": 0.0, "duration": 1.0},
            {"text": "actual content", "start": 1.0, "duration": 1.0},
            {"text": "   ", "start": 2.0, "duration": 1.0},
        ]
        out = _format_transcript_for_llm(transcript, max_chars=1000)
        assert "actual content" in out
        # Empty / whitespace-only entries should be skipped
        assert "   " not in out
        assert out.strip() == "actual content"

    def test_format_empty_transcript(self):
        out = _format_transcript_for_llm([], max_chars=1000)
        assert out == ""


# ---------------------------------------------------------------------------
# 4. run() with mocked transcript
# ---------------------------------------------------------------------------


SAMPLE_TRANSCRIPT = [
    {"text": "Welcome to my Cantonese tutorial.", "start": 0.0, "duration": 3.0},
    {"text": "Today we'll learn 5 common phrases.", "start": 3.0, "duration": 4.0},
    {"text": "First, 早晨 — good morning.", "start": 7.0, "duration": 3.0},
    {"text": "Second, 唔該 — please or thank you.", "start": 10.0, "duration": 4.0},
]


class TestRunWithTranscript:
    @pytest.mark.asyncio
    async def test_run_returns_transcript(self):
        with patch(
            "app.tools.youtube_summarize._fetch_transcript",
            return_value=SAMPLE_TRANSCRIPT,
        ):
            tool = YouTubeSummarizeTool()
            out = await tool.run(url="https://www.youtube.com/watch?v=dQw4w9WgXcQ")

        assert "Transcript of YouTube video dQw4w9WgXcQ" in out
        assert "Welcome to my Cantonese tutorial." in out
        assert "早晨" in out
        assert "唔該" in out
        assert "4 segments" in out

    @pytest.mark.asyncio
    async def test_run_respects_max_transcript_chars(self):
        with patch(
            "app.tools.youtube_summarize._fetch_transcript",
            return_value=SAMPLE_TRANSCRIPT,
        ):
            tool = YouTubeSummarizeTool()
            out = await tool.run(
                url="https://www.youtube.com/watch?v=abc",
                max_transcript_chars=50,
            )
        # Output should respect the cap
        # (50 chars of transcript + header ≈ 80 chars total)
        assert len(out) < 200


# ---------------------------------------------------------------------------
# 5. oEmbed fallback
# ---------------------------------------------------------------------------


class TestOEMbedFallback:
    @pytest.mark.asyncio
    async def test_fallback_when_dep_missing(self):
        # Simulate youtube-transcript-api not installed
        with patch(
            "app.tools.youtube_summarize._fetch_transcript",
            side_effect=ImportError("No module named 'youtube_transcript_api'"),
        ):
            # Mock oEmbed success
            with patch(
                "app.tools.youtube_summarize._fetch_oembed_metadata",
                new_callable=AsyncMock,
            ) as mock_oembed:
                mock_oembed.return_value = {
                    "title": "Cantonese Tutorial Episode 1",
                    "author_name": "CantoneseTeacher",
                }
                tool = YouTubeSummarizeTool()
                out = await tool.run(url="https://www.youtube.com/watch?v=abc")

        assert "Could not fetch the transcript" in out
        assert "youtube-transcript-api is not installed" in out
        assert "Cantonese Tutorial Episode 1" in out
        assert "CantoneseTeacher" in out

    @pytest.mark.asyncio
    async def test_fallback_when_transcript_disabled(self):
        with patch(
            "app.tools.youtube_summarize._fetch_transcript",
            side_effect=Exception("TranscriptsDisabled"),
        ):
            with patch(
                "app.tools.youtube_summarize._fetch_oembed_metadata",
                new_callable=AsyncMock,
            ) as mock_oembed:
                mock_oembed.return_value = {
                    "title": "Private Video",
                    "author_name": "SomeUser",
                }
                tool = YouTubeSummarizeTool()
                out = await tool.run(url="https://www.youtube.com/watch?v=abc")

        assert "transcript fetch failed" in out
        assert "TranscriptsDisabled" in out
        assert "Private Video" in out

    @pytest.mark.asyncio
    async def test_fallback_when_oembed_also_fails(self):
        with patch(
            "app.tools.youtube_summarize._fetch_transcript",
            side_effect=ImportError,
        ):
            with patch(
                "app.tools.youtube_summarize._fetch_oembed_metadata",
                new_callable=AsyncMock,
            ) as mock_oembed:
                mock_oembed.return_value = None  # oEmbed also failed
                tool = YouTubeSummarizeTool()
                out = await tool.run(url="https://www.youtube.com/watch?v=abc")

        assert "Error" in out
        assert "oEmbed metadata either" in out


# ---------------------------------------------------------------------------
# 6. Error paths
# ---------------------------------------------------------------------------


class TestErrors:
    @pytest.mark.asyncio
    async def test_empty_url(self):
        out = await YouTubeSummarizeTool().run(url="")
        assert "Error" in out
        assert "url" in out

    @pytest.mark.asyncio
    async def test_whitespace_url(self):
        out = await YouTubeSummarizeTool().run(url="   ")
        assert "Error" in out

    @pytest.mark.asyncio
    async def test_invalid_url_format(self):
        out = await YouTubeSummarizeTool().run(url="https://example.com")
        assert "Error" in out
        assert "video ID" in out

    @pytest.mark.asyncio
    async def test_empty_transcript_falls_back(self):
        with patch(
            "app.tools.youtube_summarize._fetch_transcript",
            return_value=[],
        ):
            with patch(
                "app.tools.youtube_summarize._fetch_oembed_metadata",
                new_callable=AsyncMock,
            ) as mock_oembed:
                mock_oembed.return_value = {
                    "title": "Empty Video",
                    "author_name": "User",
                }
                tool = YouTubeSummarizeTool()
                out = await tool.run(url="https://www.youtube.com/watch?v=abc")

        assert "transcript is empty" in out
        assert "Empty Video" in out

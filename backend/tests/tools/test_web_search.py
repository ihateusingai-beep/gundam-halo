"""Tests for WebSearchTool (Sprint 27 Track 27.1).

Per `docs/FEATURE-SPEC-SPRINT27.md` §4.2 Track 27.1.

Test categories:
  1. Schema + name (LLM spec contract)
  2. DDG HTML endpoint (mocked via respx, same pattern
     as `tests/tools/test_web_tools.py`)
  3. HTML parser (DDG redirect URL decode, tag strip)
  4. search / compare modes
  5. Error paths (timeout, HTTP error, empty results, invalid args)
  6. TTS-friendly output (no markdown fences, prose only)
"""
from __future__ import annotations

import httpx
import pytest
import respx

from app.tools.web_search import (
    DDG_HTML_URL,
    WebSearchError,
    WebSearchTool,
    _decode_ddg_redirect_url,
    _parse_ddg_html,
    _strip_html_tags,
)


# ---------------------------------------------------------------------------
# 1. Schema + name
# ---------------------------------------------------------------------------


class TestSchema:
    def test_name(self):
        assert WebSearchTool().name == "web_search"

    def test_required_param(self):
        assert "query" in WebSearchTool().parameters["required"]

    def test_to_spec(self):
        spec = WebSearchTool().to_spec()
        assert spec["type"] == "function"
        assert spec["function"]["name"] == "web_search"
        assert "query" in spec["function"]["parameters"]["properties"]


# ---------------------------------------------------------------------------
# 2. HTML parser
# ---------------------------------------------------------------------------


class TestParser:
    def test_strip_html_tags(self):
        assert _strip_html_tags("<b>hello</b> world") == "hello world"
        assert _strip_html_tags("a&#x27;b") == "a'b"
        assert _strip_html_tags("&quot;hi&quot;") == '"hi"'
        assert _strip_html_tags("<a>x</a>&amp;<b>y</b>") == "x&y"

    def test_decode_ddg_redirect_url(self):
        # Real DDG redirect format
        assert _decode_ddg_redirect_url(
            "//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2F&rut=abc"
        ) == "https://example.com/"
        # Non-redirect URL passes through
        assert _decode_ddg_redirect_url("https://example.com") == "https://example.com"

    def test_parse_ddg_html_basic(self):
        html = """
        <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2F">Example Title</a>
        <a class="result__snippet">This is the snippet text.</a>
        <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Ftest.com%2F">Test</a>
        <a class="result__snippet">Another snippet.</a>
        """
        results = _parse_ddg_html(html, max_results=5)
        assert len(results) == 2
        assert results[0]["title"] == "Example Title"
        assert results[0]["url"] == "https://example.com/"
        assert results[0]["snippet"] == "This is the snippet text."
        assert results[1]["title"] == "Test"

    def test_parse_ddg_html_caps_max_results(self):
        html = ""
        for i in range(10):
            html += f'<a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2F{i}.com%2F">T{i}</a>\n'
            html += f'<a class="result__snippet">S{i}</a>\n'
        results = _parse_ddg_html(html, max_results=3)
        assert len(results) == 3

    def test_parse_ddg_html_handles_malformed(self):
        # No matches → empty list
        assert _parse_ddg_html("nothing here", max_results=5) == []


# ---------------------------------------------------------------------------
# 3. search mode
# ---------------------------------------------------------------------------


SAMPLE_DDG_HTML = """
<html><body>
<a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Farticle1">First Result</a>
<a class="result__snippet">Snippet for the first result.</a>
<a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Farticle2">Second Result</a>
<a class="result__snippet">Snippet for the second result.</a>
<a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Farticle3">Third Result</a>
<a class="result__snippet">Snippet for the third result.</a>
</body></html>
"""


class TestSearchMode:
    @pytest.mark.asyncio
    @respx.mock
    async def test_search_returns_top_results(self):
        respx.get(DDG_HTML_URL).mock(return_value=httpx.Response(200, text=SAMPLE_DDG_HTML))

        tool = WebSearchTool()
        out = await tool.run(query="python tutorial")

        assert "Top 3 results for 'python tutorial'" in out
        assert "First Result" in out
        assert "Second Result" in out
        assert "Third Result" in out
        assert "https://example.com/article1" in out

    @pytest.mark.asyncio
    @respx.mock
    async def test_search_respects_max_results(self):
        respx.get(DDG_HTML_URL).mock(return_value=httpx.Response(200, text=SAMPLE_DDG_HTML))

        tool = WebSearchTool()
        out = await tool.run(query="python", max_results=1)
        assert "Top 1 result" in out
        # Only the first result should be in the output
        lines = out.split("\n")
        # Skip the header line, count numbered result lines
        result_lines = [ln for ln in lines[1:] if ln.startswith("1.")]
        assert len(result_lines) == 1

    @pytest.mark.asyncio
    async def test_search_rejects_empty_query(self):
        out = await WebSearchTool().run(query="")
        assert "Error" in out
        assert "query" in out

    @pytest.mark.asyncio
    async def test_search_rejects_whitespace_query(self):
        out = await WebSearchTool().run(query="   ")
        assert "Error" in out

    @pytest.mark.asyncio
    @respx.mock
    async def test_search_handles_no_results(self):
        respx.get(DDG_HTML_URL).mock(
            return_value=httpx.Response(200, text="<html><body>No results</body></html>")
        )
        out = await WebSearchTool().run(query="obscure_query")
        assert "Error" in out
        assert "no results" in out.lower()

    @pytest.mark.asyncio
    @respx.mock
    async def test_search_handles_timeout(self):
        respx.get(DDG_HTML_URL).mock(side_effect=httpx.TimeoutException("timeout"))
        out = await WebSearchTool().run(query="test")
        assert "Error" in out
        assert "timed out" in out.lower()

    @pytest.mark.asyncio
    @respx.mock
    async def test_search_handles_http_error(self):
        respx.get(DDG_HTML_URL).mock(return_value=httpx.Response(503))
        out = await WebSearchTool().run(query="test")
        assert "Error" in out
        assert "503" in out


# ---------------------------------------------------------------------------
# 4. compare mode
# ---------------------------------------------------------------------------


class TestCompareMode:
    @pytest.mark.asyncio
    @respx.mock
    async def test_compare_two_items(self):
        # First call → first item results, second call → second item
        respx.get(DDG_HTML_URL).mock(return_value=httpx.Response(200, text=SAMPLE_DDG_HTML))

        tool = WebSearchTool()
        out = await tool.run(
            query="compare",
            mode="compare",
            items=["X", "Y"],
            aspect="price",
        )
        assert "Comparison of 2 items on 'price'" in out
        assert "X:" in out
        assert "Y:" in out

    @pytest.mark.asyncio
    async def test_compare_rejects_too_many_items(self):
        out = await WebSearchTool().run(
            query="compare",
            mode="compare",
            items=["a", "b", "c", "d", "e", "f"],  # 6 items, max 5
        )
        assert "Error" in out
        assert "max length" in out.lower()

    @pytest.mark.asyncio
    @respx.mock
    async def test_compare_with_empty_items_falls_through_to_search(self):
        """If mode='compare' but items is empty, the tool
        falls through to standard search mode (no error)
        — the user might have forgotten to pass items, and
        a search is more useful than a hard error."""
        from unittest.mock import AsyncMock, patch
        tool = WebSearchTool()
        # Patch the instance method (not the class) so
        # respx can intercept the HTTP call to DDG.
        tool._ddg_search = AsyncMock(return_value=[
            {"title": "T1", "url": "https://x.com", "snippet": "S1"},
        ])
        out = await tool.run(query="test", mode="compare", items=[])
        assert "Top 1 result" in out
        assert "T1" in out


# ---------------------------------------------------------------------------
# 5. Output format (TTS-friendly)
# ---------------------------------------------------------------------------


class TestOutputFormat:
    @pytest.mark.asyncio
    @respx.mock
    async def test_no_markdown_fences(self):
        respx.get(DDG_HTML_URL).mock(return_value=httpx.Response(200, text=SAMPLE_DDG_HTML))

        out = await WebSearchTool().run(query="test")
        # No markdown code fences, headers, or bold markers
        assert "```" not in out
        assert "##" not in out
        assert "**" not in out

    @pytest.mark.asyncio
    @respx.mock
    async def test_caps_at_summary_max_chars(self):
        # Long snippets to verify the cap
        long_html = """
        <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2F1">T1</a>
        <a class="result__snippet">""" + ("A" * 500) + """</a>
        <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2F2">T2</a>
        <a class="result__snippet">""" + ("B" * 500) + """</a>
        """
        respx.get(DDG_HTML_URL).mock(return_value=httpx.Response(200, text=long_html))

        out = await WebSearchTool().run(query="test")
        # The output should be capped at summary_max_chars (800) plus header overhead
        assert len(out) < 1200

    @pytest.mark.asyncio
    @respx.mock
    async def test_output_starts_with_header(self):
        respx.get(DDG_HTML_URL).mock(return_value=httpx.Response(200, text=SAMPLE_DDG_HTML))

        out = await WebSearchTool().run(query="my query")
        first_line = out.split("\n")[0]
        assert "Top" in first_line
        assert "my query" in first_line

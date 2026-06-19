"""web_search tool — DuckDuckGo HTML search (no API key, no extra dep).

Sprint 27 (per `docs/FEATURE-SPEC-SPRINT27.md` §4.2 Track 27.1).

Searches DuckDuckGo via its public HTML endpoint
(`https://html.duckduckgo.com/html/?q=...`) and returns
either:
  - `mode="search"`: a list of result snippets (title, URL, snippet).
  - `mode="compare"`: a side-by-side list of `items` for comparison.

The tool is **deliberately dep-free**: it uses the existing
`httpx.AsyncClient` (already in the venv via `web_fetch.py`),
not the `ddgs` / `duckduckgo-search` library. This keeps
the `voice-hf` extra's install footprint small and lets
the test suite mock the HTTP layer with `respx` (the same
pattern as `tests/tools/test_web_tools.py`).

DDG's HTML endpoint is the same one `ddgs.text()` hits
under the hood; the HTML parser is robust enough for
DuckDuckGo's stable result shape (`.result__a` for title,
`.result__snippet` for snippet, `.result__url` for URL).

Mark-XL's web_search used `ddgs` + Gemini summarisation;
we keep the same DuckDuckGo source but route summarisation
through the Gundam Halo LLM engine (`app.engines.minimax`).
For the v0.1.5+ base the tool returns the raw result list
as pre-formatted prose — the agent's `NativeReAct` loop
calls the LLM to summarise the prose in the next turn.

Voice path: the returned string is TTS-friendly prose
(no markdown fences, no bullet points). The
`voice_sanitizer.py` post-processor strips stray
markdown, but the tool should pre-format where possible.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import unquote

import httpx

from app.tools._stubs import BaseTool
from app.core.registry import register_tool

logger = logging.getLogger(__name__)

DDG_HTML_URL = "https://html.duckduckgo.com/html/"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36 GundamHalo/0.1"
)
DEFAULT_TIMEOUT_S = 10.0
DEFAULT_MAX_RESULTS = 5
DEFAULT_SUMMARY_MAX_CHARS = 800

# Regex patterns extracted from DDG's HTML output. The
# `.result__a` selector (anchors inside result divs)
# gives us the title + href; `.result__snippet` is the
# snippet. The exact class names are stable as of
# 2026-06-17; if DDG redesigns, the regex needs updating.
_TITLE_RE = re.compile(
    r'<a[^>]*class="result__a"[^>]*href="(?P<url>[^"]+)"[^>]*>(?P<title>.*?)</a>',
    re.DOTALL,
)
_SNIPPET_RE = re.compile(
    r'<a[^>]*class="result__snippet"[^>]*>(?P<snippet>.*?)</a>',
    re.DOTALL,
)


def _strip_html_tags(text: str) -> str:
    """Strip HTML tags and decode entities. Used to
    clean DDG's title + snippet strings (which contain
    `<b>` highlight tags around query keywords)."""
    # Decode common HTML entities FIRST (DDG uses &#x27; for ',
    # &quot; for ", &amp; for &, etc.). Doing this before
    # tag-stripping means `&amp;` becomes `&`, not part of
    # a tag-mangled string.
    text = (
        text.replace("&#x27;", "'")
        .replace("&quot;", '"')
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&nbsp;", " ")
    )
    # Remove tags
    text = re.sub(r"<[^>]+>", "", text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _decode_ddg_redirect_url(url: str) -> str:
    """DDG's HTML endpoint returns redirect URLs of the
    form `//duckduckgo.com/l/?uddg=<encoded_url>`. Decode
    the `uddg` parameter to get the actual result URL."""
    if "uddg=" in url:
        # Extract the encoded URL
        m = re.search(r"uddg=([^&]+)", url)
        if m:
            return unquote(m.group(1))
    return url


def _parse_ddg_html(html: str, max_results: int) -> List[Dict[str, str]]:
    """Parse DDG's HTML response into a list of
    `{title, url, snippet}` dicts. Returns up to
    `max_results` results."""
    titles = _TITLE_RE.findall(html)
    snippets = _SNIPPET_RE.findall(html)

    results: List[Dict[str, str]] = []
    for i, (url, raw_title) in enumerate(titles[:max_results]):
        title = _strip_html_tags(raw_title)
        actual_url = _decode_ddg_redirect_url(url)
        snippet = _strip_html_tags(snippets[i]) if i < len(snippets) else ""
        if title and actual_url:
            results.append({
                "title": title,
                "url": actual_url,
                "snippet": snippet,
            })
    return results


class WebSearchError(RuntimeError):
    """Raised on DDG errors (timeout, non-200, parse failure)."""


@register_tool("web_search")
class WebSearchTool(BaseTool):
    """Search the web via DuckDuckGo's HTML endpoint.

    Returns a TTS-friendly prose list of the top results.
    The agent's NativeReAct loop will call the LLM in
    the next turn to summarise the prose into a final
    answer.
    """

    name = "web_search"
    description = (
        "Search the web for a query. Returns the top "
        "results from DuckDuckGo as a prose list (title, "
        "URL, snippet). For 'compare X vs Y' queries, pass "
        "`items=['X', 'Y']` to get a side-by-side comparison. "
        "Use this when the agent needs fresh information "
        "(news, prices, specs, reviews) that the LLM doesn't "
        "know from training. No API key required."
    )
    parameters: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "The search query. Examples: 'latest iPhone "
                    "release date', 'best Cantonese learning apps 2026'."
                ),
            },
            "mode": {
                "type": "string",
                "enum": ["search", "compare"],
                "description": (
                    "'search' (default) returns a flat result list. "
                    "'compare' returns a side-by-side comparison of "
                    "the `items`."
                ),
            },
            "items": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Items to compare (only when mode='compare'). "
                    "Example: ['MacBook Pro M4', 'Dell XPS 15']."
                ),
            },
            "aspect": {
                "type": "string",
                "enum": ["general", "price", "specs", "reviews"],
                "description": (
                    "Comparison aspect. 'price' emphasises cost; "
                    "'specs' emphasises technical details; 'reviews' "
                    "emphasises user ratings. Default 'general'."
                ),
            },
            "max_results": {
                "type": "integer",
                "description": (
                    "How many results to fetch (1-10). Default 5."
                ),
            },
        },
        "required": ["query"],
    }

    async def run(
        self,
        query: str,
        mode: str = "search",
        items: Optional[List[str]] = None,
        aspect: str = "general",
        max_results: int = DEFAULT_MAX_RESULTS,
        **_: Any,
    ) -> str:
        if not isinstance(query, str) or not query.strip():
            return "Error: 'query' is required and must be a non-empty string"
        query = query.strip()

        # `mode == "compare"` with `items` set: search each item
        # individually and combine the results.
        if mode == "compare" and items:
            if not isinstance(items, list) or not items:
                return "Error: 'items' must be a non-empty list when mode='compare'"
            if len(items) > 5:
                return "Error: 'items' max length is 5 (use 'search' for broader queries)"
            per_item_results: Dict[str, List[Dict[str, str]]] = {}
            for item in items:
                if not isinstance(item, str) or not item.strip():
                    continue
                single_query = f"{item} {aspect}" if aspect != "general" else item
                try:
                    per_item_results[item] = await self._ddg_search(
                        single_query.strip(), max_results
                    )
                except WebSearchError as e:
                    return f"Error: DDG search failed for {item!r} — {e}"
            return self._format_comparison(per_item_results, aspect)

        # Standard search
        try:
            results = await self._ddg_search(query, max_results)
        except WebSearchError as e:
            return f"Error: {e}"
        return self._format_results(results, query)

    async def _ddg_search(self, query: str, max_results: int) -> List[Dict[str, str]]:
        """Hit DDG's HTML endpoint and parse the response.

        Runs in the event loop (httpx is async-native),
        not via `asyncio.to_thread` — DDG's response is
        typically <50 KB and the parse is <50ms.
        """
        try:
            async with httpx.AsyncClient(
                timeout=DEFAULT_TIMEOUT_S,
                follow_redirects=True,
                headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
            ) as client:
                resp = await client.get(
                    DDG_HTML_URL,
                    params={"q": query},
                )
                resp.raise_for_status()
                html = resp.text[: 64 * 1024]  # cap at 64 KB
        except httpx.TimeoutException as e:
            raise WebSearchError(f"DDG timed out for {query!r}") from e
        except httpx.HTTPStatusError as e:
            raise WebSearchError(
                f"DDG returned HTTP {e.response.status_code}"
            ) from e
        except Exception as e:  # noqa: BLE001
            logger.exception("DDG search failed")
            raise WebSearchError(f"DDG search failed: {e}") from e

        results = _parse_ddg_html(html, max_results)
        if not results:
            raise WebSearchError(
                f"DDG returned no results for {query!r} "
                f"(possibly rate-limited; try again in a few minutes)"
            )
        return results

    def _format_results(self, results: List[Dict[str, str]], query: str) -> str:
        """Format the result list as TTS-friendly prose.

        Each result is a single line:
          "1. {title} — {url} — {snippet}"

        The list is capped at `summary_max_chars` to avoid
        blowing the 60s TTS budget.
        """
        if not results:
            return f"No results found for {query!r}."

        out: List[str] = []
        total = 0
        for i, r in enumerate(results, start=1):
            line = f"{i}. {r['title']} — {r['url']}"
            if r["snippet"]:
                line += f" — {r['snippet']}"
            if total + len(line) > DEFAULT_SUMMARY_MAX_CHARS:
                break
            out.append(line)
            total += len(line)

        header = f"Top {len(out)} result{'s' if len(out) != 1 else ''} for {query!r}:"
        return header + "\n" + "\n".join(out)

    def _format_comparison(
        self,
        per_item: Dict[str, List[Dict[str, str]]],
        aspect: str,
    ) -> str:
        """Format a side-by-side comparison as TTS-friendly prose.

        Example output:
          "Comparison of 2 items on 'price':

          MacBook Pro M4: 1. Apple announces M4 ... 2. ...
          Dell XPS 15: 1. Dell refreshes XPS ... 2. ..."
        """
        if not per_item:
            return "No comparison results."

        aspect_label = f" on {aspect!r}" if aspect != "general" else ""
        out: List[str] = [f"Comparison of {len(per_item)} items{aspect_label}:", ""]
        for item, results in per_item.items():
            if not results:
                out.append(f"{item}: no results")
                continue
            snippets: List[str] = []
            total = 0
            for r in results[:2]:  # top 2 per item
                snippet = f"{r['title']} — {r['snippet']}" if r["snippet"] else r["title"]
                if total + len(snippet) > DEFAULT_SUMMARY_MAX_CHARS // 2:
                    break
                snippets.append(snippet)
                total += len(snippet)
            out.append(f"{item}: {' / '.join(snippets)}")
            out.append("")  # blank line between items

        return "\n".join(out).rstrip()


__all__ = ["WebSearchTool", "WebSearchError"]

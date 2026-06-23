---
name: web_search
description: Search the web via DuckDuckGo HTML endpoint. Returns top N results with title + URL + snippet.
user-invocable: true
---

# web_search

DuckDuckGo HTML search (no API key). Returns top N results
with title, URL, and a snippet. Configurable via
`VoiceConfig.tools.web_search.max_results` and
`request_timeout_s` (default 5 / 10s).

## Operating Loop

1. **Don't search for things you can compute.** "What is
   17 × 23?" — calculate it. "What's the capital of
   France?" — already known. Web search is for current
   events, obscure facts, or recent releases.
2. **For news, append `news:` or filter by date in the
   query.** DuckDuckGo's HTML endpoint doesn't have a
   native date filter, but the query syntax supports
   `date:1d` / `date:1w` / etc.
3. **Cite sources.** When you use a web search result in a
   reply, name the URL. The cockpit's ActivityTicker
   already logs each search; the user can audit what the
   agent looked up.

## Examples

```
web_search(query="MiniMax M3 cluster pricing")
web_search(query="Cantonese TTS Hong Kong 2026 release")
web_search(query="whisper.cpp yue language code", max_results=10)
```

## Red Lines

- Web search costs MiniMax API quota downstream (the
  search results get summarized via the LLM). Don't search
  for things you can answer from memory.
- Some sites block DuckDuckGo's user-agent. The tool
  retries once with a different UA; if both fail, surface
  the failure to the user rather than trying alternative
  engines (which we don't ship).

## Recovery

- "rate limited" → back off 30s. Don't retry the same
  query immediately.
- "no results" → broaden the query. Don't retry the
  exact same phrasing.
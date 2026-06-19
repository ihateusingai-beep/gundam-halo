"""web_fetch tool — fetch a URL via httpx, return text content.

Used by the agent for tasks like "fetch today's weather", "summarize
this blog post", "check this API status", etc. The agent can chain
this with `WeatherTool` (which uses wttr.in under the hood) or use
it standalone for arbitrary URLs.

Security:
- Only HTTP(S) schemes allowed
- Max response size capped to 64 KB (prevents runaway downloads)
- Timeout enforced
- A simple User-Agent header is set (some sites 403 default UAs)
- We do NOT block private/internal IP ranges — for v1 we assume
  the agent is trusted (single-user, local). Future hardening can
  add SSRF protection (RFC1918 + link-local blocking).
"""
from __future__ import annotations

import logging
from typing import Any, Dict

import httpx

from app.tools._stubs import BaseTool
from app.core.registry import register_tool

logger = logging.getLogger(__name__)

# Cap response body to 64 KB. Anything bigger is truncated at the
# boundary; the LLM gets a hint that the content was clipped.
MAX_BYTES = 64 * 1024
DEFAULT_TIMEOUT_S = 15.0
USER_AGENT = "GundamHalo/0.1 (+https://github.com/ihateusingai-beep/gundam-halo)"


@register_tool("web_fetch")
class WebFetchTool(BaseTool):
    """Fetch a URL and return its body (truncated to MAX_BYTES)."""

    name = "web_fetch"
    description = (
        "Fetch a URL and return its body as text. Use this for HTTP(S) requests "
        "when the agent needs to retrieve web data (weather, articles, APIs, etc). "
        "The body is truncated to 64 KB. JSON responses are returned as-is; HTML "
        "is returned as raw text (no DOM parsing). For weather specifically, "
        "prefer the `weather` tool which parses structured data."
    )
    parameters: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "HTTP(S) URL to fetch. Must start with http:// or https://.",
            },
            "max_chars": {
                "type": "integer",
                "description": (
                    "Override the truncation limit. Default 65536 (64 KB). "
                    "Min 256, max 262144 (256 KB)."
                ),
                "minimum": 256,
                "maximum": 262144,
            },
            "timeout_s": {
                "type": "number",
                "description": "Request timeout in seconds. Default 15, max 60.",
                "minimum": 1,
                "maximum": 60,
            },
        },
        "required": ["url"],
    }

    async def run(
        self,
        url: str,
        max_chars: int = MAX_BYTES,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        **_: Any,
    ) -> str:
        if not isinstance(url, str) or not url:
            return "Error: 'url' is required"
        if not (url.startswith("http://") or url.startswith("https://")):
            return f"Error: only http(s) URLs are supported, got: {url!r}"

        # Clamp the max_chars
        max_chars = max(256, min(int(max_chars or MAX_BYTES), 262144))
        timeout_s = max(1.0, min(float(timeout_s or DEFAULT_TIMEOUT_S), 60.0))

        try:
            async with httpx.AsyncClient(
                timeout=timeout_s,
                follow_redirects=True,
                headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                raw = resp.content[:max_chars]
                text = raw.decode("utf-8", errors="replace")

                clipped = len(resp.content) > max_chars
                if clipped:
                    text += (
                        f"\n\n[truncated at {max_chars} bytes; "
                        f"total response was {len(resp.content)} bytes]"
                    )

                ctype = resp.headers.get("content-type", "?")
                return (
                    f"HTTP {resp.status_code} · {resp.headers.get('content-length', '?')} bytes · {ctype}\n"
                    f"{text}"
                )
        except httpx.TimeoutException as e:
            return f"Error: timeout after {timeout_s}s — {e}"
        except httpx.HTTPStatusError as e:
            return f"Error: HTTP {e.response.status_code} {e.response.reason_phrase}"
        except httpx.RequestError as e:
            return f"Error: request failed — {e.__class__.__name__}: {e}"
        except Exception as e:  # noqa: BLE001
            logger.exception("web_fetch failed")
            return f"Error: unexpected failure — {e}"


__all__ = ["WebFetchTool"]

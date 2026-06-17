"""youtube_summarize tool — fetch + summarize a YouTube video.

Sprint 27 (per `docs/FEATURE-SPEC-SPRINT27.md` §4.2 Track 27.2).

Fetches the transcript of a YouTube video via the
optional `youtube-transcript-api` library and returns
it as a TTS-friendly prose block. The agent's
NativeReAct loop will call the LLM in the next turn
to summarise the transcript into a final answer.

Optional dep: `youtube-transcript-api>=0.6`. If the
dep is not installed, the tool falls back to YouTube's
public `oembed` API to get the video's title and
author (so the user gets a useful partial answer)
and returns a clear message asking them to install
the dep for full transcript support.

The Mark-XL `youtube_video.py` (the source of this
tool's design) had a `tkinter` URL prompt — we
drop that. `url` is a required parameter; the LLM
extracts the URL from the user's voice/chat input.

Voice path: returns prose, no markdown fences. The
LLM summarisation step in the agent loop is
responsible for producing the final TTS-friendly
summary; the tool itself just fetches the transcript.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

import httpx

from app.tools._stubs import BaseTool

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_S = 15.0
DEFAULT_MAX_TRANSCRIPT_CHARS = 12_000  # match Mark-XL
DEFAULT_SUMMARY_MAX_CHARS = 800
OEMBED_URL = "https://www.youtube.com/oembed"
USER_AGENT = "GundamHalo/0.1 (+https://github.com/ihateusingai-beep/gundam-halo)"


def _extract_video_id(url: str) -> Optional[str]:
    """Extract the YouTube video ID from various URL formats.

    Supports:
      - https://www.youtube.com/watch?v=ID
      - https://youtu.be/ID
      - https://www.youtube.com/shorts/ID
      - https://www.youtube.com/embed/ID
    Returns None if no valid ID is found.
    """
    if not url:
        return None
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    path = parsed.path or ""

    # youtu.be/ID
    if "youtu.be" in host:
        vid = path.lstrip("/").split("/")[0]
        return vid if vid else None

    # youtube.com watch?v=ID
    if "youtube.com" in host or "youtube-nocookie.com" in host:
        if path == "/watch":
            qs = parse_qs(parsed.query)
            vids = qs.get("v", [])
            return vids[0] if vids else None
        # /shorts/ID or /embed/ID
        parts = [p for p in path.split("/") if p]
        if len(parts) >= 2 and parts[0] in ("shorts", "embed", "v"):
            return parts[1]

    return None


def _fetch_transcript(video_id: str) -> List[Dict[str, Any]]:
    """Fetch the transcript via youtube-transcript-api.

    Returns a list of `{text, start, duration}` dicts.
    Raises ImportError if the dep is not installed.
    Raises Exception on any other failure (the caller
    wraps the result in a clear error string).
    """
    from youtube_transcript_api import YouTubeTranscriptApi  # type: ignore

    return YouTubeTranscriptApi.get_transcript(video_id)


def _format_transcript_for_llm(
    transcript: List[Dict[str, Any]],
    max_chars: int,
) -> str:
    """Format the transcript as a single prose block,
    capped at `max_chars`. We concatenate all snippets
    with single spaces (no timestamps, no line breaks —
    the LLM doesn't need them and they hurt the
    TTS-friendly output).
    """
    out: List[str] = []
    total = 0
    for entry in transcript:
        text = entry.get("text", "").strip()
        if not text:
            continue
        if total + len(text) > max_chars:
            remaining = max_chars - total
            if remaining > 0:
                out.append(text[:remaining] + "...")
            break
        out.append(text)
        total += len(text) + 1  # +1 for the space
    return " ".join(out)


async def _fetch_oembed_metadata(url: str) -> Optional[Dict[str, str]]:
    """Fallback: fetch YouTube's oEmbed API for the
    video's title and author. Useful when the user
    hasn't installed `youtube-transcript-api` and the
    agent needs at least some metadata to respond.
    """
    try:
        async with httpx.AsyncClient(
            timeout=DEFAULT_TIMEOUT_S,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        ) as client:
            resp = await client.get(OEMBED_URL, params={"url": url, "format": "json"})
            resp.raise_for_status()
            return resp.json()
    except Exception as e:  # noqa: BLE001
        logger.warning("oEmbed fallback failed: %s", e)
        return None


class YouTubeSummarizeError(RuntimeError):
    """Raised on YouTube errors (no transcript, video
    private, network failure, etc.)."""


class YouTubeSummarizeTool(BaseTool):
    """Fetch + summarize a YouTube video's transcript.

    Returns the raw transcript (capped at
    `summary_max_chars`) as a TTS-friendly prose block.
    The agent's NativeReAct loop will call the LLM in
    the next turn to summarise the transcript.
    """

    name = "youtube_summarize"
    description = (
        "Fetch the transcript of a YouTube video and return "
        "it as a prose block. The agent's LLM call will "
        "summarise the transcript in the next turn. Supports "
        "youtube.com/watch, youtu.be, /shorts, and /embed URLs. "
        "If the transcript is unavailable (video has no "
        "captions, is private, or the optional "
        "youtube-transcript-api dep is not installed), the "
        "tool falls back to YouTube's oEmbed API to return "
        "the video's title and author."
    )
    parameters: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": (
                    "YouTube video URL. Examples: "
                    "'https://www.youtube.com/watch?v=dQw4w9WgXcQ', "
                    "'https://youtu.be/dQw4w9WgXcQ', "
                    "'https://www.youtube.com/shorts/abc123'."
                ),
            },
            "max_transcript_chars": {
                "type": "integer",
                "description": (
                    "Cap on transcript length before LLM "
                    "summarisation. Default 12000 (matches "
                    "Mark-XL)."
                ),
            },
        },
        "required": ["url"],
    }

    async def run(
        self,
        url: str,
        max_transcript_chars: int = DEFAULT_MAX_TRANSCRIPT_CHARS,
        **_: Any,
    ) -> str:
        if not isinstance(url, str) or not url.strip():
            return "Error: 'url' is required and must be a non-empty string"
        url = url.strip()

        # Validate URL + extract video ID
        video_id = _extract_video_id(url)
        if not video_id:
            return f"Error: could not extract a YouTube video ID from {url!r}"

        # Try the full transcript path first. If the dep
        # is missing (ImportError) or the transcript is
        # disabled, fall back to oEmbed metadata so the
        # user gets *some* useful response.
        try:
            transcript = _fetch_transcript(video_id)
        except ImportError:
            return await self._fallback_oembed(
                url,
                reason=(
                    "youtube-transcript-api is not installed. "
                    "Install with: uv add youtube-transcript-api"
                ),
            )
        except Exception as e:  # noqa: BLE001
            # Most common: TranscriptsDisabled, VideoUnavailable,
            # NoTranscriptFound, or any network/parse error.
            error_name = type(e).__name__
            return await self._fallback_oembed(
                url,
                reason=f"transcript fetch failed ({error_name}: {e})",
            )

        # Format + return
        prose = _format_transcript_for_llm(transcript, max_transcript_chars)
        if not prose.strip():
            return await self._fallback_oembed(
                url,
                reason="transcript is empty",
            )
        header = f"Transcript of YouTube video {video_id} ({len(transcript)} segments):"
        return f"{header}\n\n{prose}"

    async def _fallback_oembed(self, url: str, reason: str) -> str:
        """When the transcript path fails, fall back to
        oEmbed for basic metadata so the agent can still
        respond to the user (e.g. "I can see this is a video
        titled X by Y, but I can't read the transcript
        because Z")."""
        meta = await _fetch_oembed_metadata(url)
        if meta:
            title = meta.get("title", "(unknown)")
            author = meta.get("author_name", "(unknown)")
            return (
                f"Could not fetch the transcript for {url!r} — {reason}. "
                f"Video metadata: title={title!r}, author={author!r}. "
                f"The agent should tell the user about this limitation."
            )
        # oEmbed also failed (network down, video deleted, etc.)
        return (
            f"Error: could not fetch transcript for {url!r} — {reason}. "
            f"Could not fetch oEmbed metadata either. The video may be "
            f"private, deleted, or the URL is incorrect."
        )


__all__ = ["YouTubeSummarizeTool", "YouTubeSummarizeError"]

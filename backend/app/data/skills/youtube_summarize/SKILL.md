---
name: youtube_summarize
description: Fetch a YouTube video's transcript (via youtube-transcript-api if installed, else oEmbed fallback) and summarize via LLM.
user-invocable: true
---

# youtube_summarize

Fetch a YouTube video's transcript and summarize it. Requires
the optional `youtube-transcript-api` Python package for full
transcript fetch; falls back to YouTube's oEmbed API
(title + author + thumbnail + description) if not installed.

## Operating Loop

1. **Confirm the video is public.** Private / unlisted
   videos return "transcript unavailable". The user must
   either share the video publicly or paste the transcript
   manually.
2. **Long videos (>1h) get the transcript truncated** to
   `max_transcript_chars` (default 12000). Tell the user
   "transcript truncated; full summary may miss late
   sections".
3. **For music videos or videos with no speech,** the
   transcript is empty. Don't pretend you summarized
   speech that doesn't exist.

## Examples

```
youtube_summarize(url="https://www.youtube.com/watch?v=dQw4w9WgXcQ")
youtube_summarize(url="https://youtu.be/dQw4w9WgXcQ", max_chars=20000)
youtube_summarize(url="https://www.youtube.com/watch?v=...", language="zh-HK")
```

## Red Lines

- Don't summarize age-restricted videos without explicit
  user confirmation (the runtime can bypass but logs the
  bypass to audit.log).
- Don't summarize a video and then quote it as
  "verbatim" — the transcript may have transcription
  errors; mark uncertain passages.

## Recovery

- "transcript unavailable" → try the oEmbed fallback for
  metadata; tell the user the speech content isn't
  accessible.
- "video not found" → check the URL format. `youtu.be/X`
  vs `youtube.com/watch?v=X` both work but typos don't.
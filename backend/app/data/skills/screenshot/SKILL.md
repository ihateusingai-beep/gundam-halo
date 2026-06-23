---
name: screenshot
description: Take a screenshot of the user's screen (or a specific app/window). Returns base64 PNG.
user-invocable: true
---

# screenshot

Capture the screen as PNG. Returns base64 + dimensions.
Useful for "what's on screen now?" questions, vision-pipeline
inputs, and screenshot-to-text via OCR (post-process
yourself via `shell_exec`).

## Operating Loop

1. **Default to the primary display.** Use `display=N` to
   target the Nth display (0-indexed); useful when the
   user has multiple monitors.
2. **For window-specific captures, pass `window_name`.**
   The runtime uses `screencapture -l <window-id>` which
   avoids capturing the whole screen.
3. **For Vision / OCR, post-process.** The tool returns
   the raw PNG; if you need text, pipe through
   `shell_exec tesseract <file> -` (requires tesseract to
   be installed via `brew install tesseract`).

## Examples

```
screenshot()                                    → primary display
screenshot(display=1)                           → secondary display
screenshot(window_name="Notes")
screenshot(path="~/Downloads/screen.png")       → save to file instead of returning
```

## Red Lines

- macOS requires Screen Recording permission. The user
  must grant it once via System Settings → Privacy &
  Security → Screen Recording. Without this grant, every
  screenshot returns a black PNG (silent failure).
  Surface this to the user if the PNG is uniformly black.
- Don't loop screenshot calls in a tight cycle. Each
  call is ~200-500ms; rate-limit to once per 2s when
  watching for a UI change.

## Recovery

- "black PNG" → Screen Recording permission not granted.
  Tell the user to open System Settings and enable it.
- "Permission denied" → same, plus check the host app is
  the one granted permission (Tauri shell, not the
  uvicorn backend).
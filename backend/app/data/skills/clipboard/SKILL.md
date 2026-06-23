---
name: clipboard
description: Read from or write to the macOS pasteboard. Useful for cross-app text transfer; not for binary blobs.
user-invocable: true
---

# clipboard

Read or write the macOS pasteboard via `pbcopy` / `pbpaste`.
Text only (UTF-8). For binary content (images, files), use
`open_app` to launch the target app and paste via a11y.

## Operating Loop

1. **Read first, write second.** If the user wants to move
   clipboard contents to a file, `read` then `file_write`.
   Don't blindly `write` new content.
2. **Pasteboard may be empty.** Handle empty reads as
   "no clipboard content" not as an error.
3. **For large pastes (>10k chars),** the tool returns the
   text truncated. Use `file_write` for big content.

## Examples

```
clipboard(action="read")                              → "Last copied text"
clipboard(action="write", text="Hello from Unicorn")
```

## Red Lines

- Don't write credentials / API keys to the clipboard.
  The pasteboard is visible to any focused app; the user
  can paste into the wrong window.
- Don't read the clipboard when the user is on a password
  field. The runtime blocks this; if the user really needs
  to extract a copied password, ask them to type it
  explicitly.

## Recovery

- "pbcopy failed" → likely the sandbox blocked pasteboard
  write. Tell the user to grant "Allow Clipboard" to the
  host terminal in System Settings → Privacy & Security.
---
name: file_read
description: Read the contents of a text file from disk. Use when you need to inspect a file's contents.
user-invocable: true
---

# file_read

Read a text file's contents. Policy-gated by
`MacControlConfig.file_read_paths` (default: `~/Documents`,
`~/Downloads`, `~/workspace`, `/tmp`). Files outside these paths
are blocked with an `EPERM` error before any I/O happens — the
tool does NOT attempt to read and fail with EACCES; it refuses
upfront.

## Operating Loop

1. **Check the path is in scope.** If the user asks to read
   `~/Library/Application Support/...` or `/etc/passwd`, STOP.
   That's outside `file_read_paths`. Don't pretend the read
   failed — explain to the user that the path is outside the
   read scope, and ask them to either move the file into scope
   or extend the policy in `~/.gundam-halo/config.toml` and
   restart.
2. **Use `cat` via shell if you need line numbers or byte
   offsets** — `file_read` returns the whole file as one string.
   For a 5000-line file, prefer `shell_exec` with
   `sed -n '1,50p'` or `head -n 50`.
3. **Binary files return an error.** Don't retry. Use
   `screenshot` or `web_fetch` for binary content.

## Examples

```
file_read(path="~/workspace/gundam-halo/README.md")
file_read(path="/tmp/build.log")
file_read(path="~/Documents/notes/2026-06-13.md")
```

## Red Lines

- `~/.gundam-halo/.env` is OUT of scope. The config loader
  blocks it via the same `file_read_paths` allowlist. If you
  need to verify an API key is set, use `os.environ.get()`
  via `shell_exec` (it's allowed because shell env is a
  different scope from file content).
- Don't read `~/.gundam-halo/audit.log` and dump it to a
  channel. Audit log entries may contain file paths / user
  actions that are sensitive in a group chat.
- For files >1 MB, the tool truncates output to 4096 chars +
  adds a `_... truncated; X bytes total, N lines _` suffix.
  If you need more, page through with `shell_exec sed`.

## Recovery

- "EPERM: outside file_read_paths" → tell the user the path
  is out of scope, don't retry with a different path.
- "UnicodeDecodeError" → the file is likely binary; switch
  to `shell_exec file <path>` for the first 64 bytes.
---
name: file_write
description: Write text to a file on disk. Policy-gated by MacControlConfig.file_write_paths and security audit log.
user-invocable: true
---

# file_write

Write text to a file. Policy-gated by
`MacControlConfig.file_write_paths` (default: `~/workspace`,
`~/.gundam-halo/projects`). Every write is appended to
`~/.gundam-halo/logs/audit.log` with the path, the first
100 chars of content, and the agent session id.

## Operating Loop

1. **Confirm the path is in `file_write_paths`.** Default
   is `~/workspace` and `~/.gundam-halo/projects`. Writing to
   `~/Documents` is BLOCKED by default — that's read-only
   scope.
2. **For overwrites, prefer `trash` first.** The `trash`
   MCP tool moves the old file to OS Trash (recoverable)
   before writing. `file_write` does NOT auto-trash; if
   the file exists and you don't want to lose it, use
   `shell_exec mv <path> ~/.local/share/Trash/ 2>/dev/null`
   first.
3. **For new files in `~/workspace/...`, this is the
   primary write tool.** Don't use `shell_exec echo >
   path` — it bypasses the audit log.

## Examples

```
file_write(path="~/workspace/gundam-halo/notes.md", content="# Today\n\n- Sprint 36 Tier 1 done")
file_write(path="~/.gundam-halo/projects/test/output.json", content="{\"ok\": true}")
```

## Red Lines

- The audit log entry is visible in
  `~/.gundam-halo/logs/audit.log` and surfaced in the
  cockpit's ActivityTicker. **Don't write API keys,
  passwords, or session tokens to a file under
  `~/workspace/`** — the audit log will display the first
  100 chars. If the user needs to write a secret, route
  through `shell_exec` with `chmod 600` and put it in
  `~/.gundam-halo/.env` instead.
- Don't write to `~/.gundam-halo/config.toml` directly via
  `file_write`. The TOML parser would lose comments and
  structure. Use the `/api/setup` PATCH endpoint (which
  goes through `app.core.toml_doc`) or edit manually with
  `tomlkit`.

## Recovery

- "EPERM: outside file_write_paths" → tell the user the
  path is out of scope, suggest they either move the file
  into `~/workspace/` or extend the policy.
- "PermissionError" → likely a read-only mount (e.g. a
  DMG). Don't retry; surface to user.
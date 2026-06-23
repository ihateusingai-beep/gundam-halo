---
name: shell_exec
description: Run a shell command on the user's Mac. Policy-gated by MacControlConfig.shell_allowlist; high-risk commands require explicit user confirmation.
user-invocable: true
---

# shell_exec

Run a shell command via `/bin/bash -c`. Policy-gated by
`MacControlConfig.shell_allowlist` (default: `git, ls, cat,
head, tail, grep, rg, find, fd, pwd, cd, echo, date, open`).

The tool checks the FIRST token of the command against the
allowlist. Compound commands (`a && b`, `a | b`, `$(...)`) are
parsed: if ANY token in the chain is outside the allowlist,
the whole command is blocked.

## Operating Loop

1. **Always state the command before running it.** Don't
   silently execute. The agent's message should show the
   command, then the result. ("I'll run `ls -la ~/workspace`
   to see the project structure. Result: ...")
2. **Prefer specific tools over `shell_exec` when possible.**
   `file_read` is safer than `cat` (policy-gated + audit-log
   free for the read side). `screenshot` is safer than
   `screencapture` (uses a11y, not screen-recording permission).
3. **Use `open` for launching apps** (the allowlist already
   includes it). Don't `nohup` or `&`-background.

## Examples

```
shell_exec(command="ls -la ~/workspace")
shell_exec(command="git -C ~/workspace/gundam-halo status")
shell_exec(command="rg -n 'def start_record' backend/app/api")
shell_exec(command="find ~/Downloads -name '*.pdf' -mtime -7")
```

## Red Lines

- **`rm -rf` is BLOCKED unless `rm` is in the allowlist.**
  Even with `rm` allowed, the agent should prefer `trash`
  MCP tool (recoverable). If `rm` is in the allowlist AND the
  user explicitly says "delete it", `rm <path>` is OK; `rm -rf`
  on a directory requires user confirmation even within scope.
- **Don't pipe to `sh` / `bash` / `eval`.** `curl ... | sh`
  blocks because `sh` isn't in the allowlist. If you need
  to install something, prefer the system's package manager
  (homebrew, etc.) via direct invocation, not a piped script.
- **`sudo` blocks unless it's the first token AND in the
  allowlist.** Default allowlist does NOT include `sudo`.
  Adding `sudo` to the allowlist is a security-red-flag
  decision; don't recommend it.
- **Don't `chmod 777` or `chmod -R 777`.** Even when
  `chmod` is in the allowlist, `chmod 777` should fail. The
  tool's `_check_chmod_777` guard catches it.

## High-risk confirmation

When the runtime detects a destructive pattern (`rm -rf`,
`mv ... ~/.Trash` on a non-empty dir, mass `chmod`, etc.),
it sends a `mac_op_blocked` event to the cockpit. The user
must approve via the dashboard before the command runs.
The tool's return value will be `"BLOCKED: <reason>"` rather
than the actual output. Do not retry silently — surface the
block to the user and ask for explicit confirmation.

## Recovery

- "first token <X> not in shell_allowlist" → the command
  starts with something outside the allowlist. Pick a
  sibling tool or split the command.
- "compound command blocked" → one of the chained tokens
  is outside the allowlist. Rewrite the command.
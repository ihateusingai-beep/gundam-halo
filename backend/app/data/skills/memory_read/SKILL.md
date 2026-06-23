---
name: memory_read
description: Read a value from the agent's persistent memory store, keyed by user + key. Returns the stored value or null if not found.
user-invocable: true
---

# memory_read

Read from `~/.gundam-halo/memory/<user_key>/<key>.md`. Used
to recall facts the agent previously wrote via
`memory_write`. The runtime pre-pends up to 25 most-recent
keys to the system prompt on every turn (see
`build_system_prompt`); use `memory_read` for full content
fetch beyond the recall.

## Operating Loop

1. **Default: check the system prompt first.** If the
   `## What you remember about this user` block lists the
   key, the value is already in context. Don't re-read.
2. **For lists / large values,** `memory_read` returns the
   full file content (markdown). No truncation.
3. **For cross-user queries (the user is asking what they
   said last week),** `memory_read` is the right tool;
   `memory_write` is for adding new entries.

## Examples

```
memory_read(user_key="kencheng", key="gundam-ntd-theme-2026-06-13")
memory_read(user_key="kencheng", key="favorite-vim-mappings")
```

## Red Lines

- **MEMORY.md (the long-term distillation) is NEVER loaded
  by this tool in shared contexts.** The runtime enforces
  this for system-prompt recall; `memory_read` follows
  the same rule — if you ask for a key that's actually
  `MEMORY.md`, the tool refuses.
- Don't mass-read all keys to "see what you have". Use
  the recall list in the system prompt first; only
  fetch specific keys.

## Recovery

- "key not found" → the agent hasn't written that key.
  Either ask the user, or use `memory_write` to start
  tracking it.
---
name: memory_write
description: Write or update a value in the agent's persistent memory store, keyed by user + key. Markdown content; lasts across sessions.
user-invocable: true
---

# memory_write

Write to `~/.gundam-halo/memory/<user_key>/<key>.md`. The
value is markdown content (1-3 sentences typically; the
tool accepts longer). Persists across sessions and is
included in the system prompt on subsequent turns.

## Operating Loop

1. **Pick a clear key.** Use lowercase-kebab-case +
   date stamp for time-bound facts
   (`gundam-ntd-theme-2026-06-13`,
   `sprint-30-track-a-yolo-shipped`). Use bare names for
   standing preferences (`favorite-vim-mappings`,
   `preferred-tts-voice`).
2. **Keep values short.** 1-3 sentences. The recall
   system caps at 25 entries per turn; each entry takes
   ~80 tokens. Don't dump a 500-word essay into one key.
3. **Always confirm before writing.** Memory writes are
   sticky; the user should know what's being saved.

## Examples

```
memory_write(user_key="kencheng", key="sprint-36-tier1-shipped", value="Workspace markdown pattern (OpenClaw-inspired) loaded into system prompt. 7 starter files in app/data/workspace/.")
memory_write(user_key="kencheng", key="preferred-tts-voice", value="zh-HK-HiuMaanNeural; raise rate to +5% for serious replies, -10% for jokes.")
```

## Red Lines

- **Don't store secrets.** API keys, tokens, passwords,
  session IDs — none of these go in memory. Use
  `~/.gundam-halo/.env` (chmod 600) for credentials.
- **Don't store PII about third parties** without the
  third party's consent. The recall block surfaces in
  every turn; sensitive names leak.
- **Don't overwrite a key without warning the user.**
  The runtime logs the change to audit.log but doesn't
  notify the user. Surface "I'm updating your existing
  <key>" before writing.

## Recovery

- "key already exists" → use the existing key name; the
  tool will append rather than overwrite if you pass the
  same `key` and use a date-suffixed variant. Don't
  silently overwrite.
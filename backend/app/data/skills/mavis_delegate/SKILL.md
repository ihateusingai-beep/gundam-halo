---
name: mavis_delegate
description: Delegate a sub-task to a child Mavis session with isolated context. Useful for parallel research or "investigate X then come back" tasks.
user-invocable: true
---

# mavis_delegate

Delegate a sub-task to a child Mavis (the same Mavis session
you're running in) with a fresh context. The child runs the
task, returns a structured summary, and exits. Use this when:

- The user wants parallel research ("compare X and Y")
- A sub-task would otherwise pollute the main session
  context (e.g. "read all 50 pages of this PDF")
- You want a clean second opinion ("verify your own work")

## Operating Loop

1. **Frame the task as a self-contained question.** The
   child session doesn't see your context. Be explicit:
   "Find the official MiniMax M3 cluster pricing as of
   2026-06. Return: price per million tokens, monthly
   minimum, signup URL. Don't make up numbers."
2. **Choose the right model.** Default is the parent's
   model. Use a smaller model (e.g. `MiniMax-M2` instead
   of `Mavis-Coder`) for cheap research; a larger model
   for code review.
3. **Set a hard deadline.** Child sessions that hang
   are a known failure mode. Default timeout is 5 min;
   override with `timeout_s` for long tasks.
4. **Don't delegate user-facing tasks.** "Send a message
   to Ken" — that's `send_message`, not a child session.
   The user can see `send_message`; they can't see the
   child's reasoning.

## Examples

```
mavis_delegate(task="Compare the 3 free-tier LLM APIs in 2026-06 (MiniMax / Anthropic / OpenAI). Return: $/M tokens, monthly free credits, rate limits.")
mavis_delegate(task="Read ~/.gundam-halo/audit.log (last 1000 lines) and report any mac_op_blocked events. Format as a table.", model="minimax/MiniMax-M2", timeout_s=120)
mavis_delegate(task="Verify the test_voice_config_asr.py tests cover the asr_backend=yuesub path. If not, suggest what to add.")
```

## Red Lines

- **Don't delegate "send X to Telegram" or any external
  action.** The child session can do it, but the user
  didn't approve the child — only you. Stick to read-only
  / research tasks.
- **Don't loop `mavis_delegate`.** Each child burns API
  quota + time. For "investigate 5 things", do them
  sequentially in the same child, not 5 separate children.
- **Don't delegate to a larger model by default.** It
  costs 10x the quota; only justify for tasks that need
  it.

## Recovery

- "child session timeout" → the child took too long.
  Either retry with a longer timeout or split the task
  into smaller pieces.
- "child session error: <X>" → surface the X to the user;
  the child failed the same way the parent would have.
# M9-D — Voice quality: strip reasoning + handle markdown code fences in TTS

> **Milestone**: M9 (voice layer)
> **Priority**: medium
> **Status**: open
> **Discovered during**: M9-C live run, 2026-06-10

---

## Symptom

Two distinct content-quality issues in the voice output, both observed
in the M9-C live transcript (`/tmp/m9c_1781103856/transcript.txt`,
TTS MP3 `/tmp/m9c_1781103856/tts_output.mp3`):

1. **LLM reasoning leaks into spoken reply.** The M2 model wraps its
   internal planning in `<think>…</think>`. The current pipeline
   forwards the entire assistant message — reasoning + final answer —
   to `agent.message` → TTS. The user *hears* the model think out loud
   in English, then switches to the Cantonese reply.

   Observed:

   ```
   Agent text: '<think>\nThe user asked for the first line of the
                README.md file. The first line is:\n\n# Gundam Halo
                — Backend\n\nI should reply in Cantonese as requested.
                \n</think>\n\nREADME.md 嘅第一行係：\n\n```\n# Gundam
                Halo — Backend\n```'
   ```

2. **Markdown code fences break the TTS sentence-segmenter.** After
   stripping the `<think>` block, the reply still contains `` ``` ``
   fences around the README line. The TTS engine sees the opening
   fence as an empty sentence, throws `ERROR: No audio was received`,
   then attempts the rest. Net effect: fragmented audio, an error
   warning per fenced block in the backend log, and the user hears a
   glitched TTS.

   ```
   ERROR  app.voice.halo_responder  TTS stream failed for '```':
         No audio was received. Please verify that your parameters
         are correct.
   ```

## Impact

- **M9-C exit criteria** (`used_tool_content=True`) still passes —
  the README line *does* make it into the spoken reply (whisper
  re-transcription confirms it). So this is **not a blocker for
  M9-C sign-off**, but it is a real voice quality regression the user
  will notice every time the LLM produces a structured reply.
- Affects all voice paths that surface LLM output (text + voice
  inputs), since both feed the same `_emit_agent_response` chain.
- Amplified by tools that return structured content (file_read on
  code/markdown, shell_exec, web_fetch) — the agent tends to fence
  these in their reply.

## Repro

```bash
cd ~/workspace/working/gundam-halo/backend
set -a; source ~/.gundam-halo/.env; set +a
.venv/bin/python scripts/m9c_voice_tools.py
# In /tmp/m9c_<ts>/transcript.txt, search for "<think>" and for
# "TTS stream failed". Both present.
```

## Proposed fix

Two cleanups, both in `app/voice/halo_responder.py` (and a small
touch in `app/agents/native_react.py` / system prompt).

### 1. Strip reasoning blocks before TTS

In `HaloResponder.respond_stream` (or a thin pre-processor called
from `_emit_agent_response` in `app/api/voice_ws.py`), drop these
patterns from the agent's text *before* sentence-splitting and TTS:

- `<think>…</think>` (greedy, multiline)
- `<tool_call>…</tool_call>` (in case the model ever uses Anthropic-
  style tool calls in its visible text; current OpenAI path emits
  tool_calls as a separate field, not in content, so this is
  defensive)
- A leading "Reasoning:" / "Reasoning steps:" prefix + body, in case
  the model uses that style

Apply the strip in the **server**, not the frontend — the frontend
may want to *display* the reasoning (debug panel), the server should
*not speak* it.

### 2. Markdown-aware sentence segmenter

Replace the current naive `split(r'(?<=[.!?])\s+')` heuristic in
`HaloResponder` with a small `markdown-it-py` based pass:

- For each top-level block:
  - If fenced (` ``` ` … ` ``` `), pass it through as a single
    utterance with the fence lines removed and code contents
    described as "code block" (or read the literal contents if
    short — design decision).
  - If a heading (`# …`), speak as "section: …" then continue.
  - If a list, speak each item on its own utterance.
  - Otherwise (paragraph), split on sentence boundaries as today.

If pulling in `markdown-it-py` is too heavy for a hot path, a
~50-line regex pass over fence boundaries + sentence split is
enough.

### 3. System prompt guard (defense in depth)

In `app/agents/system_prompt.py`, add to the agent's system prompt:

> When speaking (the agent.message field is sent to TTS), do NOT
> include `<think>…</think>` blocks, and avoid markdown code fences
> in the spoken text — describe what the code does in prose instead.

This reduces the *frequency* of the issue but does not replace
the server-side strip — small models, retries, and prompt drift
will still leak occasionally.

## Test plan

- Unit: `HaloResponder.respond_stream("<think>…</think>```…```hello")`
  yields clean utterances, no `<think>` text, no empty-string errors.
- Unit: `strip_reasoning()` on a known fixture with mixed content.
- Live: re-run `scripts/m9c_voice_tools.py`, then:
  - `grep -E "<think>|TTS stream failed" /tmp/m9c_<ts>/transcript.txt`
    returns nothing.
  - Re-transcribe the TTS MP3 with Whisper; the spoken text should
    flow as one or two clean Cantonese sentences, not include
    "think" / "user asked for" English fragments.
- Manual: drive the frontend text input ("幫我讀 backend README
  嘅第一行"), confirm the cockpit badge returns to `Ready` (regression
  test for the v0.1.1 `voice.turn_ended` fix) **and** the spoken
  reply has no reasoning leak.

## Out of scope (for M9-D)

- Whisper base → medium upgrade or Cantonese fine-tune (M10).
- Live2D expression mapping per content type (separate ticket).
- Telemetry on TTS error rate per session.

## Acceptance

- [x] Server-side reasoning strip in `HaloResponder` and
      `voice_ws._emit_agent_response`.
- [x] Markdown-aware rewrite that handles fenced code blocks
      without `No audio was received` errors.
- [x] System prompt guard.
- [x] Unit tests for both (19 new tests, 102/102 voice suite pass).
- [x] M9-C live re-run passes with the strict transcript grep
      (no `<think>` in client-visible frames, no `TTS stream
      failed` in server log).
- [x] M9-C re-run results: TTS chunks 201 → 68, TTS latency
      13.7s → 6.5s, total wall 20.2s → 12.9s, used_tool_content
      still `True`. The agent's spoken reply (re-transcribed
      via whisper) still contains the README first line.
- [x] Cockpit regression — voice badge returns to "Ready — hold
      to talk" after a text-bypass turn, captured in
      `~/.mavis/tmp/gundam-halo-screenshots/v011-01-baseline-ready.png`.

**Closed in v0.1.2** (`docs/CHANGELOG.md`). Commits:
- `3ce641a` — `fix(voice): M9-D strip LLM reasoning + rewrite markdown fences for TTS`
- `895bb2a` — `chore(frontend): pin dev server to 5173 with --strictPort`

## Commits (planned)

- `<sha>` `feat(voice): strip LLM reasoning from TTS input`
- `<sha>` `feat(voice): markdown-aware sentence segmenter for TTS`
- `<sha>` `chore(agent): system prompt guard against reasoning leak`
- `<sha>` `test(voice): reasoning-strip + markdown-segmenter unit tests`

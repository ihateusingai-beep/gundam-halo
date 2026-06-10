# Changelog

All notable changes to Gundam Halo are documented here. The format is
based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

---

## [0.1.2] — 2026-06-10

Closes M9-D (voice quality follow-up from the v0.1.1 M9-C live run).

### Added
- **`backend/app/voice/tts/voice_sanitizer.py`** — server-side
  sanitiser that runs between the agent callback and the
  TTS pipeline.
  - `strip_reasoning(text)` removes `<think>…</think>` and
    `<tool_call>…</tool_call>` blocks, plus leading
    "Reasoning: …" / "推理: …" prose. Case-insensitive,
    handles both ASCII and full-width `:`.
  - `sanitize_for_tts(text)` adds a markdown-fence rewrite on
    top: triple-backtick and tilde code blocks become a single
    `[Code: …]` summary (capped at 200 chars, internal
    whitespace collapsed). Inline backticks are untouched.
- **`backend/tests/voice/test_voice_sanitizer.py`** — 19 unit
  tests covering both functions, the exact M9-C regression
  fixture, idempotence, and emotion-tag preservation.

### Changed
- **`HaloResponder.respond` and `respond_stream`** now call
  `sanitize_for_tts(agent_text)` before `parse_emotion`. The
  responder's TTS input never contains leaked reasoning or
  bare fence lines again.
- **`voice_ws._emit_agent_response`** also calls
  `sanitize_for_tts` before `parse_emotion` so the
  `agent.message` WebSocket frame is clean for the cockpit
  display too (the responder was not the only consumer).
- **`REACT_SYSTEM_PROMPT`** in `app/agents/native_react.py`
  carries a "Voice output rules" section: the model is told
  to omit `<think>` blocks from its visible reply and to
  prefer prose over fenced code blocks when speaking. The
  server-side strip is the safety net.
- **`frontend/package.json` `dev` script** now passes
  `--strictPort`. Vite exits non-zero when port 5173 is taken
  instead of silently falling back to a different port.
  Added `dev:flex` alias for the old loose behaviour.

### Fixed
- `<think>` blocks no longer leak into TTS audio (the user
  no longer hears the model reason out loud before the
  reply).
- Markdown code fences no longer fragment TTS output. The
  segmenter no longer sees bare fence lines, so the
  `ERROR: TTS stream failed for '\\`\\`\\`': No audio was
  received` warning is gone.

### Verified
| Check | Result |
|---|---|
| `pytest tests/voice/` | 102/102 pass (19 new + 83 existing) |
| M9-C live re-run (`m9c_voice_tools.py`) | PASS |
| TTS chunks | 201 → 68 (no more empty fence segments) |
| TTS total bytes | 141552 → 48240 |
| TTS latency (post `voice.end`) | 13.7s → 6.5s |
| TTS stream failed errors | 4 → 0 |
| Total wall (incl. ASR + warmup) | 20.2s → 12.9s |
| `agent.message` frames containing `<think>` (client-visible) | 0 |
| README first line in re-transcribed TTS | yes (`# Gundam Halo — Backend`) |
| `used_tool_content` | `True` |

### Commits in this release
- `3ce641a` — `fix(voice): M9-D strip LLM reasoning + rewrite markdown fences for TTS`
- `895bb2a` — `chore(frontend): pin dev server to 5173 with --strictPort`

---

## [0.1.1] — 2026-06-10

### Fixed
- **`/ws/voice` `voice.text` path now emits `voice.turn_ended`.** Previously
  the typed-turn handler ran the agent + TTS but never sent the terminal
  `voice.turn_ended` frame, so `halo-voice-ws` never left
  `"speaking"`/`"thinking"` and the mic button stayed disabled until a
  hard page refresh. The path now mirrors the `voice.end` flow and
  reports `total_duration_ms`. Confirmed via `scripts/m9c_dryrun_infra.py`
  Phase B (`voice.turn_ended` received post-`tts.end`).

- **CORS allowlist now includes `127.0.0.1` and port 8766.** Backend's
  uvicorn runs on `127.0.0.1:8766` (8765 is held by a detached
  `python -m http.server` in another workspace). Without this, a fresh
  backend restart dropped both ports from the allowlist and the cockpit
  UI broke.

### Added
- **`backend/scripts/m9c_dryrun_infra.py` — no-LLM-key infra dry-run.**
  Two phases:
  - **Phase A**: imports + warms up VAD (Silero JIT), ASR (Whisper base
    on mps), TTS (Edge / `zh-HK-HiuMaanNeural`), `HaloResponder`,
    `VoicePipeline`, the 9 default `ToolRegistry` tools
    (`file_read`, `file_write`, `mavis_delegate`, `memory_read`,
    `memory_write`, `open_app`, `shell_exec`, `weather`, `web_fetch`),
    and a `NativeReActAgent` instantiated with a `StubFileReadEngine`
    (scripts `file_read` on the README, then a final answer that
    quotes its first line).
  - **Phase B**: drives the full `/ws/voice` chain via the
    `voice.text` bypass path using the stub engine. Verifies
    `voice.hello` → `agent.message` → `live2d.trigger` →
    `tts.start` → `tts.audio` (binary MP3) → `tts.end` →
    `voice.turn_ended`.
  - Exit 0 = infra ready, 1 = any gap. Use as pre-flight before
    M9-C live or as a CI gate after backend infra changes.

- **`backend/scripts/m9c_voice_tools.py` — M9-C live end-to-end smoke.**
  Voice input (`tests/voice/fixtures/readme_query.wav`) → VAD → ASR →
  real `NativeReActAgent` with real `MiniMaxEngine` + 9 default tools →
  TTS → MP3. Verifies the agent's reply reaches TTS by re-transcribing
  the MP3 back through Whisper and matching the README's first line.
  Passes on this release (README line: `# Gundam Halo — Backend`,
  total wall 20.2s incl. ASR 6.3s + TTS 13.7s).

### Verified live
| Check | Result |
|---|---|
| `api.minimax.io/v1` (M2 cluster) auth | 200, 8 models incl. `MiniMax-M2` |
| Backend `/health` after restart | 200 |
| `voice.hello` frame | `vad=silero asr=whisper_local/base tts=true live2d=true` |
| Stub dry-run (Phase A + B) | PASS, total wall 0.9s |
| M9-C live (`m9c_voice_tools.py`) | PASS, `used_tool_content: True` |

### Known issues (tracking in M9-D)
See [`docs/tickets/M9-D.md`](./tickets/M9-D.md) for the full ticket
(scope, repro, proposed fix, acceptance criteria).
- LLM leaks `<think>…</think>` reasoning into `agent.message`, which
  then leaks into the TTS input. M9-D will add a post-processor that
  strips `<think>`/`<tool_call>` blocks before TTS.
- TTS sentence-segmenter doesn't understand markdown code fences
  (`` ``` ``), so an LLM reply that quotes a path or command in a
  fenced block produces fragmented audio (an "ERROR: No audio was
  received" warning per empty segment). M9-D will teach the segmenter
  to either pass fenced blocks through verbatim or skip them with a
  voice-friendly summary.

### Commits in this release
- `c91979c` — `chore(cors): add 127.0.0.1 + 8766 to allowlist`
- `dec8d1e` — `fix(voice): voice.text path now emits voice.turn_ended`
  (+ `m9c_dryrun_infra.py`)

> Gundam Halo is a local-only Mac project — no remote, no push. The
> `git log` is the source of truth between releases.

---

## [0.1.0] — 2026-06-08

Initial private release. Cockpit dashboard, project cards, memory
browser, NT-D/Unicorn theme, voice WebSocket pipeline
(VAD → ASR → LLM → TTS → Live2D), 9 default tools, NativeReAct agent,
Live2D sprite + image-set avatar modes, Tauri 2 scaffold.

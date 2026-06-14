# Feature Spec — "Hey Unicorn" Voice Control (Sprint 16)

> **Status:** SIGNED OFF, 2026-06-14.
> **Author:** Mavis (orchestrator).
> **Scope:** 1 week (5 working days). Brings Gundam Halo from "push-to-talk
> only, missing 5 tools" to "prefix wake phrase + complete tool surface for
> the v1 use-case catalog".
> **Out of scope (this sprint):** Native always-on wake-word engine.
> Sprint 17 candidate, **planned to leverage `~/workspace/yuesub-api`** for
> Cantonese ASR + VAD (SenseVoice + fsmn-vad + Cantonese BERT corrector).

---

## 1. Background & motivation

The headline use case in `docs/ARCHITECTURE.md` §15 and on the dashboard
landing page is:

> "Sit at your Mac, say **'Hey Unicorn'**, and the agent takes over."

A capability audit (this doc, §2) found that the **agent loop, ASR, TTS,
and 12 of 16 tools are working**, but the **user-facing entry point is
broken**:

1. There is no wake-word detection. Users must press-and-hold a button.
2. Five common Mac-control tools (brightness, DND / Focus, Bluetooth,
   Mail, screenshot) are missing entirely.
3. There's no documented "Unicorn/獨角獸" prefix convention that lets
   the agent parse casual speech into commands.

This sprint ships the **first two layers of value**:
- A unified tool surface so a single voice turn can chain 3+ actions
  (git pull → read log → reply) without the LLM being stopped at "no
  such tool".
- A **text-level** wake phrase "Unicorn/獨角獸" prefix that turns push-to-
  talk into a conversational hands-free mode. (Native audio-level wake-
  word detection is Sprint 17.)

---

## 2. Capability matrix (audit result)

| # | Use case (from spec) | Status | Path | Notes |
|---|---|---|---|---|
| 0 | "Hey Unicorn" wake | ❌ Missing | — | **No hotword engine.** Native wake-word is Sprint 17. This sprint ships text-prefix fallback. |
| 1a | "Open Safari & go to Gmail" | ✅ Works | `open_app` + `apple_script` | `tell application "Safari" to open location "https://mail.google.com"` |
| 1b | "Switch to VS Code & open latest project" | ⚠️ Partial | `open_app` + agent state | Lacks project recency memory |
| 2a | "Find PDF on Desktop" | ✅ Works | `spotlight` | `mdfind "kind:pdf" only_in ~/Desktop` |
| 2b | "Move latest Downloads image to Projects" | ✅ Works | `shell_exec` (`mv` allowlisted) | `ls -t` + `mv` chain via ReAct |
| 3a | "Lower screen brightness" | ❌ Missing | — | **Sprint 16: add `brightness` tool** (AppleScript `System Events`) |
| 3b | "Turn on DND + connect AirPods" | ❌ Missing | — | **Sprint 16: add `system_settings` tool** (DND via `defaults`; BT via `blueutil` if installed, else report and skip) |
| 3c | "Connect AirPods" | ❌ Missing | — | Same as 3b (BT) |
| 4a | "Create note 'Meeting notes' + paste clipboard" | ⚠️ Partial | `clipboard` + `shell_exec` | Writes file, not Apple Notes. **Sprint 16: prefer Apple Notes via AppleScript** |
| 4b | "Reply to email with 'got it'" | ❌ Out of scope | — | **DEFERRED.** User confirmed Mail is not a priority for v1. Tool removed from Sprint 16. |
| 5a | "git pull + report latest commit" | ✅ Works | `shell_exec` | Multi-turn ReAct, fully streamed |
| 5b | "Screenshot desktop, save as quickshot.png, open in Preview" | ⚠️ Partial | `shell_exec` | Uses `screencapture` shelled out. **Sprint 16: add dedicated `screenshot` tool** |
| 6a | "Today's weather?" | ✅ Works | `weather` | wttr.in |
| 6b | "Close all Chrome tabs except work ones" | ⚠️ Partial | `apple_script` | No "work-related" classifier — LLM has to guess by URL. **Out of scope this sprint** |
| 7a | AppleScript automation (general) | ✅ Works | `apple_script` | String-in / string-out |
| 7b | Multi-step task orchestration | ✅ Works | ReAct loop | Streaming, max 10 turns |
| 7c | Streaming TTS reply | ✅ Works | `tts.stream_synthesize` | First-audible ~1-1.5s |
| 7d | Streaming agent response | ✅ Works | `engine.stream_chat` | Per-sentence yield |

**Coverage after this sprint:** 14 of 16 use cases ✅/⚠️ (up from 12).
**Coverage if user-facing wake phrase is shipped:** 100% of *conversational*
use cases land in the agent. Only the 0 → 1 hands-free trigger remains.

---

## 3. Goals (success criteria)

1. A single voice turn can complete a 4-step task (open app → read file →
   set brightness → notify result) without the agent running out of tools.
2. The user can say **"Unicorn/獨角獸/Uni/UM"** at the start of a turn and
   the system triggers the agent without pressing any extra button.
3. The push-to-talk button still works as a fallback (no regression).
4. All Sprint 16 work is delivered behind the existing Vite dev proxy —
   no architectural rewiring, no new build pipeline, no new deployment
   step.
5. New tools are added behind the existing `default_tools()` factory
   so every existing session picks them up automatically.
6. No new npm / pnpm / pip dependencies unless absolutely necessary.

---

## 4. Non-goals (explicit)

- **Native wake-word detection (always-on listening).** Sprint 17+ candidate.
  This sprint ships *text-level* wake phrase detection that runs after
  ASR. The mic is still push-to-talk.
- **GUI automation (synthetic mouse / keyboard input).** Out of scope.
  a11y tool remains read-only. (M11 explicitly chose to defer this.)
- **Bidirectional Mail sync / OAuth.** The mail tool uses AppleScript
  against the system Mail app; no IMAP/SMTP credentials are stored.
- **Work-tab classification (#6b).** Heuristic / model-based filtering
  is a Sprint 18+ problem.
- **Native Tauri hotword mic capture.** Even if Sprint 17 adds
  Porcupine / openWakeWord, this sprint does not change Tauri shell
  configuration.

---

## 5. User-facing behavior

### 5.1 Push-to-talk (unchanged)

- User holds the 🎤 button in the right panel, speaks, releases.
- Behavior is identical to the current `use-voice-input` flow.
- The cockpit shows `◉ Listening…` while held, `⌛ Thinking…` while
  ASR + agent run, `▶ Speaking…` while TTS plays.

### 5.2 NEW: Text-level wake phrase

After ASR returns the user's transcript, the voice pipeline checks
**whether the transcript starts with a wake phrase** before invoking the
agent. If yes, the transcript is treated as a command (the wake phrase
itself is stripped, the remainder becomes the user's task).

**Recognized wake phrases** (configurable, defaults below — user-approved
2026-06-14):

| Language | Phrase | Notes |
|---|---|---|
| English | "Unicorn" | Brand |
| English | "NTD" | Gundam NT-D theme — in-world codename |
| English | "gundam" | Lowercase to match casual speech |
| Chinese (HK) | "獨角獸" | "Unicorn" literal |
| Chinese (HK) | "高達" | "Gundam" Cantonese pronunciation — high recognition confidence from Whisper |

If the transcript does **not** start with a wake phrase, the current
behavior is preserved: the agent is invoked with the full transcript
as a normal text message. This keeps typing-in-the-cockpit working
unchanged (no accidental wake phrase matching in the text input).

**Where this lives:**
- Backend: `app/voice/pipeline.py` (or a small wrapper around it) gets
  a `detect_wake_phrase(text) → str | None` helper.
- Frontend: `VoicePanel` shows a small "Listening for **Unicorn**" hint
  below the mic button so the user knows the prefix is supported.
- Configuration: `Settings → Voice` tab (new) exposes
  `wake_phrases: string[]` for the user to add custom prefixes.

### 5.3 NEW: Five missing tools

| Tool | Function | Implementation |
|---|---|---|
| `brightness` | Get / set screen brightness (0–100%) | AppleScript: `tell application "System Events" to set brightness of ...` |
| `system_settings` | Toggle DND / Focus mode, get / set various system prefs | `defaults write com.apple.controlcenter ...` for DND |
| `bluetooth` | Connect / disconnect a paired BT device, list paired | `blueutil` CLI wrapper (if installed) or `system_profiler SPBluetoothDataType` for listing |
| `screenshot` | Capture screen / window / region to a path | `screencapture` wrapper with sane defaults (no sound, no shadow, full screen) |
| `mail` | Read inbox (subjects + from + snippet), reply to most recent, send new | AppleScript `tell application "Mail"` |

### 5.4 Settings → Voice tab (new)

A new tab in the existing Settings page (`routes/settings/`) lets the
user:

- Edit `wake_phrases` (list of strings, multi-line textarea)
- Toggle "strict wake phrase" mode (default: off — any transcript is
  passed to the agent; wake phrase just adds a confidence marker)
- See live mic status + last ASR transcript (for debugging)

---

## 6. Architecture

### 6.1 Text-level wake phrase (cheap, in-process)

```
push-to-talk → VAD → ASR(text)
                          ↓
              detect_wake_phrase(text)  ←── config: wake_phrases[]
                          ↓
              if hit: strip prefix, mark `wake_triggered: true`
                          ↓
              pass to agent.run_streaming(text)
                          ↓
              voice reply + tool calls (unchanged)
```

The check is a single regex over the first ~32 chars of the transcript,
in Cantonese + Mandarin + English. Cost: < 0.1 ms, no model.

### 6.2 New tool layout

```
backend/app/tools/
├── brightness.py          (NEW, ~60 lines)
├── system_settings.py     (NEW, ~80 lines, DND / Focus + general)
├── bluetooth.py           (NEW, ~80 lines, requires blueutil hint)
├── screenshot.py          (NEW, ~50 lines)
└── builder.py             (MODIFIED, add 4 new tools to default_tools;
                            Mail tool NOT added — deferred per user)
```

Each tool follows the existing `BaseTool` pattern (see
`backend/app/tools/weather.py` for the canonical example). All go
through the `cfg.mac.<config>.enabled` gate (TBD per tool; DND / BT /
Mail need explicit user opt-in via Settings).

### 6.3 Frontend changes

- `routes/settings/VoiceTab.tsx` (NEW) — wake phrase config
- `components/gundam/VoicePanel.tsx` (MODIFIED) — "Listening for **Unicorn**"
  hint, settings link
- `components/gundam/WakePhraseHint.tsx` (NEW, ~40 lines) — small inline
  hint with link to settings

### 6.4 What does NOT change

- Voice WebSocket protocol (`/ws/voice` wire format)
- `agent.run_streaming()` shape
- Tauri shell
- Mic permission flow
- WebSocket heartbeat / reconnect logic
- Per-project memory layout
- Backend startup wiring (no new `set_agent_callback` calls)

---

## 7. File-by-file plan

### Day 1 — Tool surface foundations (4 new tools — Mail removed per user)
- `backend/app/tools/brightness.py` — AppleScript, 2 ops (get/set)
- `backend/app/tools/screenshot.py` — `screencapture` wrapper, 3 modes
- `backend/app/tools/system_settings.py` — DND toggle + read prefs
- `backend/app/tools/bluetooth.py` — `blueutil` wrapper with graceful
  fallback to `system_profiler` listing
- `backend/app/tools/builder.py` — add 4 to `default_tools()`
  (Mail tool **removed** from Sprint 16 — user opted out)

### Day 2 — Tool tests
- `backend/tests/tools/test_brightness.py` — happy path + permission error
- `backend/tests/tools/test_screenshot.py` — file existence, format
- `backend/tests/tools/test_system_settings.py` — DND toggle roundtrip
- `backend/tests/tools/test_bluetooth.py` — skip if `blueutil` not installed
- `backend/tests/tools/test_builder.py` — assert all 19 tools are wired
  (4 new + 15 existing — Mail not included)

### Day 3 — Wake phrase detection
- `backend/app/voice/wake_phrase.py` (NEW) — `detect(text) → bool`,
  `strip(text) → text`
- `backend/app/voice/pipeline.py` — integrate into `finalize_turn`
  return value: `VoiceTurnResult.wake_triggered: bool`
- `backend/app/api/voice_ws.py` — pass `wake_triggered` to
  `agent.message` event so the frontend can badge it
- `backend/app/api/voice_ws.py` — also handle `voice.text` path
  (text bypass)
- `backend/app/main.py` — Settings → wake_phrases list (read from config)
- `backend/app/core/config.py` — add `VoiceConfig.wake_phrases: list[str]`
  with default `["Unicorn", "NTD", "gundam", "獨角獸", "高達"]`
  (user-approved 2026-06-14)
- `backend/tests/voice/test_wake_phrase.py` — fixture-driven test
  matrix (each phrase × each language × ASR artifact)

### Day 4 — Frontend + Settings
- `frontend/src/routes/settings/VoiceTab.tsx` (NEW) — wake phrase list
  editor + mic status + last ASR transcript
- `frontend/src/components/gundam/WakePhraseHint.tsx` (NEW) — small
  inline hint with link to settings
- `frontend/src/components/gundam/VoicePanel.tsx` (MODIFIED) — wire
  the hint, surface "Unicorn" status badge
- `frontend/src/lib/api.ts` — add `getVoiceConfig()` / `setVoiceConfig()`
- `frontend/src/routes/settings/index.tsx` (MODIFIED) — register
  `voice` tab

### Day 5 — Verification + doc
- End-to-end smoke: relaunch dev server, push-to-talk "Unicorn, what's
  the weather" → confirm prefix stripped, agent invoked, TTS reply
- Manual test the 5 new tools via the chat panel
- Update `docs/CHANGELOG.md`, `docs/ARCHITECTURE.md` §15.10
- Run full backend + frontend test suites
- `pnpm run build` clean

---

## 8. Risks & mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| New tools increase agent's tool count, prompt gets too long, MiniMax 401s or degrades | Medium | Medium | Test with real model; tool descriptions trimmed to ~120 chars each; reorder so common tools come first |
| AppleScript permissions silently fail on first run (TCC) | High | Low | Tool returns a clear "Allow in System Settings → Privacy → Automation" message; doc updated |
| `blueutil` not installed on user's Mac | High | Low | Tool gracefully reports "Bluetooth control requires `brew install blueutil`" and continues with listing only |
| Mail AppleScript blocks on the OS Mail app for 30+ s when mailbox is large | n/a | n/a | **Removed** — Mail tool out of scope per user |
| Wake phrase false positives (transcripts that happen to start with "Unicorn" the user's typing) | Low | Low | Default mode is "permissive" — wake phrase is just a confidence marker, not a gate. Strict mode is opt-in. |
| ASR artifacts ("ok 角仙") drop the wake phrase from Cantonese transcripts | Medium | Medium | Maintain a small list of common ASR-variant phrases; can be edited by the user in Settings |
| ASR artifacts on "NTD" (e.g. "恩蒂迪" or "N.T.D." letter-by-letter) | Low | Low | User can extend `wake_phrases` in Settings; framework normalizes whitespace and case |
| Backend streaming + tool count push first-audible latency back up | Low | Medium | Re-benchmark after the tool changes; if first-audible > 2 s, defer non-essential tools behind a "lazy" flag |

---

## 9. Acceptance tests

A change is "done" when:

1. `pnpm run lint` is 0 errors, `pnpm run test` 47+ pass.
2. `cd backend && uv run pytest` all pass except pre-existing URL drift
   in `test_default_config` (already known; tracked separately).
3. `pnpm run build` clean, produces `dist/`.
4. Manual smoke checklist:
   - [ ] Push-to-talk "Unicorn, what is the weather in Hong Kong" →
     agent invokes `weather("Hong Kong")` and replies with TTS.
   - [ ] Push-to-talk "Set brightness to 50 percent" → screen visibly
     dims to 50% (on a display that supports it).
   - [ ] Push-to-talk "Take a screenshot to my desktop" → file
     `~/Desktop/screenshot_*.png` appears.
   - [ ] Settings → Voice tab shows the wake phrase list, edits
     persist across reload.
   - [ ] Strict wake phrase mode (Settings toggle) blocks a
     transcript that does not start with a recognized phrase
     (agent not invoked, voice reply "I didn't catch a wake phrase").
5. No new TODOs / FIXMEs left behind. `rg "TODO|FIXME" backend/app frontend/src` returns only the pre-existing entries (if any).

---

## 10. Out-of-scope (deferred)

- **Native wake-word detection** — Sprint 17+. Engine is **planned
  to leverage `~/workspace/yuesub-api`**, which already provides:
  - `fsmn-vad` (low-latency voice activity detection)
  - SenseVoice (FunAudioLLM) — significantly better Cantonese ASR
    than the current `whisper_local` (base) setup
  - Cantonese BERT corrector (`hon9kon9ize/bert-large-cantonese`)
    for post-ASR cleanup
  - `OnnxTranscriber` / `StreamTranscriber` modules ready to embed
  Sprint 17 will wire yuesub-api as a sub-engine of Gundam Halo's
  voice layer (likely as a subprocess or a sidecar process) and
  use SenseVoice's continuous streaming + substring match for
  the 5 wake phrases. Trade-off table will be written into
  `docs/ARCHITECTURE.md` §5.2 in the Sprint 17 spec.
- **Work-tab classifier** (close non-work Chrome tabs) — Sprint 18.
  LLM-based with a configurable blocklist.
- **Bidirectional Mail sync** — only AppleScript against system Mail
  is shipped. No IMAP / Gmail OAuth.
- **Synthetic input** (mouse / keyboard) — explicitly out of v0.1.x
  per `app/mac/a11y.py` docstring.

---

## 11. Open questions — answered

All design decisions resolved 2026-06-14:

1. **Wake phrase names (user-approved).** Default list:
   `["Unicorn", "NTD", "gundam", "獨角獸", "高達"]`.
   - "Unicorn" — brand
   - "NTD" — Gundam NT-D theme, in-world codename
   - "gundam" — lowercase to match casual speech
   - "獨角獸" — "Unicorn" literal Chinese
   - "高達" — "Gundam" Cantonese pronunciation (high Whisper recognition
     confidence; can also pair with 前綴 like "高達幫我")
2. **Mode: permissive.** Any transcript is passed to the agent; wake
   phrase is a confidence marker shown in the `MissionLog`, not a
   hard gate. (User explicitly chose permissive over strict.)
3. **Tool visibility: `MissionLog` shows tool calls** (default
   behavior; user confirmed).
4. **Mail tool removed from Sprint 16** (user opt-out). No `mail.py`.
5. **Sprint 17 wake-word engine: `~/workspace/yuesub-api`.** Sprint 17
   spec (separate doc) will detail how to wire `fsmn-vad` + SenseVoice
   + Cantonese BERT corrector into the cockpit as a sidecar engine.

---

## 12. Sign-off

- [x] **Spec scope agreed** — 4 new tools (Mail removed) + text-level wake
      phrase + Voice settings tab.
- [x] **Wake phrase defaults agreed** — `["Unicorn", "NTD", "gundam",
      "獨角獸", "高達"]`.
- [x] **Permissive default agreed.**
- [x] **MissionLog tool-call display** — current default, no change.
- [x] **Sprint 17 wake-word engine** — `~/workspace/yuesub-api` is
      the chosen source for Cantonese ASR + VAD (SenseVoice / fsmn-vad).

**Signed off 2026-06-14.** Implementation plan to follow in next
message (todo list, parallel tracks, verification gates).

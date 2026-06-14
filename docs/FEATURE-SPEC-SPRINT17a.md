# Feature Spec — Voice Hygiene: Strict Mode + Cross-Sentence Sanitizer (Sprint 17a)

> **Status:** SIGNED OFF, 2026-06-14.
> **Default flipped per user:** `strict_wake_phrase = true` (not false).
> Sign-off items 1, 2, 5, 6 confirmed. Items 3 & 4 → see §9 resolution.
> **Author:** Mavis (orchestrator).
> **Scope:** ~1 working day. Two small but high-UX-value cleanups
> building on Sprint 16 (text-level wake phrase + voice sanitizer).
> **Out of scope (this sprint):** Native wake-word engine, Cantonese
> BERT corrector. Both deferred to Sprint 17b/17c, which will wire
> `~/workspace/yuesub-api` (SenseVoice + fsmn-vad + corrector) into
> the voice layer.

---

## 1. Background & motivation

Sprint 16 shipped the text-level wake phrase ("Unicorn/獨角獸/NTD/gundam/高達")
plus the `voice_sanitizer` that strips `<think>…</think>` and rewrites
fenced code blocks. Two follow-up gaps showed up in live use:

1. **Permissive mode by default — the agent runs on every transcript.**
   Push-to-talk has no "voice is real and intended" signal. Background
   TV, accidental mic-button bump, or an echoed notification all
   fire the LLM. The user has no way to opt into a stricter gate
   where the agent stays silent unless the transcript starts with a
   recognized wake phrase.
2. **`<think>…</think>` leak across sentence boundaries.** The
   sanitizer's `_THINK_RE` regex is a single-shot non-greedy match
   per call. The voice pipeline calls `sanitize_for_tts(sentence)`
   once per yielded sentence. If the LLM opens `<think>` in one
   sentence and closes it in the next, sentence 1 keeps the open tag
   and the user hears "think…" in the spoken reply and sees
   `<think>…` in the cockpit transcript.

Both are **small, well-scoped** fixes — no model swap, no new infra,
no new dependencies. They're the right "filler" between Sprint 16
ship and Sprint 17b wake-word, and they pre-validate the voice
configuration plumbing that 17b will lean on.

---

## 2. Goals (success criteria)

1. **Strict wake-phrase mode** is a user-facing toggle in
   `Settings → Voice`. Default: **ON** (per user 2026-06-14 sign-off).
   When on (the default): a voice turn whose ASR transcript does
   not start with a configured wake phrase is **discarded** — no
   agent invocation, no TTS, the user gets a brief in-cockpit
   hint. **BREAKING CHANGE** for users who never opened the tab —
   documented in the §11 "What changed for existing users" section.
2. **Cross-sentence `<think>` sanitizer** — if the LLM opens a
   `<think>` block in sentence N and the close tag arrives in
   sentence N+M, none of the open-tag content is rendered to the
   cockpit transcript or spoken by TTS. The close-tag content (if
   any) is preserved. The implementation is a tiny per-turn state
   flag carried across `sanitize_for_tts()` calls.
3. The strict-mode flag and wake-phrase list are persisted to
   `~/.gundam-halo/config.toml` next to the existing `wake_phrases`
   key, and the in-memory config is updated immediately so the
   next turn picks up the change without a server restart. Same
   semantics as Sprint 16's `/voice/config` PUT.
4. Existing tests still pass. New unit tests cover both features
   in the same `pytest` files Sprint 16 touched.

---

## 3. Out of scope (deferred)

- **Native wake-word engine** — Sprint 17b. Plan: wire
  `~/workspace/yuesub-api`'s `OnnxTranscriber` (SenseVoice +
  fsmn-vad) into the voice pipeline as a second ASR backend
  selectable via `cfg.voice.asr.backend = "yuesub"`. Substring
  match on the wake phrase, same text-level fallback when
  SenseVoice doesn't pick it up cleanly.
- **Cantonese BERT corrector** — Sprint 17b/17c alongside
  yuesub-api. Post-ASR text fix-up via
  `hon9kon9ize/bert-large-cantonese`.
- **Tauri-side always-on mic capture** — Sprint 18+. Even with
  yuesub-api, the v1 push-to-talk flow stays; always-on requires
  Swift binding work in the Tauri shell.
- **Work-tab classifier** (close non-work Chrome tabs) — Sprint
  18+. Unrelated to voice hygiene.

---

## 4. User-facing behavior

### 4.1 Strict wake-phrase mode (NEW toggle)

A new checkbox in the existing `Settings → Voice` tab:

```
┌──────────────────────────────────────────────────────┐
│  ☐ Strict wake-phrase mode                          │
│                                                      │
│  When ON, voice turns are discarded unless the      │
│  ASR transcript starts with a configured wake       │
│  phrase. Text-input / voice.text still works.       │
│  (Default: OFF — permissive, all turns run.)        │
└──────────────────────────────────────────────────────┘
```

**Permissive (toggle OFF — legacy behavior, opt-in):**
- Any transcript → agent runs → TTS reply.
- Wake phrase matched → prefix stripped, `wake_triggered: true`
  flag attached (visible in MissionLog + transcript badge).
- Wake phrase not matched → agent runs anyway, no flag.

**Strict (default ON — new behavior):**
- Transcript starts with wake phrase → same as permissive
  (strip + flag + agent + TTS).
- Transcript does **not** start with wake phrase →
  - The `asr.result` frame is still sent to the frontend
    (so the user sees what was heard, and the wake-phrase
    chip shows "—" / "no wake").
  - The agent is **not** invoked.
  - No TTS is sent.
  - A new `voice.turn_ended` frame with `discarded: true`
    and a new `reason: "no_wake_phrase"` is sent so the
    frontend can show a brief hint ("Listening for **Unicorn**…").
  - This also applies to the `voice.text` text-input path —
    typing "what's the weather" without a wake phrase is
    **silently dropped** in strict mode (the text path is
    gated by the same flag). Rationale: the flag is named
    "strict wake-phrase mode" not "strict voice mode" —
    any input from the voice subsystem must carry the wake
    phrase; text-only is a debug surface, not a primary
    input channel, and the user said "I want to gate
    everything that comes through the voice layer".

**Out-of-band paths unaffected.** HTTP `/api/chat`,
`/api/projects/<name>/chat`, Telegram, etc. are not the
voice layer. They continue to invoke the agent with no
wake-phrase check. This keeps CLI / IM workflows working
unchanged.

### 4.2 `<think>` cross-sentence sanitization (always-on)

A bug in the existing `voice_sanitizer.strip_reasoning()`:

```python
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)

def strip_reasoning(text: str) -> str:
    ...
    out = _THINK_RE.sub("", text)
    ...
```

If a model emits:

```
Sentence 1: "<think>The user wants to know the weather."
Sentence 2: "According to wttr.in, HK is 25°C."
```

the regex only matches inside sentence 1 (no `</think>` yet)
and the user hears "think The user wants to know the weather.
According to wttr.in, HK is 25°C." with the open tag still
visible in the cockpit transcript.

**Fix:** a module-level stateful flag `_think_open: bool`
tracked across calls. `strip_reasoning()` short-circuits and
returns empty string when `_think_open` is set, until it
sees a `</think>` tag, after which it sets `_think_open = False`
and returns the text **after** the close tag (since the body
between open and close is reasoning and should be suppressed).

`voice_ws.py` resets the flag at each `voice.turn_started`
/ `voice.text` boundary so state never leaks between turns.

**Public surface change:** `strip_reasoning()` gains a
private `state` parameter (default None) so the per-turn
state can be threaded through `sanitize_for_tts()` callers
in `voice_ws.py` without using a module global in
production paths. Module global stays as the default
fallback for the test suite (which doesn't care about
state threading).

### 4.3 Settings → Voice tab updates

```diff
 <Section title="Wake phrases (Sprint 16)">
   <textarea … placeholder="Unicorn …" />
   <button>Save wake phrases</button>
 </Section>

+<Section title="Wake-phrase gate (Sprint 17a)">
+  <label>
+    <input type="checkbox" /> Strict mode (only fire on a wake phrase)
+  </label>
+  <button>Save</button>
+</Section>
```

The "How it works" footer copy is updated to reflect the
toggle's existence and direct the user to this spec.

---

## 5. Architecture

### 5.1 Strict-mode gate (in-process, no new infra)

```
                ┌──────────────────────────────┐
                │  push-to-talk OR voice.text  │
                └───────────────┬──────────────┘
                                ↓
                ┌──────────────────────────────┐
                │  VAD → ASR (text)            │
                └───────────────┬──────────────┘
                                ↓
                ┌──────────────────────────────┐
                │  detect_wake_phrase(text)    │
                │  → WakeMatch(matched, …)     │
                └───────────────┬──────────────┘
                                ↓
                ┌──────────────────────────────┐
                │  cfg.voice.strict_wake_phrase│
                │  AND not wake.matched?       │
                │  → send asr.result           │
                │  → send voice.turn_ended     │
                │     (discarded=true,         │
                │      reason="no_wake_phrase")│
                │  → return                    │
                └───────────────┬──────────────┘
                                ↓ (allowed)
                ┌──────────────────────────────┐
                │  emit asr.result             │
                │  invoke agent.stream_chat    │
                │  → agent.message + TTS       │
                │  → voice.turn_ended          │
                │     (discarded=false)        │
                └──────────────────────────────┘
```

The gate is one `if` in `voice_ws.py` after `detect_wake_phrase()`,
in **both** the `voice.end` (push-to-talk) and `voice.text`
(text-input) paths. Two ifs, ~10 lines, no shared helper.

### 5.2 Cross-sentence `<think>` sanitizer (state threading)

```
HaloResponder.respond_stream yields sentences:
   sentence 1 → sanitize_for_tts(sentence 1, state)
                  → strip_reasoning(sentence 1, state)
                  → state.think_open still True after
                    sentence 1 (open tag, no close)
                  → returns ""
   sentence 2 → sanitize_for_tts(sentence 2, state)
                  → strip_reasoning(sentence 2, state)
                  → state.think_open False (close tag
                    found at start of sentence 2)
                  → returns text after the close tag
   sentence 3 → sanitize_for_tts(sentence 3, state)
                  → state.think_open False, no tags
                  → returns "regular reply text"
```

State object: a small `@dataclass(slots=True, frozen=True)`
`SanitizerState` with `think_open: bool = False`. The
`voice_ws._emit_agent_response_streaming` closure allocates
one per turn and passes it into every `sanitize_for_tts()`
call. On turn end (or turn cancel) the state is discarded.

**Why state threading, not module global:**
The existing module global was fine when `strip_reasoning()`
was a pure function. Threading state explicitly through
`sanitize_for_tts(text, state=None)` keeps the function
reentrant (important if we ever run two voice turns in
parallel — Sprint 18+ multiclient) and makes the test
suite trivially hermetic (pass a fresh `SanitizerState()`
in each test).

### 5.3 Config schema changes

```toml
# ~/.gundam-halo/config.toml — [voice] section

[voice]
enabled = true
wake_phrases = ["Unicorn", "NTD", "gundam", "獨角獸", "高達"]
strict_wake_phrase = true        # NEW, default true (Sprint 17a)
```

`VoiceConfig` dataclass gains one field:
```python
strict_wake_phrase: bool = True   # Sprint 17a — strict is the new default
```

`_load_voice_config()` reads the new key with the default.

### 5.4 API changes

| Endpoint | Verb | Change |
|---|---|---|
| `GET /voice/config` | GET | Response gains `strict_wake_phrase: bool` field |
| `PUT /voice/config` | PUT | Body may now include `strict_wake_phrase: bool`; persisted next to `wake_phrases` |

### 5.5 WS frame changes

| Frame | Type | Change |
|---|---|---|
| `asr.result` | voice → cockpit | **Unchanged payload** (always includes `text`, `wake_phrase`, `wake_triggered`). In strict mode, `wake_triggered` is `false` and the cockpit just shows "I didn't catch a wake phrase". |
| `voice.turn_ended` | voice → cockpit | Adds optional `reason: "no_wake_phrase" | "user_cancel" | "no_agent" | null` field. `discarded` is `true` in those cases. |

### 5.6 Frontend type + UI changes

- `frontend/src/services/halo-voice-ws.ts`:
  - `VoiceTranscriptEvent.data` gains `wake_phrase: string`,
    `wake_triggered: boolean` (the backend was already
    emitting these, but the TS type omitted them — fixing
    the type-guard gap surfaced during Sprint 16 review).
  - `VoiceTurnEndedEvent.data` gains optional
    `reason: "no_wake_phrase" | "user_cancel" | "no_agent" | null`.
- `frontend/src/routes/settings/VoiceTab.tsx`:
  - Add a new `<Section title="Wake-phrase gate (Sprint 17a)">`
    with a checkbox bound to `config.strict_wake_phrase`.
  - `Save` button PUTs both `wake_phrases` and
    `strict_wake_phrase` in one request (extending the
    existing `setVoiceConfig()`).
- `frontend/src/lib/api.ts`:
  - `setVoiceConfig()` payload type gains
    `strict_wake_phrase?: boolean`.
  - `getVoiceConfig()` return type gains
    `strict_wake_phrase: boolean`.

---

## 6. File-by-file change set

| Path | Change | LoC est. |
|---|---|---|
| `backend/app/voice/tts/voice_sanitizer.py` | Add `SanitizerState` dataclass; thread `state` param through `strip_reasoning` and `sanitize_for_tts`; update `_THINK_RE` matching to short-circuit when `state.think_open` is True. Existing per-sentence test fixtures still pass; new fixtures cover the cross-sentence case. | +35 / -8 |
| `backend/app/voice/wake_phrase.py` | **No code change.** Module docstring is updated to mention strict-mode (Sprint 17a) is now an opt-in toggle. | +6 / 0 |
| `backend/app/core/config.py` | `VoiceConfig` gains `strict_wake_phrase: bool = True` (default true per sign-off); `_load_voice_config()` reads `[voice].strict_wake_phrase`. | +6 / 0 |
| `backend/app/api/voice_ws.py` | After `detect_wake_phrase()` in both `voice.end` and `voice.text` paths: if `cfg.voice.strict_wake_phrase and not wake.matched`, send `asr.result` + `voice.turn_ended{discarded:true, reason:"no_wake_phrase"}` and skip agent. Add `reason` field to all `voice.turn_ended` frames. Allocate `SanitizerState()` in `_emit_agent_response_streaming`, pass it into `sanitize_for_tts()`. Extend `GET/PUT /voice/config` for `strict_wake_phrase`. | +55 / -5 |
| `backend/tests/voice/test_voice_sanitizer.py` | Add 4 tests: cross-sentence `<think>` opening across two sentences, closing on a later sentence, mixed `<tool_call>` and `<think>`, multiple open/close pairs in one turn. | +60 / 0 |
| `backend/tests/voice/test_voice_ws.py` | Add 2 tests: strict-mode discards a no-wake ASR, strict-mode discards a no-wake text-input, strict-mode allows a wake-phrase ASR through. | +50 / 0 |
| `frontend/src/lib/api.ts` | `getVoiceConfig` / `setVoiceConfig` types gain `strict_wake_phrase`. | +6 / 0 |
| `frontend/src/services/halo-voice-ws.ts` | `VoiceTranscriptEvent.data` gains `wake_phrase` + `wake_triggered` (the runtime payload already had them — Sprint 16 type-guard gap). `VoiceTurnEndedEvent.data` gains optional `reason`. | +8 / -2 |
| `frontend/src/routes/settings/VoiceTab.tsx` | Add `Section "Wake-phrase gate"` with checkbox + Save button. Update "How it works" copy. Update `handleSave` to also persist `strict_wake_phrase`. | +40 / -5 |

**Total backend:** +156 / -13. **Total frontend:** +54 / -7.

---

## 7. Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Strict mode blocks legitimate "I just want to ask something" voice turns, user has to add a wake prefix | High | Medium | Default is OFF. If user flips it ON, they've signed up for the gate. Add a clear "Strict mode is on" indicator in the cockpit so the user knows why their turn is being dropped. |
| `<think>` state threading breaks the existing per-sentence test fixtures | Low | Low | All existing fixtures use single-sentence inputs with the close tag in the same sentence — the new code path only differs when `state.think_open` is True. New fixtures cover the new paths; existing ones pass unchanged. |
| `voice.turn_ended.reason` field confuses older frontend clients that don't recognize it | Low | Low | Field is optional; older clients ignore unknown fields. New field name is descriptive. |
| User toggles strict mode and forgets, then wonders why the agent "isn't responding" | Medium | Medium | When strict mode is ON and a turn is discarded, the cockpit shows a 2-second toast: "Wake phrase not detected — strict mode is on". Toast uses the existing Sonner theme. |
| The `<think>` state leaks between turns if a sentence is dropped (e.g. cancelled mid-stream) | Low | Low | `voice_ws._emit_agent_response_streaming` allocates a fresh `SanitizerState()` per turn. `voice.cancel` already resets the pipeline; we add `state.think_open = False` reset to the cancel path too. |
| `cfg.voice.strict_wake_phrase` doesn't load from `config.toml` (e.g. user has old config without the key) | Low | Low | Default is `True` (Sprint 17a new default); `_load_voice_config()` uses `d.get("strict_wake_phrase", defaults.strict_wake_phrase)` so missing key → strict (consistent new behavior). Users who want permissive can set the flag explicitly. |
| **BREAKING CHANGE**: existing users who never opened Settings → Voice tab now have strict mode silently on, so casual voice turns get dropped | **High** | Medium | On first launch after the upgrade, if `cfg.voice.strict_wake_phrase` is unset, server logs a one-time INFO: "Strict wake-phrase mode is now on by default. To revert: Settings → Voice → uncheck 'Strict mode'." Cockpit shows a dismissable banner for 7 days post-upgrade ("New: voice turns need a wake phrase to invoke the agent. [Settings] [Dismiss]"). |

---

## 8. Acceptance tests

A change is "done" when:

1. **Unit tests pass:**
   - `cd backend && uv run pytest tests/voice/test_voice_sanitizer.py` —
     4 new tests, all existing tests still green.
   - `cd backend && uv run pytest tests/voice/test_voice_ws.py` —
     3 new tests (strict-no-wake-discard-asr, strict-no-wake-discard-text,
     strict-wake-allows-asr), all existing tests still green.
   - `cd backend && uv run pytest` — full suite green except the
     pre-existing URL-drift skip in `test_default_config`.
2. **Frontend builds clean:**
   - `pnpm run lint` — 0 errors.
   - `pnpm run test` — all 47+ tests pass.
   - `pnpm run build` — clean, produces `dist/`.
3. **Manual smoke checklist:**
   - [ ] Settings → Voice tab: see the new "Wake-phrase gate" section
     with a checkbox. Default **checked** (strict mode on).
   - [ ] Uncheck the box, click Save → reload page → checkbox still
     unchecked. `~/.gundam-halo/config.toml` has
     `strict_wake_phrase = false`.
   - [ ] Push-to-talk "what's the weather" (no wake phrase) in
       strict mode (default) → no TTS, no agent call, cockpit shows a
       2-second toast "Wake phrase not detected".
   - [ ] Push-to-talk "Unicorn, what's the weather" in strict
       mode → agent runs, TTS plays (same as permissive).
   - [ ] Flip back to permissive (uncheck the box, save), repeat
       the no-wake push-to-talk → agent runs (current behavior
       preserved).
   - [ ] `text-input` field in strict mode without wake phrase →
       discarded (no agent call).
   - [ ] LLM emits `<think>The user wants X.` in sentence 1
       and "the answer is Y" in sentence 2 (test fixture or
       prompt injection) → cockpit transcript shows only
       "the answer is Y"; TTS does not speak "think The user
       wants X.".
   - [ ] **First-launch upgrade path**: delete `~/.gundam-halo/config.toml`,
       restart server, push-to-talk "what's the weather" without
       a wake phrase → discarded (strict-on default kicks in even
       with no config file). Cockpit shows the 7-day upgrade banner
       on first reload.
4. **No new TODOs / FIXMEs** in the changed files.
   `rg "TODO|FIXME" backend/app/voice backend/app/api/voice_ws.py frontend/src/lib/api.ts frontend/src/services/halo-voice-ws.ts frontend/src/routes/settings/VoiceTab.tsx`
   returns only the pre-existing entries (if any).

---

## 9. Open questions — to confirm before sign-off

1. **Strict mode affects text-input `voice.text` path too?**
   Current spec: yes. Rationale: anything coming through the
   voice layer is gated. Typing into the cockpit in strict
   mode without a wake phrase is silently dropped. Alternative:
   text-input bypasses the gate (only real mic input is gated).
   *Default in this spec: gate text-input too. Easy to flip.*

2. **Cockpit hint when strict mode discards a turn?**
   Current spec: 2-second Sonner toast "Wake phrase not
   detected — strict mode is on". Alternative: a small inline
   hint under the mic button (no toast, less noisy). *Default
   in this spec: toast. Easy to flip.*

3. **Reset `sanitize_for_tts` state on every turn, or only on
   explicit cancel?** Current spec: every turn. Alternative:
   only on cancel. *Default in this spec: every turn. The
   state is cheap (one bool) and the safety is worth it.*

---

## 10. Sign-off

- [x] **Spec scope agreed** — strict-mode toggle + cross-sentence
      `<think>` sanitizer; no new infra, no new dependencies.
- [x] **Strict-mode default agreed** — **ON** (per user 2026-06-14).
      Breaking change for users who never opened Settings → Voice
      tab. Mitigated by §11 first-launch banner + log line.
- [x] **Strict mode affects text-input too** — **yes** (default
      per spec, not flipped by user — kept as drafted).
- [x] **Cockpit hint when discarded** — **Sonner toast** "Wake
      phrase not detected — strict mode is on" (default per spec,
      not flipped — kept as drafted).
- [x] **Sanitizer state reset on every turn** — **yes** (default
      per spec, not flipped — kept as drafted).
- [x] **Out-of-scope items confirmed** — yuesub-api integration
      (SenseVoice + fsmn-vad + Cantonese BERT corrector) +
      native always-on mic capture both deferred to Sprint 17b/17c/18.

**Signed off 2026-06-14.** Implementation plan to follow in next
message (todo list, parallel tracks, verification gates).

---

## 11. What changed for existing users (BREAKING CHANGE)

Sprint 17a flips `strict_wake_phrase` from `False` to `True` as
the default. For users who already had a config file from Sprint
16:

| User profile | Sprint 16 behavior | Sprint 17a behavior | Action required |
|---|---|---|---|
| **Never opened Settings → Voice**; no `config.toml` | Agent ran on every transcript | **Agent is silent unless a wake phrase is present** | (a) Add a wake phrase to the start of your voice turn, OR (b) open Settings → Voice, uncheck "Strict mode", save |
| **Has `config.toml` without `strict_wake_phrase` key** | Permissive (no key → default False) | **Strict (no key → default True after upgrade)** | Same as above |
| **Has `config.toml` with `strict_wake_phrase = false` explicit** | Permissive | Permissive (unchanged) | None |
| **Has `config.toml` with `strict_wake_phrase = true` explicit** | Strict (Sprint 17a doesn't exist yet) | Strict (unchanged) | None |

### Mitigations

1. **Server-side log line on first launch after upgrade:**
   ```
   INFO  voice: strict_wake_phrase=True is now the default (Sprint 17a).
         To revert to permissive: set [voice].strict_wake_phrase = false
         in ~/.gundam-halo/config.toml, or use Settings → Voice.
   ```
   Emitted once per server lifetime, only if the config file does
   not have `strict_wake_phrase` set (so it doesn't re-print on
   every restart for users who already chose one or the other).

2. **Frontend 7-day upgrade banner:** on the first 5 page loads
   after the upgrade (tracked via `localStorage["halo.voice.
   strict-banner-shown"]` + a timestamp), show a dismissable
   Sonner toast at the top of the cockpit: "New: voice turns
   need a wake phrase to invoke the agent. [Open Settings]
   [Dismiss]". After dismiss OR 7 days, never show again.

3. **README / STATUS-2026-06-XX entry:** the Sprint 17a
   completion status doc must call out the breaking change
   prominently. Users who read `docs/CHANGELOG.md` will see it.

4. **No data loss:** users who were typing commands into the
   voice text-input field without a wake phrase will see those
   commands silently dropped in strict mode. Recommend
   transitioning to the regular chat input (`/api/chat`,
   `/api/projects/<name>/chat`) which is not gated by the
   voice layer. This is mentioned in the upgrade banner.

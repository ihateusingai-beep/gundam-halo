# Feature Spec — Sprint 18: CyberWaveform cockpit mount + Settings ASR switcher

> **Status:** DRAFT — awaiting user sign-off.
> **Author:** Mavis (orchestrator).
> **Scope:** 1-1.5 working days. Two surgical, complementary changes
> that close the loop on two open follow-ups from Sprint 17a
> and 17b. **NO new dependencies, NO model downloads, NO
> backend service rewrites.**
> **Out of scope (deferred):** Tauri always-on mic capture
> (Sprint 19+), fsmn-vad-online real streaming (Sprint 19+),
> Cantonese Whisper fine-tune training (Sprint 19+).

---

## 0. Why this sprint exists

Sprint 17a spec §3 captured two audio-reactive cockpit
follow-ups. Sprint 17b's spec 17a-commit (`56e0616`) deferred
the HUD wiring, and Track E of Sprint 17b (commit `75da1b2`)
delivered the `useMicAnalyser` + `useSharedAmplitude("mic")`
plumbing. **But the CyberWaveform has no caller in the
codebase today** — it's a demo component from Sprint 16 that
sat unused. User's earlier screenshot at `/cyber-wave-demo`
showed the waveform frozen because that was a one-off dev
route, not the actual cockpit layout.

The cockpit layout today shows the avatar (CSSAvatar /
GundamAvatar) but the audio-reactive CyberWaveform isn't
mounted. **Track A** of this sprint mounts it in the cockpit
right panel, wired to the user's live mic stream — closing
the loop on the 2026-06-14 screenshot debug session.

Sprint 17b spec §4.1 said the Settings → Voice tab would
**read-only** display the current ASR backend + corrector
(Track F delivered that, commit `4d925ab`). **Track B** of
this sprint makes those fields **editable** via the Settings
tab — picking `whisper_local` vs `yuesub` from radio buttons
and persisting to `~/.gundam-halo/config.toml`. The user then
sees a "Restart required" hint (Track F already shipped the
banner — we just flip the `restart_required` field based on
the actual diff).

## 1. Goals (success criteria)

1. **CyberWaveform in the cockpit.** The right panel of the
   cockpit shows the layered sine-wave oscilloscope, and when
   the user holds the mic button the wave pulses to their
   voice in real time. When the user releases, the wave
   decays back to idle drift. **No changes to the wave
   shape, the colors, or the speed** — same component, just
   mounted and wired to the mic source.
2. **Settings → ASR backend switcher.** A radio button group
   in the Settings → Voice tab lets the user pick
   `whisper_local` (Sprint 16, default) vs `yuesub` (Sprint
   17b, Cantonese). Saving the form writes to
   `~/.gundam-halo/config.toml [voice.asr] backend = ...` and
   flips the `restart_required` field on the next GET.
3. **Settings → Corrector switcher.** A second radio group
   in the same tab picks `bert` (default), `opencc`, or
   `none`. The `bert` choice requires the BERT model to be
   downloaded; the tab shows a hint if it's missing.
4. **No regressions.** Sprint 16/17a/17b flows keep working
   for users who don't change anything. All 80 backend
   tests + 52 frontend tests still pass.

## 2. Out of scope (deferred)

- **Tauri always-on mic capture** (Sprint 19+). The mic
  capture remains push-to-talk.
- **fsmn-vad-online real streaming** — `FsmnVAD` continues
  to use RMS-energy as the level source. A follow-up sprint
  will swap to per-frame speech probability from
  `Fsmn_vad_online` (per spec 17b §5.1).
- **Cantonese Whisper fine-tune** — separate `train` extra,
  not a runtime dependency.
- **Cockpit auto-restart on backend crash** — separate
  reliability sprint.

## 3. User-facing behavior

### 3.1 Cockpit HUD (Track A)

The cockpit's right panel today shows the avatar (CSSAvatar /
GundamAvatar), a "Voice — Ready, hold to talk" panel, and a
"Wake phrase hint". Sprint 18 inserts the CyberWaveform
**above the avatar** at a fixed height of 80px (a compact
view; the cyber-wave-demo screenshot showed 160px, but the
cockpit's right column is narrower). The new layout:

```
┌─ right panel ──────────────┐
│ ┌─ CyberWaveform 80px ────┐ │  ← new
│ │ ~~~~~~~~~~~~~~~~~~~~~~~ │ │
│ └─────────────────────────┘ │
│ ┌─ Avatar (160px) ───────┐ │
│ │       (avatar)         │ │
│ └─────────────────────────┘ │
│ ┌─ Voice panel ──────────┐ │
│ │   🎤 hold to talk       │ │
│ └─────────────────────────┘ │
│ ┌─ Wake phrase hint ─────┐ │
│ └─────────────────────────┘ │
└─────────────────────────────┘
```

When the user holds the mic button, the wave pulses in
sync with their voice (Sprint 17b's `useSharedAmplitude("mic")`).
When they release, the wave decays to idle drift over ~1 second.

If the user hasn't granted mic permission (browser blocks
`getUserMedia`), the wave stays in idle drift mode — same
as before, no error toast. The cockpit's existing "denied"
state in VoicePanel handles the user-facing error.

### 3.2 Settings → ASR backend switcher (Track B)

The current `Wake-phrase gate (Sprint 17a)` section in
`/settings/voice` grows two new sections below it. Both
have a Save button that triggers one `setVoiceConfig` PUT.

**Section: ASR engine (Sprint 18)**
```
┌─ ASR engine (Sprint 18) ────────────────────────────┐
│ ◯ whisper_local — openai-whisper (English / Mandarin)│
│ ● yuesub — SenseVoiceSmall + fsmn-vad (Cantonese)    │
│                                                     │
│  Selected: yuesub. Restart the backend to take       │
│  effect: pkill -f 'uvicorn app.main:app' && ...     │
└─────────────────────────────────────────────────────┘
```

**Section: Corrector (Sprint 18)**
```
┌─ Corrector (Sprint 18) ──────────────────────────────┐
│ ◯ none   — raw ASR text                               │
│ ◯ opencc — OpenCC + regex rules (fast, <5ms)          │
│ ● bert   — OpenCC + BERT masked-LM (slow, 300-500ms)  │
│                                                      │
│  Note: bert requires hon9kon9ize/bert-large-cantonese. │
│  If it's missing, see scripts/setup-yuesub-models.sh.   │
└──────────────────────────────────────────────────────┘
```

Both sections have a single **Save** button (matching the
existing wake-phrase save). On save:

- `wake_phrases` + `strict_wake_phrase` + `asr.backend` +
  `asr.corrector` are sent in **one** PUT to `/voice/config`
  (the existing endpoint).
- The backend persists all four to `config.toml`, updates
  the in-memory config, and returns `{restart_required:
  true}` (because changing `asr.backend` or `asr.corrector`
  requires a backend restart).
- The dashboard shows the **"Restart required" banner**
  (Track F already shipped the rendering; we just flip the
  flag based on whether `asr.backend` or `asr.corrector`
  changed).

## 4. Architecture

### 4.1 Track A — CyberWaveform mount

The cockpit layout (`components/layout/CockpitLayout.tsx`)
already has a right column. We add a `<CyberWaveform
source={micActive ? "mic" : "idle"} stream={micStream} />`
above the avatar. `micStream` and `micActive` come from
`useVoiceInput({...})` — but CockpitLayout doesn't own the
mic today (VoicePanel does). We hoist the mic state from
VoicePanel to CockpitLayout so both can subscribe.

```tsx
// CockpitLayout.tsx
const mic = useVoiceInput({ onFrame: voiceSendAudio });
const [micActive, setMicActive] = useState(false);
// pass mic + setMicActive to VoicePanel
// pass mic.stream + micActive to CyberWaveform

<CyberWaveform
  source={micActive ? "mic" : "idle"}
  stream={mic.stream}
  height={80}
  layers={4}
  amplitudeScale={1.2}
/>
```

Why hoist to CockpitLayout (instead of prop-drilling the
stream from VoicePanel to the waveform): the cockpit owns
the right column layout, and the user-experience is "I see
the wave + the avatar + the mic button all on the right
side". Co-locating the state in the parent makes the data
flow obvious.

### 4.2 Track B — Settings ASR switcher

`api.setVoiceConfig({wake_phrases, strict_wake_phrase, asr_backend, asr_corrector})`
already accepts the new fields (Sprint 17b Track F + this
sprint's tightening of the backend PUT). The Settings tab
adds the two new radio groups and dispatches them in the
same payload as the wake-phrase save.

Backend `/voice/config PUT`:

- Read all four fields from the payload
- Validate `wake_phrases` + `strict_wake_phrase` (existing)
- Validate `asr_backend` is one of `whisper_local | yuesub`
  (NEW)
- Validate `asr_corrector` is one of `bert | opencc | none` (NEW)
- Compare old vs new for `asr_backend` and `asr_corrector`:
  - If changed → set `restart_required = True` in the
    response
  - Otherwise → set `restart_required = False`
- Persist to `config.toml` (the existing toml-edit logic
  already handles arbitrary keys; we just add the two new
  lines)
- Return the same shape Track F shipped, plus the new
  `restart_required` flag

### 4.3 Restart-required UX

The "Restart required" banner that Track F shipped is
already in place. The diff for Sprint 18 is the **data
flow** that flips its `restart_required` field based on
actual changes:

1. User changes `asr.backend` in the Settings tab.
2. Save dispatches `setVoiceConfig({...asr_backend: "yuesub"})`.
3. Backend validates, persists, computes the diff
   (`asr.backend` was `whisper_local`, now `yuesub` →
   `restart_required = true`).
4. PUT response includes `restart_required: true`.
5. Frontend caches the response in `VoiceConfig` state;
   the existing banner in VoiceTab reads `restart_required`
   and shows the warning.

A subsequent PUT that **doesn't** change asr fields flips
`restart_required` back to `false`.

## 5. File-by-file change set

| Path | Change | LoC est. |
|---|---|---|
| `frontend/src/components/layout/CockpitLayout.tsx` | Hoist `useVoiceInput` to here; render `<CyberWaveform source stream height layers amplitudeScale />` above the avatar | +25 / -10 |
| `frontend/src/components/gundam/VoicePanel.tsx` | Stop owning `useVoiceInput`; accept `mic` + `setMicActive` as props from CockpitLayout | +5 / -30 |
| `frontend/src/services/halo-voice-ws.ts` | No change (Track E already shipped the WS event) | 0 / 0 |
| `frontend/src/routes/settings/VoiceTab.tsx` | Add 2 new radio sections (ASR engine + Corrector); dispatch all 4 fields in one PUT; show "Restart required" banner when `restart_required` flips true | +120 / -5 |
| `backend/app/api/voice_ws.py` | `put_voice_config` accepts `asr_backend` + `asr_corrector`; validates; computes diff vs current to set `restart_required`; persists to config.toml | +60 / -10 |
| `backend/app/core/config.py` | No change (Track B already added `corrector` field; `backend` was always there) | 0 / 0 |
| `frontend/src/lib/api.ts` | `setVoiceConfig` payload type gains `asr_backend?` + `asr_corrector?`; `getVoiceConfig` return type already updated by Track F | +5 / 0 |
| `frontend/src/hooks/__tests__/CockpitLayout.test.tsx` | NEW. Renders the cockpit, asserts CyberWaveform is present with the right props, and that the source flips to "mic" when the user holds the button | +80 / 0 |
| `backend/tests/voice/test_voice_config.py` | NEW. PUT /voice/config with asr_backend + corrector changes; verifies config.toml updated + restart_required flag set; verifies unknown asr_backend rejected | +150 / 0 |
| `docs/FEATURE-SPEC-SPRINT18.md` | NEW. This file. | +180 / 0 |
| `docs/CHANGELOG.md` | Add Sprint 18 entry under [Unreleased] | +30 / 0 |

**Total**: ~660 LoC. Backend ~210 + Frontend ~225 + tests ~230 +
docs ~210. ~1.5 days wall clock.

## 6. Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **Mic state hoist breaks VoicePanel's hold-to-talk button** | Medium | High | The `useVoiceInput` contract is unchanged; we just move ownership from VoicePanel to CockpitLayout. The button + state values are passed down as props. Existing VoicePanel tests (none today) would still need to be added in a follow-up, but Sprint 18 is the first time VoicePanel is tested. |
| **CyberWaveform doesn't render correctly at 80px height** (the dev demo was 160px) | Medium | Low | The component's `height` prop is already parameterized (Sprint 16). Smoke test: open the cockpit, hold the mic, observe the wave. If the layout breaks, bump to 100px. |
| **User changes asr_backend but doesn't realize restart is required** | Medium | High | The "Restart required" banner is the explicit signal. The Save toast also says "Restart required for the new ASR engine to load." We also write a one-time server log line on first detected mismatch. |
| **CockpitLayout's right column overflows when CyberWaveform is added** | Low | Medium | The right column is grid-flex; we add `flex-shrink-0` on the CyberWaveform wrapper. |
| **Backend rejects an unknown asr_backend value** | Low | Low | The factory raises `ValueError` (Track B); the PUT endpoint returns 400 with a clear message. |
| **CyberWaveform's idle drift runs even when the user never opens the cockpit** | Low | Low | The global idle-drift loop is already there (Sprint 16); one extra subscriber doesn't matter. |
| **The existing wake-phrase save breaks when we add asr fields to the payload** | Low | High | Track F's existing voice_ws tests cover the wake-phrase save; we'll run them and add coverage for the asr fields. |

## 7. Acceptance tests

1. **Backend pytest**: `tests/voice/test_voice_config.py` —
   PUT with asr_backend change sets restart_required=True;
   PUT with no asr change sets restart_required=False; PUT
   with unknown asr_backend returns 400; corrector validation
   similar.
2. **Frontend vitest**: `CockpitLayout.test.tsx` — renders
   the cockpit with the CyberWaveform present; mic-active
   state flips the source prop to "mic".
3. **Existing tests still pass**:
   - Backend: 80/82 (2 skipped, same as Sprint 17b)
   - Frontend: 52 + new tests
4. **Manual smoke checklist**:
   - [ ] Open the cockpit at `/`. See the layered sine
     wave in the right panel above the avatar. Wave is in
     idle drift mode.
   - [ ] Hold the mic button. The wave pulses in time
     with your voice. Release. Wave decays to idle drift
     over ~1 second.
   - [ ] Open Settings → Voice. See the new "ASR engine"
     and "Corrector" sections. Pick `whisper_local`, save.
   - [ ] The "Restart required" banner appears. Restart
     the backend. The banner disappears on next visit.
   - [ ] The cockpit still works (no regression).

## 8. Sign-off

- [ ] **Track A scope agreed** — mount CyberWaveform in
      CockpitLayout, height=80, layers=4, mic-driven
- [ ] **Track B scope agreed** — Settings tab adds ASR
      engine + Corrector radio groups; one Save dispatches
      all 4 fields; restart_required banner flips based on
      diff
- [ ] **Out-of-scope items confirmed** — Tauri always-on,
      fsmn-vad-online real streaming, Whisper fine-tune all
      deferred to Sprint 19+

**Sign-off → todo list breaks into 3 tracks:**
- Track A: frontend cockpit mount (4 hours)
- Track B: backend + frontend ASR switcher (6 hours)
- Track C: tests, lint, commit, CHANGELOG (2 hours)

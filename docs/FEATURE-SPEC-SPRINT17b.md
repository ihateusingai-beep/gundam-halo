# Feature Spec — Sprint 17b: Cantonese ASR (SenseVoice + fsmn-vad) + BERT corrector + Audio-Reactive HUD

> **Status:** SIGNED OFF (design decisions), 2026-06-14.
> **Author:** Mavis (orchestrator).
> **Scope:** 4-6 working days. **Larger than 17a** due to D3 scope
> flip (BERT corrector enabled in this sprint, was deferred in 17a).
> **Out of scope (deferred):** Tauri-side always-on mic capture
> (Sprint 18+), Cantonese Whisper fine-tune (training pipeline
> track, not runtime).

## 0. Design decisions (signed off 2026-06-14)

| # | Question | Decision | Notes |
|---|---|---|---|
| **D1** | VAD strategy | **C — dual VAD** (silero + fsmn-vad-online in parallel) | silero continues to fire `vad.speech_start/end` for utterance boundary. fsmn-vad runs in parallel and broadcasts per-chunk level for the audio-reactive HUD. |
| **D2** | yuesub-api integration | **C — Hybrid lift (ASR only)** | Port `OnnxTranscriber`'s model-load + `transcribe()` + `_load_tokenizer` + `_setup_aligner` into `app/voice/asr/yuesub.py`. The yuesub-api repo stays as dev reference. We do NOT depend on its Flask/Gradio surface. |
| **D3** | Cantonese BERT corrector | **B — Enable in Phase 1** *(SCOPE FLIP from 17a §3)* | Download `hon9kon9ize/bert-large-cantonese` (~1.4GB) via `download_models.py --with-bert`, symlink into `~/.gundam-halo/models/`, wire `Corrector(corrector="bert")` post-ASR. Adds ~300-500ms latency per sentence; mitigated by sentence-streamed delivery (per-chunk corrector calls, not whole-utterance). |
| **D4** | Audio-reactive HUD source | **A — Client-side AnalyserNode** | `useVoiceInput` computes RMS from `AnalyserNode.getByteTimeDomainData()`, pushes to `useSharedAmplitude` via a new setter. Hook signature gains an `amplitudeSource` prop (default = idle drift, override = real mic). WS contract unchanged. |
| **D5** | Model storage | **A — Symlink** | `mkdir -p ~/.gundam-halo/models` then `ln -sf ~/workspace/yuesub-api/models/iic ~/.gundam-halo/models/iic` and `ln -sf ~/workspace/yuesub-api/models/denoiser.onnx ~/.gundam-halo/models/denoiser.onnx`. Single source of truth in yuesub-api repo. |

---

## 1. Background & motivation

Sprint 16 shipped text-level wake-phrase detection (Unicorn/NTD/...)
on top of `whisper_local` ASR. Sprint 17a added strict-mode gating
and a cross-sentence `<think>` sanitizer. Two follow-ups remain
from 17a's deferred list, plus one UX gap from the 17a screenshot
debug session:

1. **Cantonese ASR is the headline use case.** `whisper_local`
   base model works but has high WER on conversational Cantonese
   with code-switching. `SenseVoiceSmall` (FunAudioLLM) is a
   234M-param ONNX ASR model fine-tuned on Cantonese + Mandarin
   + English that runs in real-time on Apple Silicon. yuesub-api
   already wraps it with `fsmn-vad` for streaming segment
   detection and `hon9kon9ize/bert-large-cantonese` for
   post-ASR spelling correction. Sprint 17b lifts this stack
   into Gundam Halo.
2. **The cockpit HUD is fake.** As confirmed 2026-06-14
   (`docs/FEATURE-SPEC-SPRINT17a.md` §3 follow-up): the
   `CyberWaveform` / `GundamAvatar` "pulse" visualizer in
   `useSharedAmplitude` is a deterministic idle-breathing
   placeholder. Sprint 17b wires the real mic stream so the
   waveform actually follows the user's voice.
3. **BERT corrector scope flip.** Sprint 17a §3 deferred
   the corrector to 17b/17c. User sign-off 2026-06-14 brought
   it forward to 17b to avoid a half-shipped yuesub stack.

---

## 2. Goals (success criteria)

1. **yuesub ASR backend** selectable via
   `voice.asr.backend = "yuesub"` in `config.toml`. When
   selected, voice turns are transcribed by SenseVoiceSmall
   on Apple Silicon (MPS) in real-time, with `fsmn-vad`
   running in parallel and feeding per-chunk level to the
   cockpit HUD.
2. **Cantonese BERT corrector** applied to every SenseVoice
   transcript before it reaches the agent. OpenCC t2s is
   the fallback corrector if BERT download is skipped or
   the user explicitly selects `corrector = "opencc"` in
   config.
3. **Strict-wake + voice-end → transcript path** unchanged.
   The wake phrase detector still runs on the post-corrector
   text (corrector is high-confidence on common misspellings
   like "俾" → "畀", "系" → "係", so it should run BEFORE
   wake detection to avoid false negatives).
4. **Audio-reactive cockpit** drives the existing
   `CyberWaveform` and any future HUD element from the
   browser's `AnalyserNode` when the voice WS is connected
   and the mic is open. Falls back to the current idle-
   breathing animation when the WS is disconnected or the
   mic is muted.
5. **No regression on Sprint 16/17a flows.** All existing
   tests pass. whisper_local remains the default backend
   for users who don't set `voice.asr.backend = "yuesub"`.

---

## 3. Out of scope (deferred)

- **Tauri-side always-on mic capture** — Sprint 18+. Even
  with yuesub-api, the v1 push-to-talk flow stays. Always-
  on requires Swift binding work in the Tauri shell and
  carries a "mic permission while the app is in the
  background" UX cost. The audio-reactive HUD works in
  push-to-talk mode (mic only active while the user
  holds the button), so the always-on is not a blocker
  for this sprint's UX win.
- **Cantonese Whisper fine-tune** — separate "train" extra
  in `pyproject.toml`. Not a runtime dependency; orthogonal
  to the ASR-backend swap.
- **Work-tab classifier**, **bidirectional Mail sync**,
  synthetic input — unchanged from prior sprint scope.

---

## 4. User-facing behavior

### 4.1 New ASR backend choice

```toml
# ~/.gundam-halo/config.toml — [voice.asr] section

[voice.asr]
backend = "yuesub"          # NEW: "yuesub" (Sprint 17b) or "whisper_local" (Sprint 16, default)
language = "auto"           # yuesub only: "yue" | "zh" | "en" | "auto"
corrector = "bert"          # yuesub only: "opencc" | "bert" | "none"
device = "auto"             # "auto" | "mps" | "cpu" (yuesub only; whisper_local uses its own)
```

Default remains `backend = "whisper_local"`. Switching is a
config edit + backend restart (yuesub models are 2GB+ and
should not be reloaded on every config PUT). The
`/voice/config` GET endpoint surfaces the current backend so
the Settings → Voice tab can show a "restart required"
banner when the user changes `asr.backend`.

### 4.2 Audio-reactive cockpit (D4)

Behavior change for the user:

- **Before Sprint 17b**: CyberWaveform and GundamAvatar
  pulse on a fixed 6.5s + 9.2s sine cycle with a 7-12s
  "burst" envelope. Feels alive but is fully decoupled
  from the mic.
- **After Sprint 17b**: when the user holds the mic
  button (or types `voice.text` in strict mode with a
  wake phrase), the AnalyserNode in the browser computes
  RMS from the local mic stream at 20Hz, and the
  `useSharedAmplitude` hook reflects that. The waveform
  and avatar pulse in time with the user's voice. When
  the WS is disconnected or the mic is muted, the hook
  falls back to the existing idle drift.

**No settings change required** — this is automatic and
always on. The user does not need to opt in.

### 4.3 Cantonese corrector (D3)

When `corrector = "bert"` and the yuesub backend is
selected, the corrector runs **per ASR segment**, not per
whole utterance. A segment is typically 1-2 sentences, so
the 300-500ms latency hit is absorbed by the sentence-
streamed TTS path. The corrector fixes common SenseVoice
mistakes:

| ASR output | Corrected | Reason |
|---|---|---|
| `俾我` | `畀我` | OpenCC + regex rule |
| `系邊個` | `係邊個` | OpenCC + regex rule |
| `噶` | `㗎` | OpenCC + regex rule |
| 雜亂粵拼 `ge3` 誤識 | 修為 `嘅` | BERT perplexity (high-confidence) |

The corrector is invisible to the user — its output is
the final `asr.result` text. The user can disable it by
setting `corrector = "opencc"` (faster, regex-only) or
`corrector = "none"` (raw ASR output).

---

## 5. Architecture

### 5.1 Backend — yuesub ASR lift

```
                            ┌──────────────────────┐
   mic PCM frames (16k) ───▶│  VAD Pipeline         │
                            │  ├─ silero_vad        │──▶ speech_start / speech_end
                            │  └─ fsmn_vad_online   │──▶ per-chunk level → WS broadcast
                            └──────────┬───────────┘
                                       │ buffered utterance bytes
                                       ▼
                            ┌──────────────────────┐
                            │  ASR (yuesub)         │
                            │  ├─ SenseVoiceSmall   │──▶ raw transcript
                            │  └─ corrector         │──▶ corrected transcript
                            └──────────┬───────────┘
                                       │ corrected text
                                       ▼
                            ┌──────────────────────┐
                            │  detect_wake_phrase   │──▶ strict-mode gate (17a)
                            └──────────┬───────────┘
                                       ▼
                            ┌──────────────────────┐
                            │  agent + TTS         │
                            └──────────────────────┘
```

**Key invariants:**

- **silero is the source of truth for utterance boundary.**
  `fsmn-vad-online` runs in parallel and emits per-chunk
  level for HUD; it does NOT trigger the ASR path. This
  preserves Sprint 16's existing VAD contract.
- **Corrector runs before wake detection.** `俾我睇下
  unicorn 嘅 app` should still match `unicorn` after
  correction. Running the corrector after wake detection
  would risk false negatives on `"ni3"` → `"你"`.
- **fsmn-vad-online is per-frame**, not per-utterance.
  We call it inside `pipeline.process_frame()` for every
  WebSocket audio chunk, capturing the model's
  per-chunk speech-probability score. This score is the
  audio-reactive HUD's source-of-truth amplitude, even
  before the corrector + agent kick in.

### 5.2 File layout

```
backend/app/voice/asr/
├── asr_factory.py            (MODIFIED — add "yuesub" branch)
├── asr_interface.py          (UNCHANGED)
├── whisper_local.py          (UNCHANGED)
└── yuesub.py                 (NEW — lifted OnnxTranscriber + corrector)

backend/app/voice/vad/
├── vad_factory.py            (UNCHANGED — silero stays default)
├── silero_vad.py             (UNCHANGED)
└── fsmn_vad.py               (NEW — fsmn-vad-online wrapper for per-chunk level)

backend/app/voice/pipeline.py (MODIFIED — call fsmn_vad per frame, broadcast level)
backend/app/voice/corrector/
├── __init__.py               (NEW)
└── corrector.py              (NEW — lifted Corrector + BertModel, async wrapper)

backend/app/api/voice_ws.py   (MODIFIED — broadcast vad.audio_level frames)
backend/app/core/config.py    (MODIFIED — add corrector + device to VoiceASRConfig)

frontend/src/hooks/
├── use-shared-amplitude.ts   (MODIFIED — gain amplitudeSource prop)
└── use-mic-analyser.ts       (NEW — AnalyserNode RMS at 20Hz)

frontend/src/services/
└── halo-voice-ws.ts          (MODIFIED — type: VadAudioLevelEvent + handler for fsmn level; client-side mic level takes priority in useSharedAmplitude)

frontend/src/routes/settings/
└── VoiceTab.tsx              (MODIFIED — show current ASR backend + "restart required" banner)
```

### 5.3 Backend config schema additions

```toml
# ~/.gundam-halo/config.toml — [voice.asr] section

[voice.asr]
# v1: "whisper_local" (Sprint 16). Sprint 17b: "yuesub" for SenseVoice + fsmn-vad.
backend = "whisper_local"

# yuesub only:
language = "auto"        # "auto" | "yue" | "zh" | "en"
corrector = "bert"        # "bert" | "opencc" | "none"
device = "auto"           # "auto" (mps on mac) | "mps" | "cpu"

# whisper_local (unchanged):
model_size = "base"
model_path = ""
compute_type = "int8"
```

New `VoiceASRConfig` fields:
```python
language: str = "auto"          # yuesub only
corrector: str = "bert"         # yuesub only
device: str = "auto"            # yuesub only
```

`_load_voice_config()` reads them with `d.get(key, defaults)`.

### 5.4 WS frame additions

| Frame | Type | Direction | Payload |
|---|---|---|---|
| `vad.audio_level` | NEW | server → client | `{session_id, level: number}` — `level` is the per-chunk fsmn-vad speech probability (0..1), broadcast every ~50ms while the WS is active. Optional; the cockpit falls back to client-side AnalyserNode RMS if the server doesn't send it. |

The `vad.audio_level` frame is **rate-limited** on the server
(no more than one frame per 50ms) to avoid swamping the
WebSocket. The frontend (per D4) is the primary source of
audio level; server-side is a fallback for environments
where the client mic RMS isn't available (e.g. the Tauri
shell when not in a browser tab).

### 5.5 Frontend `useSharedAmplitude` signature change

```typescript
// before (Sprint 16/17a)
function useSharedAmplitude(): number

// after (Sprint 17b)
function useSharedAmplitude(source?: "idle" | "mic"): number
```

When `source === "mic"`, the hook subscribes to the
browser's `AnalyserNode` (via `useMicAnalyser`) and returns
the real mic RMS. When `source === "idle"` or undefined,
the hook returns the existing idle-drift value.

The cockpit's `VoicePanel` flips the source to `"mic"` when
the user holds the mic button (using the same lifecycle
state the panel already tracks), and back to `"idle"` on
release. No new state in the cockpit; the hook signature
change is internal to the HUD components.

### 5.6 Symlink setup script

```bash
# scripts/setup-yuesub-models.sh — idempotent, safe to re-run.
# Sets up the symlinks from Gundam Halo's expected model dir
# to the yuesub-api repo's model dir.

set -euo pipefail

HALO_MODELS="$HOME/.gundam-halo/models"
YUESUB_MODELS="$HOME/workspace/yuesub-api/models"

mkdir -p "$HALO_MODELS"

# iic/ — SenseVoice + fsmn-vad ONNX bundles
if [ ! -e "$HALO_MODELS/iic" ]; then
  ln -s "$YUESUB_MODELS/iic" "$HALO_MODELS/iic"
  echo "linked iic/"
fi

# denoiser.onnx — file, not a directory
if [ ! -e "$HALO_MODELS/denoiser.onnx" ]; then
  ln -s "$YUESUB_MODELS/denoiser.onnx" "$HALO_MODELS/denoiser.onnx"
  echo "linked denoiser.onnx"
fi

# hon9kon9ize/ — BERT corrector (only if user enabled D3-B)
if [ ! -e "$HALO_MODELS/hon9kon9ize" ]; then
  if [ -d "$YUESUB_MODELS/hon9kon9ize" ]; then
    ln -s "$YUESUB_MODELS/hon9kon9ize" "$HALO_MODELS/hon9kon9ize"
    echo "linked hon9kon9ize/"
  else
    echo "BERT corrector not downloaded yet. Run:"
    echo "  cd $HOME/workspace/yuesub-api && python download_models.py --with-bert"
    echo "then re-run this script."
  fi
fi

echo "yuesub models ready at $HALO_MODELS"
```

The script is **documented in the README** but NOT
auto-run by the backend. Users have to opt in by
running it once. This avoids surprising existing
whisper_local users with a 2GB+ download.

---

## 6. File-by-file change set

| Path | Change | LoC est. |
|---|---|---|
| `backend/app/voice/asr/yuesub.py` | NEW. Lifted `OnnxTranscriber` + corrector + BertModel + tokenizer + aligner. Adds `transcribe(audio: bytes) → str` matching the `ASRInterface` contract. Handles model paths from config; falls back to yuesub-api repo dir if symlink not set up. | +350 / 0 |
| `backend/app/voice/corrector/corrector.py` | NEW. Async wrapper around yuesub-api's `Corrector`. The corrector is CPU-bound (OpenCC + regex) or GPU/CPU-bound (BERT) so we run it in `asyncio.to_thread` to avoid blocking the event loop. | +120 / 0 |
| `backend/app/voice/corrector/__init__.py` | NEW. `from .corrector import Corrector`. | +3 / 0 |
| `backend/app/voice/vad/fsmn_vad.py` | NEW. Wrapper around `Fsmn_vad_online`. Per-frame `process_chunk(pcm_bytes, sr=16000) → (speech_prob: float, is_segment_end: bool)`. The `is_segment_end` flag is for HUD use only; silero is still the utterance boundary. | +90 / 0 |
| `backend/app/voice/pipeline.py` | MODIFIED. `process_frame()` also calls `fsmn_vad.process_chunk()` and emits the per-chunk level. Tracks `current_session_id` so the broadcast can include it. | +35 / -5 |
| `backend/app/voice/asr/asr_factory.py` | MODIFIED. Add `"yuesub"` branch that returns `YuesubASR(corrector, device, language)`. | +30 / 0 |
| `backend/app/voice/asr/asr_interface.py` | UNCHANGED. | 0 / 0 |
| `backend/app/api/voice_ws.py` | MODIFIED. Subscribe to the per-chunk level from the pipeline and broadcast `vad.audio_level` frames (rate-limited 50ms). Add the new event to `VoiceHelloEvent` so the client knows if the server supports it. | +40 / 0 |
| `backend/app/core/config.py` | MODIFIED. `VoiceASRConfig` gains `language`, `corrector`, `device` fields. `_load_voice_config()` reads them. | +15 / 0 |
| `backend/pyproject.toml` | MODIFIED. New optional group `voice-yuesub` with `funasr_onnx`, `librosa`, `resampy`, `transformers[onnx]`, `opencc`, `tqdm`. Already-installed: `onnxruntime`, `torch`, `torchaudio`. Total new disk: ~600MB (transformers + opencc + librosa); funasr_onnx is just a Python wrapper. | +10 / 0 |
| `scripts/setup-yuesub-models.sh` | NEW. Idempotent symlink script (see §5.6). | +40 / 0 |
| `frontend/src/hooks/use-shared-amplitude.ts` | MODIFIED. `useSharedAmplitude(source?: "idle" \| "mic")` — when `source === "mic"`, the hook returns the value from `useMicAnalyser()`. Idle drift stays as the default. | +30 / -10 |
| `frontend/src/hooks/use-mic-analyser.ts` | NEW. Creates an `AudioContext` + `AnalyserNode` from the existing mic stream (the same one `useVoiceInput` already captures), polls `getByteTimeDomainData()` at 20Hz, returns RMS. Cleans up on unmount. | +80 / 0 |
| `frontend/src/services/halo-voice-ws.ts` | MODIFIED. Add `VadAudioLevelEvent` type. Add a handler that listens for `vad.audio_level` frames and forwards to `useSharedAmplitude` (used as a fallback when the client-side AnalyserNode is not available). | +20 / 0 |
| `frontend/src/routes/settings/VoiceTab.tsx` | MODIFIED. Add a "Current ASR backend" row to the "Voice WebSocket" section. When the user changes `asr.backend` and saves, show a "Restart required" toast (we don't auto-restart the backend from the frontend). | +25 / 0 |
| `backend/tests/voice/test_yuesub_asr.py` | NEW. 6 tests: factory returns correct subclass, transcribe returns string, corrector is applied, corrector is "none" passthrough, fsmn_vad per-chunk level is in [0,1], yuesub models missing error path. | +180 / 0 |
| `backend/tests/voice/test_fsmn_vad.py` | NEW. 3 tests: silence chunk returns ~0, speech chunk returns ~1, segment-end flag fires on long speech. | +90 / 0 |
| `backend/tests/voice/test_audio_level_broadcast.py` | NEW. 2 tests: WS sends `vad.audio_level` frames while a turn is active, frames are rate-limited to one per 50ms. | +80 / 0 |
| `frontend/src/hooks/__tests__/use-shared-amplitude.test.ts` | NEW. 3 tests: idle drift default, mic source returns RMS, source flip is reactive. | +90 / 0 |
| `docs/FEATURE-SPEC-SPRINT17b.md` | NEW. This file. | +498 / 0 |
| `docs/CHANGELOG.md` | MODIFIED. Sprint 17b entry. | +25 / 0 |
| `README.md` | MODIFIED. yuesub setup section. | +40 / 0 |

**Total backend:** +770 / -5. **Total frontend:** +245 / -10. **Docs:** +563 / 0.
**Total LoC:** ~1,560.

---

## 7. Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **funasr_onnx install fails on macOS arm64** because of `funasr` Python package transitively requiring CUDA | High | High | Pin `funasr_onnx==1.1.13` (latest stable that doesn't pull CUDA), document the install command separately, and write a `--check-yuesub-deps` CLI subcommand. |
| **Model load takes >5s on first startup** | High | Medium | Lazy-load yuesub on first ASR call, not at backend startup. The first turn pays a one-time cost; subsequent turns are fast. Log the load time. |
| **fsmn-vad per-frame call >10ms latency** | Medium | High | fsmn-vad accepts batched frames; we batch up to 4 frames (1s of audio) before calling. The 20Hz broadcast rate is preserved. |
| **BERT corrector 300-500ms latency per sentence** | High | Medium | The corrector is sentence-streamed (one call per ASR segment, not per utterance). TTS starts on the first corrected sentence while later sentences are still being corrected. User-perceived latency is unchanged. |
| **Cantonese BERT model is 1.4GB+ download** | High | Low | Symlink from yuesub-api repo. Document `download_models.py --with-bert` in the setup script. User can opt for `corrector = "opencc"` to skip. |
| **WS frame flood: vad.audio_level overwhelms the connection** | Medium | Medium | Rate-limit to 1 frame per 50ms (20Hz) on the server. Add a `vad.audio_level.enabled = false` config to disable for users who don't want it. |
| **whisper_local regression** when yuesub backend is selected | Low | High | whisper_local path is unchanged. yuesub is opt-in. Tests cover both paths independently. |
| **Strict-mode (Sprint 17a) interacts badly with corrector's text mutation** | Medium | High | Corrector runs BEFORE wake detection (see §5.1 invariant). Tests cover corrector-then-wake sequence. If corrector ever changes the leading character class in a way that breaks wake matching, we re-evaluate. |
| **Symlink fails (e.g. user has `~/.gundam-halo/models/iic` as a real dir)** | Low | Low | The setup script is idempotent and checks `[ ! -e ]` before linking. README documents how to manually remove a conflicting dir. |
| **CPU bound corrector blocks event loop** | Low | High | `Corrector.correct()` is wrapped in `asyncio.to_thread()`. Tests assert it doesn't block the loop. |
| **User accidentally selects yuesub without running the model download script** | Medium | Medium | `YuesubASR.__init__` checks for the SenseVoiceSmall dir at the configured path and raises a clear `ASRError` with the exact shell command to run. |

---

## 8. Acceptance tests

A change is "done" when:

1. **Unit tests pass:**
   - `cd backend && uv run pytest tests/voice/ -q` — 38 existing
     + 11 new tests all green. (26 sanitizer + 12 voice_ws
     + 6 yuesub_asr + 3 fsmn_vad + 2 audio_level_broadcast
     + 3 use-shared-amplitude frontend)
   - `cd frontend && pnpm run test` — 47 existing + 3 new
     = 50 tests pass.
2. **Backend builds + lints clean:** `cd backend && uv run
   ruff check app/ tests/` returns 0 errors.
3. **Frontend builds clean:** `pnpm run build` produces
   `dist/` without errors.
4. **Model setup script idempotent:** `bash
   scripts/setup-yuesub-models.sh` succeeds when run twice
   in a row (the second run is a no-op).
5. **Manual smoke checklist:**
   - [ ] `cd backend && uv sync --extra voice --extra
     voice-yuesub` installs without errors on macOS
     arm64.
   - [ ] `bash scripts/setup-yuesub-models.sh` creates the
     symlinks; `ls -la ~/.gundam-halo/models` shows them.
   - [ ] Set `voice.asr.backend = "yuesub"` in
     `~/.gundam-halo/config.toml`. Restart backend. Log
       shows `Creating ASR engine: backend=yuesub` and
       `Loading SenseVoiceSmall on device=mps`.
   - [ ] Push-to-talk "高達, 香港天氣點" in strict mode
       (default) → ASR returns "高達, 香港天氣點" or
       similar; corrector runs without breaking the wake
       phrase; agent replies with the weather.
   - [ ] Hold the mic button and speak normally → the
       CyberWaveform in the cockpit visibly follows the
       voice. Release the button → the waveform decays
       back to idle drift.
   - [ ] Switch `corrector = "opencc"` in config and
       restart → the corrector no longer hits BERT (faster
       startup, smaller log).
   - [ ] Switch `voice.asr.backend = "whisper_local"` and
       restart → existing Sprint 16/17a flow works
       unchanged.
   - [ ] Settings → Voice tab shows the current ASR
       backend. Changing `backend` and saving shows a
       "Restart required" toast.
6. **No new TODOs / FIXMEs** in the changed files.
   `rg "TODO|FIXME" backend/app/voice/asr/yuesub.py backend/app/voice/corrector/ backend/app/voice/vad/fsmn_vad.py backend/app/api/voice_ws.py frontend/src/hooks/use-shared-amplitude.ts frontend/src/hooks/use-mic-analyser.ts frontend/src/routes/settings/VoiceTab.tsx`
   returns only pre-existing entries (if any).

---

## 9. Open questions — to confirm before sign-off

1. **Symlink location for BERT model:** the yuesub-api
   `download_models.py --with-bert` puts the model at
   `~/workspace/yuesub-api/models/hon9kon9ize/...`. Confirm
   the symlink target. *(This is settled by the D5-A script
   in §5.6 — listed for completeness.)*
2. **First-turn latency budget:** yuesub's SenseVoice takes
   ~800ms to warm up on first transcribe call. Do we
   (a) accept the first-turn latency hit, or (b) run a
   warmup `transcribe(1s-of-silence)` at backend startup?
   *(Default: (a) lazy load. If user complains, switch to
   (b).)*
3. **fsmn-vad model path:** confirm we reuse the existing
   yuesub-api ONNX bundle at
   `~/workspace/yuesub-api/models/iic/speech_fsmn_vad_zh-cn-16k-common-pytorch/`
   via the same symlink as SenseVoice. *(Default: yes, single
   symlink handles both.)*
4. **HUD fallback priority when both client mic RMS and
   server fsmn-vad level are available:** which wins?
   *(Default: client wins — lower latency, no WS round-trip.
   Server is a fallback for non-browser Tauri context.)*

---

## 10. Sign-off

- [x] **D1 VAD:** dual VAD (silero + fsmn-vad in parallel).
- [x] **D2 Integration:** hybrid lift ASR (port `OnnxTranscriber`
      into `app/voice/asr/yuesub.py`).
- [x] **D3 Corrector:** enable BERT in Phase 1
      *(SCOPE FLIP from 17a §3)*.
- [x] **D4 HUD:** client-side `AnalyserNode` (no WS contract
      change for the audio path).
- [x] **D5 Models:** symlink (`~/.gundam-halo/models/iic`
      → yuesub-api repo).
- [x] **Scope confirmed:** 4-6 working days, ~1,560 LoC,
      14 new tests, 0 expected regressions on existing
      tests.

**Signed off 2026-06-14.** Implementation plan to follow in
next message (todo list, parallel tracks, verification gates).

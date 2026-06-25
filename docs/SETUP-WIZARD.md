# Setup Wizard — User Walkthrough (Sprint 44)

The Gundam Halo setup wizard takes you from "just installed" to
"first voice turn" in **< 90 seconds** (target). It walks you
through 7 steps, each one self-contained and skippable.

## When you'll see it

The wizard opens automatically the first time you launch Gundam
Halo on a fresh Mac (no `~/.gundam-halo/config.toml`). After
that, the home page shows a "Setup" card (Sprint 39) with your
progress (e.g. "Step 3 of 8") and a "Resume setup" link.

You can also re-open the wizard manually by clicking the card
or visiting `http://localhost:5173/setup` (or via Tailscale
remote access if enabled).

## The 7 steps

| # | Step | Required? | Time |
|---|---|---|---|
| 1 | **Welcome** | — | 5s |
| 2 | **LLM Provider** | ✓ Required | 30s |
| 3 | **Voice ASR** | ✓ Required | 20s |
| 4 | **Voice TTS** | ✓ Required | 30s |
| 5 | **Theme** | Optional (defaults to NT-D) | 10s |
| 6 | **Tailscale** | Optional (skip if no remote access) | 10s |
| 7 | **Smoke Test** | Auto-runs | 30s |

### Step 1 — Welcome

The wizard's intro screen. Click **Let's go →** to begin.

### Step 2 — LLM Provider

Pick your LLM provider and paste your API key. The wizard:

1. Stores the raw key in `~/.gundam-halo/.env` (chmod 600) — never
   in `config.toml` and never echoed back.
2. Tests the key against the provider's `/v1/models` endpoint
   (a cheap ping — no chat completion).
3. Writes the **env var name** to `config.toml`.

**Click "Validate" before clicking "Next"** to confirm your key
works without committing to saving it. The validation runs the
same connection test as Next, but doesn't touch any files.

Supported providers:

- **MiniMax** (default) — `https://api.minimax.io/v1`, model
  `MiniMax-M2`. Get a key at https://platform.MiniMax.io.
- **OpenAI** — `https://api.openai.com/v1`, model `gpt-4o-mini`.
- **Anthropic** — `https://api.anthropic.com/v1`, model
  `claude-3-5-sonnet-latest`.
- **Ollama** (local) — `http://localhost:11434/v1`, model
  `llama3.1`. No key needed; make sure Ollama is running.

### Step 3 — Voice Speech-to-Text (ASR)

Pick your ASR backend:

- **whisper_local** (default) — openai-whisper, runs locally.
  Pick model size: `tiny` / `base` / `small` / `medium` /
  `large-v3`. **base** is the sweet spot for Cantonese on
  Apple Silicon (~1s latency).
- **sherpa** — sherpa-onnx offline ASR. Faster than whisper on
  CPU but lower accuracy for Cantonese. Specify a model path.
- **yuesub** — Cantonese-specific (SenseVoice + fsmn-vad).
  Highest accuracy for Cantonese but requires the model files
  in `~/.cache/models/iic/...`. Specify a model path.

Device: `mps` (Apple GPU) is recommended on M1/M2/M3. Falls back
to `cpu` if MPS isn't available.

### Step 4 — Voice Text-to-Speech (TTS)

Pick your TTS backend + voice. Click **Preview** next to a
voice to hear a 1-sentence sample (`你好，Unicorn。`).

If the voice layer isn't loaded yet (e.g. you jumped to step 4
without finishing the wizard), preview shows "Preview
unavailable until step 7" — the smoke test at step 7 boots the
voice layer.

Supported voices:

- **edge** (default, free, online) — Microsoft Edge TTS. The
  Cantonese voice is `zh-HK-HiuMaanNeural` (and `WanLungNeural`).
- **azure** (premium quality) — same voices as edge but
  paid-tier quality. Requires Azure subscription.
- **piper** (offline, local) — Piper TTS. Works without
  internet but voices sound more robotic.

### Step 5 — Theme

Pick from 8 Gundam themes (the cockpit restyles instantly so
you can preview before committing):

- **gundam-ntd** (default) — Unicorn Psychoframe, pink
- **gundam-god** — orange-gold
- **gundam-seed** — pink-red
- **gundam-crossbone** — light blue
- **gundam-destiny** — purple
- **gundam-halo** — cyan
- **gundam-ntd-green** — Unicorn Green
- **gundam-cartoon** — original 1979

### Step 6 — Tailscale (Optional)

If you want to access Gundam Halo from your phone or another
Mac, enable Tailscale here. Per the project memory: **public
internet exposure is OFF** — Tailscale is the only supported
remote access method.

If you don't need remote access, click **Skip for now** — the
backend will still work on the local Mac.

To enable Tailscale: install the Tailscale app from
https://tailscale.com/download, then come back and click
**Enable Tailscale**. The wizard runs `tailscale ping
<hostname>` to verify reachability.

### Step 7 — Smoke Test

This step **auto-runs** when you arrive. It tests:

- **Text chat round-trip** — your LLM provider responds to a
  test prompt.
- **Voice round-trip** — the ASR + TTS pipeline can hear your
  mic and play audio back.

Two indicators turn green (or red) as each check completes.
If both are green within 30 seconds, click **Finish wizard →**
to land on the cockpit.

If smoke hangs (>30s) or fails, you can click **Skip smoke &
finish** to land on the cockpit anyway — investigate later
via `~/.gundam-halo/logs/launchd.err.log`.

## What happens after the wizard

You land on `/` (the cockpit overview). You can:

- Click **Voice Link** indicator (top-right) to enable the
  microphone. The first voice turn takes ~2-5 seconds to
  warm up the Whisper model.
- Open **Settings → Voice** to fine-tune wake phrases, ASR
  backend, or TTS voice.
- Visit `/setup` again at any time to re-run the wizard
  (your existing config will be preserved unless you click
  **Skip wizard** to wipe it).

## Crash recovery

If the wizard crashes mid-flow (e.g. browser tab closed,
Tauri app quit, computer slept), reopen it and it picks up
where you left off. The backend's `setup_state.json` is the
source of truth for which step you're on.

Form state (text you've typed but not yet submitted) is
**not** persisted across crashes — you'll re-type TTS
config fields, but the wizard remembers which steps are
done.

## Security guarantees

- The API key you paste in step 2 is **never** written to
  `config.toml`. The TOML references the env var name
  (`api_key_env = "MINIMAX_API_KEY"`).
- The raw key is **never** in the response payload (verified
  by 4 backend tests).
- The `.env` file is created with chmod 600 (owner-only
  read/write).
- The API key input field defaults to `type="password"`. The
  "Show" toggle is opt-in.

## What to do if a step fails

| Symptom | Cause | Fix |
|---|---|---|
| "Invalid API key" on MiniMax step 2 | Wrong key, or expired | Re-check the key at https://platform.MiniMax.io. Click "Validate" to test before saving. |
| Smoke test text OK / voice FAIL | Voice model not loaded | Check `~/.gundam-halo/logs/launchd.err.log` for the Whisper init error. |
| Smoke test both FAIL | Backend offline or stuck | Restart the backend via the menu bar tray → Restart. |
| Tailscale "unreachable" | Tailscale daemon not running | Run `tailscale up` in a terminal, then re-run the wizard. |
| Wizard stuck on a step for >1 min | Network timeout to MiniMax | Check your internet connection. The wizard has a 30s smoke timeout — beyond that, click "Skip smoke & finish". |

## FAQ

**Q: Can I skip the wizard?**
A: Yes. Click **Skip wizard** in the footer. The backend will
still boot with a minimal config; you'll need to edit
`~/.gundam-halo/config.toml` manually for voice to work.

**Q: Can I re-run the wizard after finishing?**
A: Yes. Click the **Setup** card on the home page (or visit
`/setup`). The wizard shows "Setup complete" — click **Review**
to walk through the steps again without overwriting anything.

**Q: Can I edit a single step after finishing?**
A: Yes. Click the step indicator on the wizard page (e.g. step
2) to jump directly to it. Sprint 45 will add per-step edit
from the Settings page.

**Q: Where's the API key actually stored?**
A: In `~/.gundam-halo/.env` (chmod 600). The `config.toml`
references the env var name only. See `docs/SECURITY-HARDENING.md`
for the full security model.

**Q: My voice turns were working yesterday, now they don't.**
A: Visit `/setup` and click "Re-run smoke" on step 7. If
voice FAILs, the wizard will suggest next steps.

## See also

- `docs/FEATURE-SPEC-SPRINT44-WIZARD.md` — the full design spec.
- `docs/FEATURE-SPEC-SPRINT30.md` — the wizard backend spec
  (M13 §"Setup wizard").
- `docs/SELF-HEALING.md` — what happens when the backend
  crashes (Sprint 43).
- `docs/CHANGELOG.md` — Sprint 44 release notes.

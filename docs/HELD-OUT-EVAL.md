# Held-out Eval — End-to-End Guide (Sprint 40)

Sprint 40 closes the **user-action path** for M9-E Layer 2
acceptance criterion 6 ("Held-out WER < 10% with personalised
model active"). The backend has been ready since Sprint 38
(plumbing) + Sprint 39 (dashboard); Sprint 40 adds the
**orchestrator + UI affordance** to make the verification flow
a 1-button interaction.

## The 90-second path

Goal: run your **first** held-out eval from the cockpit.

1. Open the cockpit (Tauri app or Tailscale dashboard).
2. On the home page, find the **Voice Eval** card. If you've
   never run an eval before, it shows "No evals yet".
3. **Record a 30-second Cantonese clip** via:
   ```bash
   bash scripts/record-held-out.sh
   ```
   The script prompts you to speak for 30 seconds, plays the
   recording back so you can verify your mic captured clean
   audio, then opens your `$EDITOR` on a `.txt` sidecar.
   **Type the Cantonese transcript** of what you just said
   (this is the ground truth for WER).
4. From the cockpit's Voice Eval card, click **"Run eval"**.
   The card shows "Eval in progress…" with a live elapsed
   counter.
5. After ~2 minutes (depending on Whisper model size), the
   card refreshes with your WER:
   - **WER < 15%** → green PASS badge (Cantonese quality
     is decent already).
   - **WER > 15%** → red FAIL badge with a "fine-tune
     recommended" hint.

That's the baseline. The card now shows the sparkline of
your first eval (1 point).

## The 60-minute path

Goal: bring your WER below 10% via a personalised fine-tune.

1. On the Voice Eval card, click **"Fine-tune + re-eval"**.
   This launches a background job — the card shows "Fine-tune
   in progress…" (the job can take 30-60 minutes).
2. **Wait.** The card polls every 3 seconds. The card also
   surfaces the job log path (`~/.gundam-halo/logs/finetune-<id>.log`)
   so you can `tail -f` it from a terminal if you're curious.
3. When the fine-tune + after-eval completes, the card
   refreshes with **both** the new WER AND the improvement
   indicator:
   - "↗ −42.0pp WER (−84.0%) · ✓ M9-E criterion 6" (if
     after WER is < 10%).
   - "↗ −15.0pp WER (−30.0%)" (if improvement but still
     above 10% — try a longer training corpus next time).
4. **Activate the personalised model** via Settings → Voice
   → Personalised Fine-tune → click "Activate". This swaps
   `voice.asr.backend = "whisper_hf"` and sets
   `voice.asr.model_path` in `~/.gundam-halo/config.toml`.
5. **Restart the backend** (the cockpit shows a "restart
   required" banner).
6. Speak Cantonese. The agent hears your personalised
   accent.

## What the orchestrator does

The orchestrator (`scripts/run_held_out_pipeline.py`) chains
3 subprocess calls + a diff report:

```
┌─────────────────────────────────────────────────────────────────────┐
│  scripts/run_held_out_pipeline.py --mode full                       │
│                                                                     │
│  1. baseline eval (current backend, default whisper_local base)     │
│     → scripts/run_held_out_eval.py --threshold 0.15                 │
│     → trend JSON: tests/voice/held_out_results/<UTC-ts>.json         │
│                                                                     │
│  2. fine-tune                                                        │
│     → scripts/finetune_whisper_yue.py                               │
│       --base_model_path ~/.gundam-halo/models/whisper-base          │
│       --train_audio_dir ~/.gundam-halo/recordings/                  │
│       --output_dir ~/.gundam-halo/models/whisper-yue-personalised/  │
│       --num_train_epochs 1                                         │
│                                                                     │
│  3. after eval (whisper_hf + new checkpoint)                         │
│     → scripts/run_held_out_eval.py --threshold 0.15                 │
│     → trend JSON: tests/voice/held_out_results/<UTC-ts>.json         │
│                                                                     │
│  4. diff report (printed to stdout)                                 │
│     "Baseline WER: 50.0%  (backend: whisper_local)"                  │
│     "Latest run:  WER = 8.0%   (backend: whisper_hf)"                │
│     "Improvement: −42.0pp WER (−84.0%)"                             │
│     "✓ M9-E Layer 2 acceptance criterion 6 MET"                     │
└─────────────────────────────────────────────────────────────────────┘
```

The orchestrator doesn't reimplement any of the 3 scripts —
it shells out to them and chains their exit codes. Each
existing script keeps its own tests + CLI behavior.

## Backend API surface (Sprint 40)

| Endpoint | Method | Purpose |
|---|---|---|
| `/voice/run-held-out-eval` | POST | Start a held-out eval in a background thread. Returns `{job_id, status: "pending"}`. |
| `/voice/run-held-out-eval/{job_id}` | GET | Poll an eval job's state. Returns the full `EvalJob` JSON or 404. |
| `/voice/run-finetune` | POST | Start a LoRA fine-tune in a background thread. Returns `{job_id, status: "pending"}`. |
| `/voice/list-jobs` | GET | List recent eval/finetune jobs (newest first). Used by the card to show "Last eval: 2 hours ago". |
| `/voice/eval-results` | GET | (Sprint 39 — unchanged) The 7-run trend + threshold for the sparkline. |

## The improvement indicator — what counts as "improvement"

The card renders the green ↗ + "−Xpp WER improvement" badge
ONLY when **both** of these conditions hold:

1. The latest 2 trend rows have **different `asr_backend`**
   values (e.g. `whisper_local` → `whisper_hf`). This prevents
   false positives from re-running the same backend twice.
2. The previous run's WER is **higher** than the latest run's
   WER (otherwise it's a regression, not an improvement — the
   card shows "Regression" instead).

The badge also includes "✓ M9-E criterion 6" if and only if
the latest run's WER is below 10% — that's the visual signal
that closes the milestone.

## Common failure modes

### "Eval unavailable" on the card

The backend is unreachable. Fix via the cockpit's
BackendHealthBanner (Sprint 43) — clear the crash log if
needed.

### "Run eval" button does nothing

The button is disabled when an active job is running. The
card shows the active-job pill ("● Eval: running (45s)")
above the buttons. Wait for the current job to finish (or
click "dismiss" to stop tracking the orphan — does NOT kill
the subprocess).

### "Fine-tune" button is greyed out

The button is disabled when there's no baseline run yet
(only 1 trend row, not 2). Run "Run eval" first.

### Fine-tune crashes with OOM

Your Mac is running out of memory. Reduce the training corpus
size:
```bash
bash scripts/run_held_out_pipeline.py --mode finetune \
    --train-corpus-dir ~/.gundam-halo/recordings/yue-self-short/ \
    --model-size base
```
Or close other memory-heavy apps. The default recipe uses
`batch_size=1` + `gradient_accumulation_steps=8` (effective
batch 8) for the M-series memory ceiling.

### "Improvement badge doesn't appear after fine-tune"

Two possibilities:
1. **Backend didn't actually change** — check the trend JSONs
   in `backend/tests/voice/held_out_results/`. Each JSON has
   `asr_backend` in the `results[0]` field. If both JSONs
   have the same value, the improvement check bails (intended).
2. **WER got WORSE** — the card shows "Regression" instead of
   "Improvement". This means the fine-tune hurt — try a
   longer corpus or different base model size.

### "Job stuck on running for > 10 minutes"

The orchestrator's `_run_orchestrator_thread` runs the
subprocess without a hard timeout (some fine-tunes take
60 min). To check if it's really running:
```bash
tail -f ~/.gundam-halo/logs/<job_id>.log
```
If the log is growing, it's working. If not, the subprocess
likely died — kill it via `pkill -f finetune_whisper_yue` and
click "dismiss" on the card.

## Privacy + security notes

- The orchestrator writes nothing to disk except:
  - Trend JSONs (`backend/tests/voice/held_out_results/*.json`).
    Each is ~1-2 KB and contains the user's transcript (the
    ground truth). The transcript is already on disk in
    `~/.gundam-halo/recordings/held-out-<date>.txt`, so this
    isn't new attack surface.
  - Job logs (`~/.gundam-halo/logs/eval-<job_id>.log`,
    `~/.gundam-halo/logs/finetune-<job_id>.log`). Standard
    `append` mode, never leaves the Mac.
- The diff report prints "Baseline WER" + "After WER" to
  stdout / the cockpit UI. The transcript content itself is
  NOT included (only WER numbers).
- Job state is stored in `~/.gundam-halo/state/eval_jobs.json`
  with chmod 644 (default). Contains job_id, kind, status,
  timestamps, log path. No transcript content. No PII beyond
  the timestamps ("user ran an eval at 3am").
- The fine-tune script downloads Common Voice yue from
  Hugging Face Hub (~30 min on first run). No telemetry
  back to Gundam Halo servers (we don't have any).

## FAQ

**Q: How long does the fine-tune take?**
A: 30-60 minutes for a ~30-minute self-record corpus
(1 epoch, LoRA rank 32). 2-3 hours for the full Common
Voice yue 50h corpus.

**Q: Can I fine-tune on someone else's voice?**
A: Technically yes — pass `--train-corpus-dir /path/to/their/recordings`.
But this raises an obvious consent issue. The cockpit
defaults to your own `~/.gundam-halo/recordings/` for that
reason.

**Q: My fine-tune produced a smaller file than expected.**
A: LoRA adapters save as a ~30 MB file (vs ~150 MB for the
base model + ~150 MB for the merged weights). The recipe
saves only the merged checkpoint by default (Sprint 30 Track
B); switch to "save adapters only" by editing
`scripts/finetune_whisper_yue.py:130` if you want the smaller
artifact.

**Q: How do I undo an Activate?**
A: Settings → Voice → ASR backend → switch back to
"whisper_local". The diff is just 1 line in
`~/.gundam-halo/config.toml`.

**Q: Can I run multiple evals in parallel?**
A: Yes — each click on "Run eval" generates a new job_id.
The threads don't share state (they write to separate
trend JSONs based on UTC timestamp). The card shows
whichever job is newest in `list-jobs`.

**Q: Does the orchestrator work on Apple Silicon (MPS)?**
A: Yes — the fine-tune script auto-detects MPS via
`torch.backends.mps.is_available()`. CPU is the fallback
(slower but works).

## See also

- `docs/FEATURE-SPEC-SPRINT40-LIVE-EVAL.md` — the design spec.
- `docs/FEATURE-SPEC-SPRINT38.md` — the held-out eval
  plumbing (the scripts the orchestrator composes).
- `docs/FEATURE-SPEC-SPRINT39.md` — the eval-results endpoint
  + HeldOutEvalCard.
- `docs/tickets/M9-E.md` — M9-E Layer 2 v2 status (now
  user-action-required to close).
- `scripts/record-held-out.sh` — the bash recorder.
- `scripts/run_held_out_eval.py` — the single-eval runner.
- `scripts/finetune_whisper_yue.py` — the LoRA fine-tune
  recipe.
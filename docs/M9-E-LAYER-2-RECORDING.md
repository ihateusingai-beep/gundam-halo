# M9-E Layer 2 — Personalised refinement recording guide

> Sprint 67 prep · 2026-07-12
> **Status**: Pipeline ready · waiting on user-action-required step
> **Comes after**: Sprint 67 (`<commit>`)

This guide walks you through recording your own Cantonese
audio so the backend can fine-tune a Whisper checkpoint
on your voice + vocabulary, then swap it in as the
production ASR engine. The whole flow is one command
once you've recorded the audio.

---

## 1. Why this exists

The default ASR model (`openai/whisper-base` or the CV-yue
LoRA from Sprint 55) is trained on a generic Cantonese
corpus. Your voice, your accent, your vocabulary ("Unicorn",
"NT-D", project-specific terms) are not in the training
data. M9-E Layer 2 closes the loop:

1. You record 5+ minutes of Cantonese audio via the
   Tauri Record card.
2. The pipeline (`personalise_yue.sh`) validates the
   audio format + transcript, runs a LoRA finetune on
   your audio, swaps the backend to your personalised
   checkpoint, and re-runs the held-out eval so you can
   SEE the WER drop.

The actual M9-E criterion 6 (visible WER drop after
self-record fine-tune) is gated on you recording enough
audio. Sprint 67 ships the pipeline + validator + 1-
command wrapper; the recording itself is a 10-min
manual step.

---

## 2. Step-by-step

### Step 1 — Record audio (5-10 min, manual)

Use the **Tauri Record card** in the cockpit to record
5-10 minutes of Cantonese speech. The Tauri Record card
saves each chunk to
`~/.gundam-halo/recordings/yue-self-<date>/` as:

- `chunk-XXX.wav` — 16-bit mono PCM at 16 kHz
  (Whisper's expected input)
- `chunk-XXX.txt` — your transcript, one line per file,
  UTF-8

The Record card prompts you for the transcript AFTER
recording each chunk. The script expects a
**Cantonese character set** (at least 4 CJK characters
per file — the validator rejects empty or non-CJK
transcripts).

**Suggested prompts** (read each out loud in Cantonese):

- "今日天氣好好啊"
- "我哋去食飯喇"
- "你呢個點樣做嘅"
- "佢唔識講英文"
- "畀我睇吓嗰本書"
- "幾多錢一公斤呀"
- "我聽日返廣州"
- "香港人鍾意飲凍奶茶"

Record 50+ chunks for a meaningful WER improvement.
The Sprint 67 validator accepts any corpus with **at
least 5 minutes of total audio** (more is better).

### Step 2 — Validate (1 command)

```bash
cd ~/workspace/working/gundam-halo/backend
uv run python scripts/validate_yue_self_record.py
```

The script picks the most recent `yue-self-*` dir in
`~/.gundam-halo/recordings/` and checks:

- Directory name follows `yue-self-YYYY-MM-DD`
- Each chunk has a matching `.wav` + `.txt` pair
- Each WAV is 16-bit mono PCM at 16 kHz
- Each TXT is non-empty UTF-8 + has at least 4 CJK
  characters
- Total audio duration is >= 5 minutes

Pass `--dry-run` to see what would be checked without
exiting non-zero. Pass `--force` to override the 5-min
threshold (the finetune may not improve WER with less
than 5 min, but the script will still run).

Exit codes:
- `0` — corpus is valid
- `1` — hard fail (wrong format, missing files, etc.)
- `2` — soft fail (under 5-min threshold; `--force` to
  override)

### Step 3 — Run the 1-command pipeline (30-60 min, unattended)

```bash
cd ~/workspace/working/gundam-halo
./backend/scripts/personalise_yue.sh
```

The script orchestrates 3 steps:

1. **Validate** the corpus (skipped if you just ran it)
2. **Finetune** (`scripts/finetune_whisper_yue.py`):
   LoRA adapters on top of `whisper-yue-base` from
   Sprint 55. ~30-60 min on Apple Silicon for 5-10 min
   of audio.
3. **Swap** (`scripts/swap_to_personalised_model.py`):
   Updates `~/.gundam-halo/config.toml` to point
   `voice.asr.model_path` at the new personalised
   checkpoint.

The personalised model is saved to
`~/.gundam-halo/models/whisper-yue-personalised/`.

### Step 4 — Measure the WER improvement (3 min, manual)

```bash
cd ~/workspace/working/gundam-halo/backend
uv run python scripts/run_held_out_eval.py
```

The script runs the held-out eval against the
personalised checkpoint and reports the WER. Compare
to the pre-personalised WER (the `HeldOutEvalCard` in
the cockpit shows the trend).

A meaningful WER drop is ~5-15pp on the CV-yue test
split (per the M9-E criterion 6 spec). If you don't
see a drop, the corpus is too small or the audio is
too noisy; record more + re-run.

---

## 3. Rollback

If the personalised checkpoint is worse than the
default (rare but possible if the corpus is too small
or has noisy transcripts):

```bash
cd ~/workspace/working/gundam-halo/backend
uv run python scripts/swap_to_personalised_model.py --rollback
```

This restores `voice.asr.backend = "openai_whisper"`
and `voice.asr.model_path = ""` (the pre-personalised
state).

---

## 4. Troubleshooting

**Validator says "missing transcript"**: the Tauri
Record card saves the WAV but you haven't typed the
transcript yet. Open the chunk's corresponding TXT
file and add the transcript.

**Validator says "not 16kHz"**: the recording was made
at a different sample rate. Re-record with the
default Tauri settings (16 kHz mono PCM).

**Validator says "under 5-min threshold"**: you have
less than 5 minutes of total audio. Either record
more or pass `--force` to override (not recommended
for meaningful WER improvement).

**Finetune crashes with OOM**: your Mac ran out of RAM.
The finetune needs ~8 GB of free RAM. Close other
apps + re-run. If still OOM, reduce the LoRA rank in
`finetune_whisper_yue.py` (the script has a `--rank`
flag).

**Swap succeeds but the cockpit still shows the old
model**: the backend caches the model at WS connect
time. Restart the backend (the cockpit banner has a
restart button).

---

## 5. What this guide does NOT cover

- **Live fine-tuning** (online learning from each
  voice turn). M9-E Layer 2 is offline — you record,
  then run the pipeline. Live fine-tuning is Sprint
  68+ scope if the user requests it.
- **Multi-speaker fine-tuning** (corpus from multiple
  voices). The current pipeline assumes 1 speaker.
  Multi-speaker is out of scope.
- **Cross-language transfer** (e.g. Cantonese → Yue
  dialects). The current LoRA finetune stays within
  Cantonese.

---

## 6. Sprint 67 deliverable summary

- **NEW** `backend/scripts/validate_yue_self_record.py`
  (~200 LoC): pre-flight check for the corpus
- **NEW** `backend/scripts/personalise_yue.sh`
  (~70 LoC): 1-command wrapper
- **NEW** `docs/M9-E-LAYER-2-RECORDING.md` (this file):
  step-by-step guide
- The existing `finetune_whisper_yue.py` (Sprint 55) +
  `swap_to_personalised_model.py` (Sprint 54) +
  `run_held_out_eval.py` (Sprint 26) are reused as-is.

Sprint 68+ runs the actual refinement (user-action-
required). Sprint 67 ships the prep.

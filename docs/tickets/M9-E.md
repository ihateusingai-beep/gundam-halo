# M9-E — Whisper base → medium + Cantonese fine-tune

> **Milestone**: M9 (voice layer) — M9-D follow-up
> **Priority**: medium (perceived quality, not blocking)
> **Status**: Layer 1 closed (rejected); Layer 2 v1 in flight
> (v0.1.3 base + Common Voice yue LoRA); **Layer 2 v2 self-record
> corpus SCOPED** (Sprint 33 / Track 31-B — UI + IPC contracts
> shipped; Tauri Rust pipeline deferred to a follow-up sprint
> per scope realism).
> **Discovered during**: M9-C live run, 2026-06-10
> **Owner**: Ken + Mavis
> **Decided stack** (2026-06-11): Common Voice yue LoRA + HF
> transformers + PEFT, on Whisper **base** (medium rejected in
> Layer 1).

---

## Update — 2026-06-18: Layer 2 v2 self-record corpus (Sprint 33 / Track 31-B)

**Layer 2 v2 self-record corpus shipped the backend half
+ UI + IPC contracts in Sprint 33; the Tauri Rust
recording pipeline is deferred to a follow-up sprint per
scope realism.** See the detailed status block at the
bottom of this ticket (search for "Update — 2026-06-18:
Layer 2 v2 status") for the file-by-file status table +
acceptance checklist.

---

## Update — 2026-06-11: Layer 1 REJECTED, Layer 2 is the real path

**Layer 1 (model_size base → medium) was tested and rejected in
v0.1.3.** M9-C live re-run with `model_size = "medium"`:

| Metric | base | medium | Δ |
|---|---|---|---|
| Cold-start | ~1.0s | ~40s (incl. 1.5 GB download) | +39s (first time) |
| Per-turn ASR (5s utt) | ~5.5s | ~16s | **+10.5s / 3x** |
| Total wall (M9-C live) | 12.9s | 33.1s | +20s |
| Cantonese quality | garbled English | marginally cleaner English, still no actual Cantonese | marginal |
| Disk footprint | 139 MB | +1.5 GB | +1 GB permanent |

The 3x per-turn ASR latency is unacceptable for the cockpit
UX (the user is waiting for turn-end feedback), and the
Cantonese quality improvement is marginal. Whisper's
Cantonese coverage is essentially zero across the entire
model family; a bigger base model is not the answer.

**Layer 1 is closed — not implementing.** The decision is
documented in `CHANGELOG.md` v0.1.3. `config.toml.example`
has been reverted to `base` with a comment pointing at this
ticket.

**Layer 2 (Cantonese fine-tune) is now the entire scope of
M9-E.** See the rest of this ticket for the fine-tune plan,
or jump to [Layer 2 fine-tune](#layer-2-cantonese-fine-tune-yue-specific-weights).

---

## v0.1.3 Layer 2 plan (Ken + Mavis, 2026-06-11)

### Stack decisions

| Question | Answer | Why |
|---|---|---|
| Dataset | **Common Voice yue** (Mozilla, CC-BY-SA 4.0, ~50h) | Public, no auth, native Cantonese speakers. Skip self-record for v1 (option B available later). |
| Toolchain | **Hugging Face `transformers` + PEFT/LoRA** | Modern, active, smaller LoRA memory footprint, MPS-friendly. |
| Base model | **Whisper `base`** (not medium) | Medium rejected in Layer 1 for latency. Base + LoRA per-turn ~6s on MPS. |
| LoRA rank | 32, alpha 64, target `q_proj` + `v_proj` | Standard ratio; ~5M trainable params; attention-only LoRA is empirically the best quality/memory trade-off for Whisper. |
| Training epochs | 3 | Standard for LoRA on 50h corpus. |
| Effective batch | 8 (per_device 1 × grad_accum 8) | Memory ceiling on M-series MPS. |
| Learning rate | 1e-3 | Standard LoRA starting point for Whisper. |
| Optimizer | default (AdamW) | HF Trainer default. |
| Mixed precision | none / bf16 if M3+ | MPS fp16 unreliable; bf16 is M3/M4 only. |

### Code / config changes (committed in v0.1.3)

| File | Status | Note |
|---|---|---|
| `pyproject.toml` | ✅ | New `train` extra: `transformers`, `peft`, `datasets`, `accelerate`, `jiwer`, `soundfile`. Install with `uv sync --extra train --extra voice`. |
| `app/core/config.py` | ✅ | `VoiceASRConfig.model_path: str = ""` accepted. Loader updated. |
| `app/voice/asr/whisper_local.py` | ✅ | Constructor accepts `model_path`; **emits a warning** if set, since openai-whisper can't load HF directories yet. Full support lands in v0.1.4. |
| `app/voice/asr/asr_factory.py` | ✅ | Threads `model_path` through. |
| `scripts/finetune_whisper_yue.py` | ✅ NEW | Full recipe script. CLI + argparse. `prepare_common_voice_yue` raises NotImplementedError as a **stub** — the real materialise-and-split logic is the next chunk of work. |
| `tests/voice/test_whisper_yue.py` | ✅ NEW | Acceptance tests; **all skip** until a trained model lands at `~/.gundam-halo/models/whisper-yue-base/`. |

### What's NOT in v0.1.3 (deferred)

- **Actual training run** — the script is the recipe; executing it
  is its own ~3h wall-clock session (download 50h CV yue + LoRA
  training + WER eval).
- **`WhisperLocalASR` swap to HF-pipeline backend** — the openai-
  whisper package cannot load HF-format model directories. v0.1.4
  will replace the backend. The trained weights from this sprint
  are forward-compatible.
- **User-recorded corpus** — deferred to a future Layer 2 v2.
- **`m9c_voice_tools.py` augmented system note removal** — depends
  on the trained model working through the new backend, so this
  also lands in v0.1.4.

### How to actually run the training (v0.1.3 follow-up session)

```bash
cd ~/workspace/working/gundam-halo/backend
# 1. Install the training stack on top of the existing venv.
uv sync --extra train --extra voice

# 2. (Optional) Verify the env.
.venv/bin/python -c "import transformers, peft, datasets, jiwer; print('ok')"

# 3. Run the training. This will:
#    - Download Common Voice 13.0 yue via Hugging Face Hub (~30min)
#    - Materialise train/val/test splits to ~/.gundam-halo/cache/cv-yue/
#    - LoRA fine-tune Whisper base for 3 epochs (~2.5h on M-series)
#    - Merge LoRA into the base weights and save to
#      ~/.gundam-halo/models/whisper-yue-base/  (HF format)
#    - Run WER on the held-out test split, exit 2 if WER > 20%
.venv/bin/python scripts/finetune_whisper_yue.py

# 4. Run the acceptance tests (now that the model exists, they
#    don't skip).
.venv/bin/python -m pytest tests/voice/test_whisper_yue.py -v
```

### v0.1.4 follow-ups (after the model is trained)

1. Replace `WhisperLocalASR` (openai-whisper) with
   `WhisperHFASR` (transformers pipeline) — same interface,
   swap the inference path. Add `backend = "whisper_hf"` to
   the factory, keep `whisper_local` as a backward-compat
   alias.
2. Update `~/.gundam-halo/config.toml`:
   ```toml
   [voice.asr]
   backend = "whisper_hf"
   model_path = "~/.gundam-halo/models/whisper-yue-base/"
   ```
3. Re-run M9-C live. **Delete the augmented system note in
   `scripts/m9c_voice_tools.py:187-192`** — verify the agent
   still completes the task without the workaround.
4. Commit the model directory under `~/.gundam-halo/` only if
   it's small enough; otherwise document the download step
   in a setup script.

---

## Layer 2 fine-tune (Cantonese yue-specific weights)


## Symptom

The M9-C live Cantonese fixture transcribes to:

```
ASR text: 'Please use the file read tool to read backhand read me
         and tell me the first line.'
```

The original spoken Cantonese is roughly:

> 幫我讀 gundam-halo backend 嘅 README 嘅第一行

What the user actually said (Cantonese, normal speed) and what
Whisper base hears is **completely different** — Whisper base
treats it as English, mis-hears the Cantonese phonemes as English
words ("backhand" / "first line" leak through from common
phrases), and the agent only figures out the intent because the
spoken sentence *happens* to contain the words "file read tool"
and "first line". The agent's system prompt has to rely on an
*augmented* note pointing at the README explicitly so the LLM
still gets a usable directive (see
`backend/scripts/m9c_voice_tools.py:187-192`).

This is a fundamental ceiling on the voice layer: every Cantonese
utterance the user makes has to be re-translated by the LLM
through an English lens, and any time the spoken Cantonese
doesn't happen to contain enough English words the LLM will
mis-route the request.

## Why base fails on Cantonese

- `openai-whisper` base (~74M params) is a one-size-fits-all
  English-pretrained model. Its Cantonese coverage is
  effectively zero.
- Cantonese is a low-resource language for Whisper: not in
  the original 680k-hour training set, only covered by
  multilingual fine-tuning in larger models.
- The `language="yue"` hint is **not** in
  `whisper.tokenizer.LANGUAGES`, so we already pass
  `language=None` (auto-detect) and let the model guess — it
  almost always guesses English for HK speakers.

The M9-D ticket already added a server-side "augmented system
note" workaround that points the agent at the file the user
*probably* means. That works for the M9-C fixture because the
spoken query happened to mention "README" / "file read" in
English-friendly tokens. For real users in real conversation
it will fall over.

## Proposed fix

Two layers, both required for real production Cantonese.

### Layer 1: Bump Whisper `base` → `medium`

Whisper medium (~769M params) has substantially better
multilingual coverage, including Cantonese. The
`openai-whisper` package's `whisper.load_model("medium")`
downloads a single `.pt` file from
`https://openaipublic.azureedge.net/main/...` (or
`download_root` if set, e.g. `~/.cache/whisper`).

**Trade-off**: model size goes from ~150 MB (base) to ~1.5 GB
(medium), cold-start time roughly doubles (we observed
~1.0s for base on MPS; expect ~2.5–3.0s for medium), and
inference latency per 5-second utterance goes from
~600 ms to ~1.5 s on Apple Silicon M-series.

The cold-start is paid once per `create_app()` (lifespan), so
the per-turn hit is just the inference latency. For a 5-second
Cantonese utterance the per-turn delta is ~900 ms — acceptable
for the cockpit UX (the VAD-detected turn is already
human-paced, not latency-sensitive).

Config change (live `~/.gundam-halo/config.toml`):

```toml
[voice.asr]
backend = "whisper_local"
model_size = "medium"            # was "base"
device = "auto"
```

No code change required — `whisper_local.py:23` already
forwards `model_size` to `whisper.load_model(self._model_size, ...)`.

### Layer 2: Cantonese fine-tune (yue-specific weights)

Whisper medium still treats Cantonese as a low-resource
language. The M9-E endgame is a fine-tune of Whisper medium
on a Cantonese dataset, exporting the weights to a local
directory, and pointing the ASR factory at that directory
instead of a model-size name.

**Datasets** (open, Cantonese, suitable for Whisper fine-tune):

- **Common Voice yue** — Mozilla's crowdsourced Cantonese
  corpus (~50h released in v11, growing). CC-BY-SA 4.0.
  Direct download: https://commonvoice.mozilla.org/yue/datasets
- **MDCC** (Mandarin-Cantonese Code-switching Corpus) — has a
  Cantonese subset, useful for code-switch tolerance.
- **yue-cantonese-speech** (Hugging Face) — smaller curated
  set, good for quick iteration.
- **Self-recorded** — for a single-user project like Gundam
  Halo, recording 30 minutes of the user's own Cantonese
  speech (Tauri app records mic on demand) and fine-tuning
  on that is realistic and dramatically improves
  personalisation. The user has consented via the cockpit
  privacy toggle.

**Fine-tune tooling** (in order of recommendation):

1. **Hugging Face `transformers` + PEFT/LoRA** — modern
   stack, easy to iterate. Use
   `WhisperForConditionalGeneration.from_pretrained(...)`
   with `language="cantonese"` + `task="transcribe"`,
   freeze the encoder, LoRA the decoder.
2. **`openai-whisper` fine-tuning** (the official repo
   ships `whisper-finetune` notebooks) — more direct, but
   older and less ergonomic than HF.
3. **mlx-whisper** (Apple Silicon native) — fastest
   inference on MPS, but fine-tune story is less mature.

**Expected outcomes** (rough estimates from public Whisper
Cantonese benchmarks):

| Model | Common Voice yue WER |
|---|---|
| Whisper base (current) | ~70–80% |
| Whisper medium | ~35–45% |
| Whisper medium + LoRA fine-tune on 10h yue | ~15–25% |
| Whisper medium + full fine-tune on 50h yue | ~8–15% |

A WER of <20% on a single user's voice is "production
usable" for the cockpit — the LLM downstream has enough
signal to route requests correctly without the
augmentation workaround.

### Code changes required (Layer 2)

1. **`app/core/config.py`** — extend `VoiceASRConfig` with
   an optional `model_path: str | None = None`. When set,
   `whisper_local.py` uses it instead of `model_size`.
2. **`app/voice/asr/whisper_local.py`** — accept either
   `model_size` (download from HF mirror) or `model_path`
   (load from local dir).
3. **`app/voice/asr/asr_factory.py`** — pass `model_path`
   through to the constructor.
4. **New script `backend/scripts/finetune_whisper_yue.py`** —
   fine-tune a Whisper medium checkpoint on the user's
   recorded corpus, export to `~/.gundam-halo/models/whisper-yue-medium/`.
5. **Tests** in `tests/voice/test_whisper_local.py` — load
   the fine-tuned model from a small fixture, transcribe a
   known fixture, assert WER < threshold.

## Out of scope (separate tickets)

- ASR streaming (we currently transcribe the whole turn
  after `voice.end`, not chunk-by-chunk).
- Multi-speaker / diarisation.
- Code-switching (mixed Cantonese + English + Mandarin in
  the same turn).
- Whisper large-v3 evaluation.

## Test plan

### Layer 1 acceptance

- [ ] Live `~/.gundam-halo/config.toml` switched to
      `model_size = "medium"`.
- [ ] Cold-start time logged at `INFO` level: should be
      < 5s on Apple Silicon M-series.
- [ ] Re-run M9-C live. Assert `ASR text` no longer looks
      like garbled English — at minimum, the proper nouns
      "gundam-halo", "README", "backend" should survive
      verbatim.

### Layer 2 acceptance

- [ ] `model_path` config option wires through to
      `whisper_local.py:load_model` without code changes to
      the M9-C dry-run / live scripts.
- [ ] `scripts/finetune_whisper_yue.py` runs end-to-end on
      a 30-min fixture corpus and produces a checkpoint
      under `~/.gundam-halo/models/whisper-yue-medium/`.
- [ ] `tests/voice/test_whisper_local.py` loads the
      fine-tuned model and asserts WER < 20% on a held-out
      Cantonese fixture.
- [ ] M9-C live re-run: `ASR text` matches the user's
      spoken Cantonese closely enough that the agent's
      **augmented system note is no longer needed**
      (delete lines 187–192 of `m9c_voice_tools.py` and
      verify the agent still completes the task).

## Resource requirements

- **Disk**: +1.4 GB for medium weights, +1.4 GB for the
  fine-tuned copy. Total ASR model footprint: ~3 GB.
- **Cold-start RAM**: ~2.5 GB peak during load.
- **Fine-tune**: 50h of Common Voice yue + 1× Apple Silicon
  Mac with 16 GB RAM, ~6h of fine-tune time on M-series GPU
  via mlx. (LoRA only, full fine-tune would need 24+ GB.)
- **Self-record path**: 30 min user recording + 1h
  fine-tune, all local, no cloud spend.

## Decision points (block on user)

- **Layer 1 alone** (model_size bump, no fine-tune) is
  shippable today. The Cockpit will still be usable for
  users who mostly speak English / Mandarin; Cantonese
  alone won't be production-grade until Layer 2.
- **Fine-tune dataset**: Common Voice yue (open, less
  personalised), self-record (private, more personalised),
  or both? Recommendation: start with Common Voice yue for
  Layer 2 v1, add self-record in v2 once the pipeline
  works.
- **Fine-tune toolchain**: HF + LoRA (modern, recommended)
  vs. `openai-whisper` (official, more direct). Pick one
  before starting work to avoid context switches.

## Acceptance summary

- [ ] Layer 1: medium model wired through config + ASR
      factory, no code-side breakage, M9-C live re-run
      produces a non-garbled Cantonese transcript.
- [ ] Layer 2: `model_path` config option, fine-tune
      script, WER < 20% on held-out Cantonese fixture,
      M9-C's augmented system note becomes redundant.
- [ ] CHANGELOG entry for v0.1.3 documenting both layers
      and the model footprint trade-off.

## Update — 2026-06-24: Layer 2 v2 status (Sprint 33b — Tauri pipeline lands)

**Sprint 33b ships the Tauri Rust recording + training
pipeline that Sprint 33 deferred.** All 5 IPC commands
(`start_record` / `stop_record` / `start_train` /
`get_train_progress` / `activate_model`) now run real
work; the cockpit's 3 cards (Record / Train / Swap) wire
to `invoke()` and bind to live `phase` from the response.

What's live now (Sprint 33b):

| Artifact | Status | Path |
|---|---|---|
| `cpal` input stream (16 kHz mono int16) | ✅ | `frontend/src-tauri/src/recording/capture.rs` |
| `hound` WAV writer (30 s chunks, 480k samples) | ✅ | `frontend/src-tauri/src/recording/capture.rs` |
| JSONL manifest appender (one line per chunk) | ✅ | `frontend/src-tauri/src/recording/capture.rs` |
| `tokio` chunk-rotator (1 s poll, 3-idle exit) | ✅ | `frontend/src-tauri/src/recording/capture.rs` |
| `WhisperHandle` (parallel Python helper subprocess) | ✅ | `frontend/src-tauri/src/recording/transcribe.rs` |
| `TrainHandle` (LoRA fine-tune subprocess) | ✅ | `frontend/src-tauri/src/recording/transcribe.rs` |
| `RecordingError` (4 real variants) | ✅ | `frontend/src-tauri/src/commands.rs` |
| `toml_edit` config patch in `activate_model` | ✅ | `frontend/src-tauri/src/commands.rs` |
| Rust unit tests (6 cases — WAV round-trip, JSONL schema, stop-flag race) | ✅ | `frontend/src-tauri/src/recording/capture.rs::tests` |
| Frontend wire-in (VoiceTab 3 cards → live `phase`) | ✅ | `frontend/src/routes/settings/VoiceTab.tsx` |

The `cpal::Stream` `!Sync` workaround (per
`cpal-0.15.3`'s `PhantomData<*mut ()>`) means the capture
thread is a dedicated `std::thread` — the Tauri `State`
holds only `Arc<AtomicBool>` stop flags + `Arc<Mutex<...>>`
counters, all `Send + Sync`.

**Acceptance criterion status**:

- [x] JSONL manifest schema pinned (8 unit tests pass).
- [x] Trainer accepts `--base_model_path` + `--train_audio_dir`.
- [x] Settings UI shows the 3 cards (Record / Train / Swap).
- [x] Tauri IPC command surface defined + registered.
- [x] Real microphone capture + parallel WhisperHFASR
      transcription (Sprint 33b ships this).
- [ ] Held-out WER < 10% with personalised model active
      (per §4.3 acceptance criterion 6) — needs live
      training run + held-out eval; deferred to next
      sprint.

## Update — 2026-06-18: Layer 2 v2 status (Sprint 33 / Track 31-B)

**Layer 2 v2 self-record corpus shipped the **backend half**
in Sprint 33; the Tauri Rust recording pipeline is
**deferred** to a follow-up sprint.**

What's live now (Sprint 33):

| Artifact | Status | Path |
|---|---|---|
| `finetune_whisper_yue.py --base_model_path` flag | ✅ | `backend/scripts/finetune_whisper_yue.py` |
| `finetune_whisper_yue.py --train_audio_dir` flag | ✅ | `backend/scripts/finetune_whisper_yue.py` |
| Self-record manifest schema + reader | ✅ | `backend/app/voice/self_record_manifest.py` |
| Manifest unit tests (8 cases, JSONL schema) | ✅ | `backend/tests/voice/test_self_record_manifest.py` |
| `--base_model_path` CLI parser test | ✅ | `backend/tests/voice/test_finetune_script.py` |
| Settings → Voice → Personalised Fine-tune UI | ✅ | `frontend/src/routes/settings/VoiceTab.tsx` |
| Tauri IPC command surface (5 commands) | ✅ scaffold | `frontend/src-tauri/src/commands.rs` |
| Tauri recording pipeline (capture + queue) | ⚠️ deferred | `frontend/src-tauri/src/recording.rs` |

The user's day-to-day path:

1. Run `bash scripts/install-launchd.sh` to enable
   auto-restart (Sprint 34, separate ticket).
2. Open Settings → Voice → Personalised Fine-tune →
   click **Start recording** (toast surfaces
   "deferred to follow-up sprint").
3. Manually invoke the personalised fine-tune via:
   ```bash
   cd backend && .venv/bin/python scripts/finetune_whisper_yue.py \
       --base_model_path ~/.gundam-halo/models/whisper-yue-base/ \
       --train_audio_dir ~/.gundam-halo/recordings/yue-self-<date>/ \
       --num_train_epochs 1 \
       --output_dir ~/.gundam-halo/models/whisper-yue-self-<date>/ \
       --skip_eval
   ```
4. Run `pytest tests/voice/test_held_out_eval.py -v` to
   verify the personalised model passes WER < 15% on
   the user's recorded held-out set.

**Acceptance criterion status**:

- [x] JSONL manifest schema pinned (8 unit tests pass).
- [x] Trainer accepts `--base_model_path` + `--train_audio_dir`.
- [x] Settings UI shows the 3 cards (Record / Train / Swap).
- [x] Tauri IPC command surface defined + registered.
- [ ] Real microphone capture + parallel WhisperHFASR
      transcription — **deferred** to follow-up sprint.
      The Rust scaffold (`recording.rs`) defines the
      pipeline shape and validates `ChunkRecord`s; the
      capture thread + mpsc transcription queue are the
      next sprint's work.
- [ ] Held-out WER < 10% with personalised model active
      (per §4.3 acceptance criterion 6) — blocked on
      the deferred recording pipeline.

## Commits (planned)

- `<sha>` `chore(asr): bump Whisper base → medium via config`
- `<sha>` `feat(asr): accept model_path for local fine-tuned checkpoints`
- `<sha>` `feat(scripts): Cantonese Whisper fine-tune script`
- `<sha>` `test(asr): load fine-tuned model + WER assertion`

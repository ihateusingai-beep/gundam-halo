# M9-E — Whisper base → medium + Cantonese fine-tune

> **Milestone**: M9 (voice layer) — M9-D follow-up
> **Priority**: medium (perceived quality, not blocking)
> **Status**: open
> **Discovered during**: M9-C live run, 2026-06-10
> **Owner**: TBD (Ken + Mavis collaboration)

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

## Commits (planned)

- `<sha>` `chore(asr): bump Whisper base → medium via config`
- `<sha>` `feat(asr): accept model_path for local fine-tuned checkpoints`
- `<sha>` `feat(scripts): Cantonese Whisper fine-tune script`
- `<sha>` `test(asr): load fine-tuned model + WER assertion`

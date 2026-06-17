# Feature Spec — Sprint 24: v0.1.4 land finalization (Track 3 augmented-note deletion + WER acceptance gate)

> **Status:** DRAFT — proposed Sprint 24 scope.
> **This is a SPEC-ONLY sprint.** No code is written
> until the user has completed the M9-E Layer 2
> training run (Sprint 19d runbook) AND the M9-C
> live re-run has been observed to pass without
> the augmented system note.
> **Predecessors:**
> - Sprint 19d (commit `0388699`) shipped the
>   training runbook + smoke test.
> - Sprint 19d addendum (commit `a8d8e17`) shipped
>   the background monitor (`finetune_whisper_yue_monitor.py`).
> - Sprint 21 (commit `3353106`) shipped
>   `prepare_common_voice_yue` impl.
> - Sprint 22 (commit `e0b87f9`) shipped the
>   4-track design freeze.
> - Sprint 23 (commit `4e85e99`) shipped Tracks 1
>   (WhisperHFASR), 2 (whisper_local cleanup),
>   and 4 (Sprint 17a banner expiry). **Track 3
>   was explicitly deferred** to this sprint
>   because it is conditional on the M9-C live
>   re-run passing without the workaround.
> **Scope:** 1 hour wall clock when implemented
> (Track 3 deletion is 16 lines + comment
> header, plus a CHANGELOG entry). The bulk of
> Sprint 24's "work" is the **user-driven
> acceptance gate workflow** that gates the
> commit: training run + WER check + double
> M9-C live re-run.
> **Out of scope (deferred to 25+):** launchd /
> systemd supervisor; self-record corpus +
> Layer 2 v2; mlx-whisper inference.

---

## 0. Why this sprint exists

Sprint 23 (commit `4e85e99`) shipped three of
the four tracks from the Sprint 22 v0.1.4
rollout plan. The remaining track — **Track 3
(augmented system note deletion)** — was
explicitly deferred because it is **the
observable acceptance test for the M9-E Layer
2 fine-tune**, and the fine-tune itself has
not yet been executed (it's a user-driven 3h+
wall-clock session per Sprint 19d §6 runbook).

Sprint 24 ships the design freeze for the
final piece of v0.1.4 land. The actual
implementation lands in Sprint 25+ once the
user has run the training session and the
M9-C live re-run has been observed to pass
without the augmented system note.

This spec also captures the **acceptance gate
workflow** that gates the commit: the
Sprint 19d runbook (training) + the Sprint
22 §4.2 M9-C double-run workflow (acceptance
test) + the git revert safety net. These
three steps together are the single
**observable proof** that the fine-tune worked
— if the agent completes the M9-C fixture
without the synthetic system note telling it
to use `file_read` on `README.md`, then the
fine-tuned model handles Cantonese proper-noun
tokens correctly, and the M9-D workaround
becomes obsolete.

## 1. Goals

1. **Document the Track 3 acceptance gate
   workflow** so the user can run the
   M9-C double re-run in a single session
   without re-deriving the steps.
2. **Pin the WER acceptance criterion** at
   < 20% on the held-out Common Voice yue test
   set (per M9-E §"Layer 2 acceptance" +
   Sprint 19d §6.1 + Sprint 22 §4.2).
3. **Capture the git revert safety net** so
   the user can roll back the augmented-note
   deletion in one command if the M9-C re-run
   fails without it.
4. **No code is written in this sprint.**
   Sprint 24 is spec-only. The CHANGELOG
   entry is "Planned for v0.1.4 finalization
   (Sprint 25+, post-training)".

## 2. Out of scope (deferred)

- **Actual augmented-note deletion** — Sprint
  25+ (1 hour, conditional on the M9-C live
  re-run passing without the workaround).
- **Actual training run** — user session, 3h+
  wall clock (per Sprint 19d §6). This is a
  pre-condition for the Track 3 deletion, not
  part of any sprint.
- **`uv sync --extra voice-hf --extra voice`
  install** — 3GB of ML deps (the user runs
  this once before the training run).
- **launchd / systemd supervisor** — Sprint
  25+ per Sprint 19b §2.
- **Self-record corpus + Layer 2 v2** — per
  M9-E §"v0.1.3 Layer 2 plan".
- **mlx-whisper inference** — per M9-E
  §"Fine-tune tooling".

## 3. User-facing behavior

This sprint is **invisible to the user until
the training run completes**. The cockpit
still uses `WhisperLocalASR(base)` (or
`YuesubASR` if the user picked that). Once
the training run produces a HF-format
checkpoint under
`~/.gundam-halo/models/whisper-yue-base/`,
the user can flip the `voice.asr.backend`
config to `"whisper_hf"` and point
`model_path` at the new checkpoint. The
M9-C live re-run then verifies the fine-tune
worked.

The augmented-note deletion is the **observable
acceptance test**. The script
`backend/scripts/m9c_voice_tools.py:179-199`
contains a 21-line block (the comment header
+ the `augmented = (...)` construction + the
`agent.run(augmented, context=ctx)` call) that
augments the spoken Cantonese text with a
synthetic system note telling the agent to
use `file_read` on `README.md`. This block
was added in M9-D because Whisper base
garbled Cantonese proper-noun tokens. With
the fine-tuned model, the synthetic note
becomes obsolete — but **only if the
fine-tune actually worked**. If WER > 20%,
the agent can't route the request correctly
without the workaround.

The deletion lands in Sprint 25+ when the
user has observed:
- (a) The training run exited 0 with
  `WER < 20%` on the held-out test set.
- (b) The M9-C live re-run with the
  augmented note (the v0.1.3 code) AND the
  new `WhisperHFASR` backend completes
  the file_read task on `README.md` and
  replies in Cantonese.
- (c) The M9-C live re-run **without** the
  augmented note also completes the task.

If all three pass, the deletion commits.
If (c) fails, the user runs
`git revert <commit-hash-of-Sprint-25>`
and the v0.1.4 land is held until the
fine-tune is retrained or the user accepts
the degraded behavior.

## 4. Architecture

### 4.1 The acceptance gate workflow

The acceptance gate has three sequential
steps, each with a clear pass/fail. The
user drives the entire flow in a single
session (~3.5h wall clock total: 3h training
+ 30min M9-C runs + setup time).

#### Step 1 — Training run (Sprint 19d runbook)

```bash
# In the backend dir:
cd ~/workspace/working/gundam-halo/backend

# Pre-flight: install the training deps.
# ~3GB of ML libs (transformers, torch, datasets, peft, etc.)
uv sync --extra train --extra voice

# Optional: install the voice-hf extra for the post-training
# WhisperHFASR runtime (only needed AFTER the training run
# produces a HF-format checkpoint). Skip this for now —
# the training script doesn't need it.
# uv sync --extra voice-hf

# Run the training. This will:
#   - Download Common Voice 13.0 yue via Hugging Face Hub
#     (~30min, resumable on re-run)
#   - Materialise train/val/test splits to
#     ~/.gundam-halo/cache/cv-yue/  (resumable)
#   - LoRA fine-tune Whisper base for 3 epochs
#     (~2.5h on M-series)
#   - Merge LoRA into the base weights and save to
#     ~/.gundam-halo/models/whisper-yue-base/  (HF format)
#   - Run WER on the held-out test split,
#     exit 2 if WER > 20%
.venv/bin/python scripts/finetune_whisper_yue.py

# If the script exits 0, the training succeeded
# and the WER gate passed (< 20%). The HF-format
# checkpoint is at ~/.gundam-halo/models/whisper-yue-base/.

# If the script exits 2, WER > 20%. Inspect the
# training log + eval output and decide whether to:
#   - bump --num_train_epochs from 3 to 5
#   - bump --lora_r from 32 to 64
#   - expand the training set
#   - roll back and defer the sprint
```

The training run is monitored by the
Sprint 19d addendum background supervisor
(`scripts/finetune_whisper_yue_monitor.py`).
The monitor exits 0 on success, 2 on WER
failure, 3 on crash, 4 on hang (no progress
for >30 min), 1 on bad model version. The
user can run the monitor in a separate
terminal:

```bash
# In a separate terminal, after kicking off
# the training:
.venv/bin/python scripts/finetune_whisper_yue_monitor.py \
    --pid $(pgrep -f finetune_whisper_yue.py)
```

#### Step 2 — WER gate verification (M9-E acceptance)

```bash
# Run the WER acceptance test against the
# fine-tuned model. The test loads the
# HF-format checkpoint from
# ~/.gundam-halo/models/whisper-yue-base/
# and asserts WER < 20% on the held-out
# Cantonese fixture.
.venv/bin/python -m pytest tests/voice/test_whisper_yue.py -v

# Expected: all tests pass (no longer skip
# when the model is missing).
```

If the test fails, the fine-tune didn't
achieve the WER target. The user inspects
the eval output and decides whether to
re-train (return to Step 1) or defer the
Sprint 25 commit.

#### Step 3 — M9-C double re-run (acceptance test for Track 3)

This is the **observable acceptance test**
for the M9-E fine-tune. The user runs
`scripts/m9c_voice_tools.py` **twice**:
once with the v0.1.3 augmented note (the
existing code), once without (after the
Sprint 25 commit lands). If both pass,
the fine-tune is good. If only the v0.1.3
run passes, the fine-tune didn't fully
fix the Cantonese proper-noun problem and
the user must investigate.

```bash
# Pre-flight: install the voice-hf extra
# (~850MB of ML libs) so the new
# WhisperHFASR backend can load the
# fine-tuned checkpoint.
uv sync --extra voice-hf --extra voice

# Update the user's config.toml to point
# at the new HF-format checkpoint. This
# is a one-time manual edit.
cat >> ~/.gundam-halo/config.toml << 'EOF'

# v0.1.4: switch to the fine-tuned
# Whisper HF backend.
[voice.asr]
backend = "whisper_hf"
model_path = "~/.gundam-halo/models/whisper-yue-base/"
EOF

# Restart the backend to pick up the new
# config (Sprint 19b's `schedule_restart`
# also fires here if the user changed
# `asr_backend` via the Settings → Voice
# tab PUT).
# ... restart the backend ...

# Run 1: M9-C with the v0.1.3 augmented
# note (the current code, no change).
# This is the baseline — we already
# know this passes (it was the M9-C
# acceptance in Sprint 17b).
.venv/bin/python scripts/m9c_voice_tools.py

# Expected: exit 0, used_tool_content == True,
# the TTS output contains the README's
# first line ("# Gundam Halo — Backend").

# Run 2: M9-C WITHOUT the augmented note.
# This is the test — the user runs the
# M9-C live re-run after the Sprint 25
# commit lands. See Sprint 25 spec for
# the exact diff.

# (For Sprint 24, this step is documented
# in the spec but not executed. The user
# runs it during the Sprint 25 session.)
```

If Run 2 fails (the agent can't complete
the file_read task without the synthetic
system note), the fine-tune didn't work
and the user runs:

```bash
# One-command revert of the augmented-note
# deletion.
git revert <commit-hash-of-Sprint-25>
```

The augmented note is restored, the
fine-tune checkpoint is kept (so the
user can re-train with different
hyperparameters without re-running the
3h training session), and the v0.1.4
land is held.

### 4.2 The Track 3 deletion (Sprint 25 impl)

When Sprint 25 lands, the deletion is a
20-line edit to
`backend/scripts/m9c_voice_tools.py:179-199`
(the comment header + the
`augmented = (...)` block + the
`agent.run(augmented, context=ctx)` call):

```python
# BEFORE (v0.1.3 / Sprint 23):
async def native_react_voice_cb(sid: str, text: str) -> str | None:
    print(f"  [agent.run] in: {text!r}")
    # M9-C note: ASR may mangle the spoken query (whisper base
    # + Cantonese is lossy with proper-noun tokens). To make
    # M9-C's tool-calling path deterministic, we augment the
    # spoken text with an explicit instruction + the absolute
    # path of the README, so the LLM still gets a clear
    # "use file_read on /Users/kencheng/.../README.md" directive
    # even when ASR returned "Please use the file read tool to
    # read back and read me and tell me the first line.".
    augmented = (
        f"{text}\n\n"
        "[system note for the agent: the user is asking about the "
        f"file {README_PATH!r}. Use the file_read tool to read it, "
        "then quote its first line. Reply in Cantonese.]"
    )
    ctx = AgentContext(
        session_id=sid,
        user_id="ken",
        user_display_name="Ken",
        project_id=None,
    )
    result = await agent.run(augmented, context=ctx)

# AFTER (v0.1.4 finalization / Sprint 25):
async def native_react_voice_cb(sid: str, text: str) -> str | None:
    print(f"  [agent.run] in: {text!r}")
    # M9-E Layer 2 acceptance: the fine-tuned WhisperHFASR
    # backend handles Cantonese proper-noun tokens correctly,
    # so we no longer augment the spoken text with a
    # synthetic system note. The agent receives the raw
    # ASR transcript. If the agent fails the M9-C fixture
    # here, the fine-tune didn't work and we need to
    # `git revert` this change (see Sprint 24 spec §4.1).
    ctx = AgentContext(
        session_id=sid,
        user_id="ken",
        user_display_name="Ken",
        project_id=None,
    )
    result = await agent.run(text, context=ctx)
```

**21 lines removed** (lines 179-199 inclusive;
the M9-C note comment header (8 lines) +
the `augmented = (...)` block (6 lines) +
the `agent.run(augmented, ...)` call (1 line)
+ the surrounding blank lines (2 lines) +
the new M9-E acceptance comment (4 lines
replacing 8 lines = net -4 lines)).
**Net: -16 lines**, matching Sprint 22 spec
§5 file-by-file table estimate.

The `README_PATH` constant at line 50 stays
— the `m9c_voice_tools.py` main() function
(line 111-115) still uses it to populate
`README_FIRST_LINE` for the success check
at line 362-366. We only delete the
augmentation, not the fixture loading.

### 4.3 Git revert safety net

The Sprint 25 commit lands with a clear
commit message that includes the revert
command. The user copies the commit hash
from `git log` immediately after the
commit lands:

```bash
$ git log --oneline -1
4e85e99 feat(asr): Sprint 23 — v0.1.4 land ...   # Sprint 23
... (Sprint 24 spec, Sprint 25 commit) ...
<hash>  feat(asr): Sprint 25 — M9-E Layer 2 acceptance: delete augmented system note

# User copies <hash> for potential revert.
```

If the M9-C re-run fails without the
augmented note, the user runs:

```bash
git revert <hash>
# This restores the augmented note in a
# new commit. The fine-tune checkpoint at
# ~/.gundam-halo/models/whisper-yue-base/
# is NOT deleted — the user can re-train
# with different hyperparameters without
# re-running the 3h training session.
```

The revert is **non-destructive**: the
augmented note returns to
`m9c_voice_tools.py:179-199` exactly as
it was before the Sprint 25 commit. The
user keeps `backend = "whisper_hf"` +
`model_path = "~/.gundam-halo/models/whisper-yue-base/"`
in `~/.gundam-halo/config.toml` (the
fine-tuned model is still useful, just
not enough on its own to remove the
augmentation).

### 4.4 File-by-file change set (when Sprint 25 lands)

| Path | Change | LoC est. |
|---|---|---|
| `backend/scripts/m9c_voice_tools.py` | Replace lines 179-199 (the M9-C note comment + `augmented = (...)` block + `agent.run(augmented, ...)` call) with a 4-line M9-E Layer 2 acceptance comment. | 0 / -16 |
| `docs/CHANGELOG.md` | v0.1.4 finalization release entry: M9-E Layer 2 acceptance, augmented-note deletion, M9-C double re-run. | +90 / 0 |
| `docs/tickets/M9-E.md` | Mark Layer 2 acceptance boxes ✓ (or ✗ if WER > 20% and the user reverted). | +5 / -5 |

**Total**: ~84 LoC. ~1 hour wall clock
(Sprint 25 is a single-commit sprint).

### 4.5 Dependency graph (final v0.1.4 land)

```
+----------------------------------+
| Step 1: prepare_common_voice_yue |  ← Sprint 21 ✓ (commit 3353106)
| (180 LoC impl in finetune script) |
+----------------+-----------------+
                 v
+----------------------------------+
| Actual training run             |  ← User session, 3h+  ← Sprint 24 GATE
| (Sprint 19d runbook + monitor)   |
+----------------+-----------------+
                 v
+----------------------------------+
| WER < 20% on held-out fixture   |  ← Sprint 24 GATE
| (tests/voice/test_whisper_yue.py)|
+----------------+-----------------+
                 v
+----------------------------------+
| Step 2: WhisperHFASR backend     |  ← Sprint 23 ✓ (commit 4e85e99)
| (factory + impl + tests)         |
+----------------+-----------------+
                 v
+----------------------------------+
| Step 3: remove warning           |  ← Sprint 23 ✓ (commit 4e85e99)
| (WhisperLocalASR cleanup)        |
+----------------+-----------------+
                 v
+----------------------------------+
| Step 4: M9-C live re-run #1     |  ← User session, 5 min
| (with augmented note, baseline)  |
+----------------+-----------------+
                 v
+----------------------------------+
| Step 5: delete augmented note   |  ← Sprint 25, 1 hour
| (m9c_voice_tools.py:179-199)     |    (conditional on Step 6)
+----------------+-----------------+
                 v
+----------------------------------+
| Step 6: M9-C live re-run #2     |  ← User session, 5 min
| (without augmented note)         |    (acceptance test)
+----------------+-----------------+
                 v
+----------------------------------+
| Step 7: git commit OR revert    |  ← User session, 1 min
| (Track 3 deletion accepted)     |
+----------------+-----------------+
                 v
+----------------------------------+
| Optional: launchd supervisor     |  ← Sprint 25+ (deferred)
+----------------------------------+
```

Sprint 24 is the **gate** for the training
run + WER check. Sprint 25 is the
**implementation** of the Track 3 deletion
(conditional on the gate passing). The
**acceptance test** for the deletion is
the Step 6 M9-C re-run, which the user
executes in the same session as the
Sprint 25 commit.

## 5. Sprint 24 vs Sprint 25 scope split

The reason Sprint 24 is spec-only and
Sprint 25 is the implementation:

- **Sprint 24 (spec-only)** captures the
  acceptance gate workflow, the M9-C
  double re-run procedure, the git revert
  safety net, and the file-by-file change
  set. It does **not** delete the
  augmented note — the deletion is
  conditional on the user running the
  training session and the M9-C re-run.
- **Sprint 25 (impl)** is the
  one-commit implementation of the
  deletion, with a CHANGELOG entry and
  the M9-E ticket update. The user
  commits the Sprint 25 change AFTER
  Step 4 (M9-C with augmented note)
  passes, then runs Step 6 (M9-C
  without augmented note) to verify
  the deletion.

The split keeps Sprint 24 visible to the
user **before** the training run, so the
user can review the acceptance gate
workflow in advance. The Sprint 25 commit
is small (1 hour) and can be done in the
same session as the training run.

## 6. Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **WER > 20% on first training run** | Medium | High | The training script exits 2 on WER > 20%. The user re-trains with more epochs / larger LoRA / more data. Worst case: roll back to `whisper_local(base)` and defer v0.1.4 land. |
| **Augmented-note deletion breaks M9-C** | Low | High | The git revert path is one command. The user keeps the augmented note in git history; if the agent fails the M9-C re-run, revert. The fine-tune checkpoint is NOT deleted on revert — the user can re-train with different hyperparameters. |
| **M9-C fixture is no longer the right acceptance test** | Low | Low | M9-C was designed for M9-D (Cantonese on whisper-base). If the fine-tune works, the M9-C live re-run passes. If the fine-tune overfits, M9-C still passes (the fixture is in the training distribution). We need a held-out test (user-recorded, ~30s) to verify personalisation. |
| **Common Voice yue download auth wall** | Low | Medium | Mozilla dropped the auth wall for v11+ public datasets. If a future version re-introduces auth, the user runs `huggingface-cli login` first. We don't bake the auth into the script. |
| **M9-E fine-tune is overfit to Common Voice yue speakers** | Medium | Medium | Common Voice yue is read speech (people reading prompted text), not conversational. Production Cantonese has more casual speech patterns. Mitigation: the user can record their own 30-min corpus (M9-E §"Self-recorded") and mix with Common Voice for Layer 2 v2. |
| **Training script crashes mid-run** | Low | Medium | The Sprint 19d addendum monitor (`finetune_whisper_yue_monitor.py`) detects crashes (exit code 3) and hangs (exit code 4). The materialisation step (Sprint 21) is resumable — if the streaming download crashes, re-running the script picks up where it left off. |
| **MPS OOM during training** | Low | Medium | The training script's `--batch_size` defaults to 8; if the user's Mac has < 16GB unified memory, drop to 4 via `--batch_size 4`. The training log shows memory usage; the user can kill and restart with smaller batch. |
| **User forgets to update `~/.gundam-halo/config.toml`** | Medium | High | Step 3 of the acceptance gate workflow explicitly calls out the config.toml update. The `MavisBridge` (Sprint 19c P1 §3.4) also surfaces a "Restart required" banner when `asr_backend` changes via the Settings → Voice tab. If the user edits config.toml directly, the banner doesn't fire — but the backend restart will pick up the new value. |
| **User runs M9-C re-run on the wrong backend** | Low | High | The re-run must use the new `WhisperHFASR` backend (not `WhisperLocalASR(base)`). Step 3 explicitly checks `~/.gundam-halo/config.toml` for `backend = "whisper_hf"` BEFORE running. If the user accidentally leaves `backend = "whisper_local"`, the M9-C re-run uses the v0.1.3 model and the augmented note deletion is meaningless. |
| **`uv sync --extra voice-hf` breaks the venv** | Low | Low | The voice-hf extra adds ~850MB of ML deps. The user runs `uv sync --extra voice-hf --extra voice` (NOT `--all-extras`, which would pull in 50+ test/dev deps). If the sync fails, the user can `uv sync --extra voice` to restore the baseline. |

## 7. Acceptance tests

1. **Training run exits 0** — The user runs
   `scripts/finetune_whisper_yue.py` and
   observes exit code 0. The HF-format
   checkpoint is at
   `~/.gundam-halo/models/whisper-yue-base/`.
2. **WER < 20% on held-out fixture** —
   `pytest tests/voice/test_whisper_yue.py -v`
   passes. The fixture's
   `FINE_TUNED_MODEL_DIR` constant
   (`backend/tests/voice/test_whisper_yue.py`)
   points at the user's local checkpoint
   directory; the test no longer skips
   because the model is present.
3. **M9-C Run 1 passes (with augmented note)**
   — `python scripts/m9c_voice_tools.py`
   exits 0 with `used_tool_content == True`
   and the TTS output contains the README's
   first line.
4. **Track 3 deletion lands** — Sprint 25
   commit modifies
   `m9c_voice_tools.py:179-199`, deleting
   16 lines and adding 4 lines (M9-E
   acceptance comment). The git diff
   shows the expected change.
5. **M9-C Run 2 passes (without augmented note)**
   — Same script, same config, but with
   the Sprint 25 commit applied. Exits 0
   with `used_tool_content == True`. **This
   is the observable acceptance test for
   the M9-E fine-tune.**
6. **No regression** — all 188 backend
   voice tests + 2 skipped from Sprint 23
   still pass. All 63 frontend vitest tests
   still pass. `pnpm tsc --noEmit` clean.
   `pnpm build` succeeds.
7. **Git revert safety net** — If Run 2
   fails, `git revert <sprint-25-hash>`
   restores the augmented note. The user
   verifies by re-running M9-C and seeing
   the agent complete the task again. The
   fine-tune checkpoint is NOT deleted.

## 8. Sign-off

- [ ] **Sprint 24 scope agreed** — spec-only,
      captures the acceptance gate workflow
      (training + WER + double M9-C re-run)
      and the Track 3 deletion file-by-file
      change set. No code is written in
      Sprint 24.
- [ ] **Sprint 25 scope agreed** —
      one-commit implementation of the
      augmented-note deletion, conditional
      on the M9-C re-run passing without
      the workaround. Git revert is the
      rollback path.
- [ ] **Out-of-scope items confirmed** —
      launchd / systemd supervisor; self-
      record corpus + Layer 2 v2; mlx-whisper
      inference all deferred to Sprint 26+.

---

## Appendix A — Sprint 24 spec ↔ Sprint 22 spec line-number drift

Sprint 22 spec §4.1 "Track 3" lists the
augmented-note block as "lines 180-195" (in
one place) and "lines 187-192" (in another
place, narrower scope). The actual line range
in the current code
(`backend/scripts/m9c_voice_tools.py`) is
**lines 179-199 inclusive** (verified
2026-06-17 against commit `4e85e99`):

- **179-186**: 8-line M9-C note comment
  header (the "ASR may mangle the spoken
  query" rationale).
- **187-192**: 6-line `augmented = (...)`
  block (the f-string concatenation +
  the synthetic system note string).
- **193-198**: 6-line `AgentContext(...)`
  constructor + the `result = await
  agent.run(augmented, context=ctx)` call.
- **199**: trailing blank line.

**Net deletion: 20 lines (179-199) − 4 lines
(M9-E replacement comment) = 16 lines.** This
matches Sprint 22 spec §5 file-by-file table
estimate of `0 / -16`.

If the user runs `git diff` on the Sprint 25
commit and sees a different number, the
spec was probably written against an earlier
commit (e.g. `ffc2624` for Sprint 20 or
`3353106` for Sprint 21). The current code at
`4e85e99` (Sprint 23) has the augmented-note
block at lines 179-199 inclusive.

## Appendix B — M9-C success criteria deep-dive

The M9-C live re-run
(`backend/scripts/m9c_voice_tools.py`) has
three observable success criteria
(`main()` function, line 390):

```python
return 0 if (asr_text and agent_text and used_tool_content) else 1
```

The Sprint 24 acceptance gate cares about
**`used_tool_content`** specifically:

```python
# Line 355-366:
used_tool_content = False
if saved_mp3.exists() and saved_mp3.stat().st_size > 0:
    try:
        tts_text = transcribe_tts_output(saved_mp3)
        print(f"  TTS audio re-transcribed: {tts_text!r}")
        # Check: did the agent's text make it into the spoken reply?
        # The LLM's reply should reference the README's first line.
        tokens = [t for t in README_FIRST_LINE.split() if len(t) > 3]
        for tok in tokens:
            if tok in tts_text or tok in (agent_text or ""):
                used_tool_content = True
                break
```

`used_tool_content == True` means the agent's
reply (or the TTS output) contains a token
from the README's first line (`# Gundam Halo
— Backend`). The token check is loose —
`len(t) > 3` filters out short tokens like
"the" and "a", and the match is substring
("Gundam", "Halo", "Backend" all match).

**Why this is the right acceptance test for
Track 3**: if the agent's reply contains
"Gundam" or "Backend" or "Halo", it must
have called `file_read` on `README.md` to
get those tokens. The `file_read` tool is
the only way for the agent to access the
file content. So `used_tool_content == True`
proves:
1. The agent heard the user's request
   (the ASR transcript was correct).
2. The agent decided to use `file_read`
   (without the synthetic system note
   telling it to).
3. The agent's `file_read` call succeeded
   (the README is at the expected path).
4. The agent's reply included the file
   content (the token check passed).

The augmented-note workaround bypasses step
2 — it tells the agent explicitly to use
`file_read`, even if the ASR transcript
mangled the user's request. The deletion
removes the bypass, so step 2 has to work
endogenously.

**If `used_tool_content` is True on Run 2
(without the augmented note), the fine-tune
is good. If False, the fine-tune didn't
fully fix the Cantonese proper-noun
problem and the user must investigate.**

## Appendix C — Why Sprint 24 is spec-only

The user might ask: why not combine Sprint
24 (spec) and Sprint 25 (impl) into a
single sprint?

The answer is **commit cadence**:

- Sprint 24 is **visible before the
  training run**. The user reviews the
  acceptance gate workflow, the M9-C
  double re-run procedure, and the git
  revert safety net BEFORE spending 3h
  on the training session. If the user
  disagrees with the workflow (e.g. wants
  a different acceptance test), they can
  push back on the spec without wasting
  the training session.
- Sprint 25 is **one commit at the end
  of the training session**. The user
  applies the deletion, runs the M9-C
  re-run, and either commits the deletion
  or reverts. The commit is small (16
  lines) and the rollback is one command.

Combining the two into one sprint means
the user reviews the workflow in the
middle of the training session, which is
the wrong time to be making process
decisions. The spec-only → impl split
keeps the design freeze separate from
the implementation, which is the pattern
Sprint 20 → 21 → 22 → 23 already
established.

## Appendix D — Test count evolution (cumulative)

| Sprint | New tests | Total backend voice |
|---|---|---|
| 21 (previous) | +5 | 102 |
| 22 (spec-only) | 0 | 102 |
| 23 (impl: 1+2+4) | +38 | 140 |
| **24 (spec-only)** | **0** | **140** |
| 25 (impl: 3) | +0 (no new tests needed; the deletion is verified by the M9-C re-run) | 140 |

Sprint 25 ships 0 new tests because the
Track 3 deletion is verified by **the
M9-C live re-run itself** (the `used_tool_content
== True` check at `m9c_voice_tools.py:390`).
Adding a unit test for "does the script
not augment the text" would be a tautology
— the test would just check that the
`augmented` variable is unused, which is
trivially true after the deletion. The
**observable** test is the M9-C re-run.

If the user wants a unit-test
counterpart, we could add
`test_m9c_voice_tools_no_augmented_note`
that greps the source for the
`augmented =` assignment and asserts
its absence. This would be a 5-line
test. But it's redundant with `git diff`
— the user can see the deletion in the
Sprint 25 commit. We skip it for now.

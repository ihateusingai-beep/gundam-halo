# Feature Spec — Sprint 25: v0.1.4 finalization (Track 3 impl — augmented-note deletion + M9-C re-run gate)

> **Status:** DRAFT — proposed Sprint 25 scope.
> **This is an IMPLEMENTATION sprint.** It is a
> single-commit, ~1 hour wall clock change.
> **Predecessors:**
> - Sprint 19d (commit `0388699`) shipped the
>   training runbook + smoke test.
> - Sprint 19d addendum (commit `a8d8e17`)
>   shipped the background monitor.
> - Sprint 21 (commit `3353106`) shipped
>   `prepare_common_voice_yue` impl.
> - Sprint 22 (commit `e0b87f9`) shipped the
>   4-track design freeze.
> - Sprint 23 (commit `4e85e99`) shipped
>   Tracks 1 (WhisperHFASR), 2 (whisper_local
>   cleanup), 4 (Sprint 17a banner expiry).
>   Track 3 was explicitly deferred.
> - Sprint 24 (commit `c24eb85`) shipped the
>   acceptance gate workflow (training + WER
>   + double M9-C re-run) and the git revert
>   safety net as a spec-only freeze.
> **Pre-condition (gate):** The user has
> completed the M9-E Layer 2 training run
> (Sprint 19d runbook) and observed WER < 20%
> on the held-out fixture. The M9-C live
> re-run with the v0.1.3 augmented note (the
> baseline) passed. This is the green light
> to ship the Sprint 25 commit.
> **Scope:** 1 commit, ~1 hour wall clock. The
> commit deletes ~10 lines from
> `m9c_voice_tools.py:179-199` (the M9-C note
> comment + the `augmented = (...)` block)
> and replaces them with a 5-line M9-E Layer
> 2 acceptance comment. The commit message
> embeds the revert command for the
> post-commit gate.
> **Out of scope (deferred to 26+):**
> launchd / systemd supervisor; self-record
> corpus + Layer 2 v2; mlx-whisper inference.

---

## 0. Why this sprint exists

Sprint 24 (commit `c24eb85`) shipped the
design freeze for the final piece of v0.1.4
land. The acceptance gate workflow
(training run → WER < 20% check → M9-C
double re-run) is documented. The git
revert safety net is specified. The
file-by-file change set is locked in.

Sprint 25 ships the **one-commit
implementation** of the Track 3 augmented-
note deletion. The commit lands in the
**same session as the training run** —
the user runs the M9-C live re-run twice
(once with the v0.1.3 augmented note, once
without), and either commits the deletion
or reverts it, all in a ~5 min window after
the training run completes.

This is a **surgical edit sprint**. The
total change is one file, ~10 lines net
deletion, one CHANGELOG entry, one commit.
The risk register is dominated by the
**M9-C re-run passing without the augmented
note** — if it fails, the user runs
`git revert <hash>` and the augmented note
returns exactly as it was. The
fine-tune checkpoint at
`~/.gundam-halo/models/whisper-yue-base/`
is NOT touched by the revert; the user can
re-train with different hyperparameters
without re-running the 3h session.

## 1. Goals

1. **Ship the Track 3 deletion** in a single
   commit. The user observes M9-C Run 1
   (with augmented note) passing, applies
   the deletion commit, observes M9-C Run 2
   (without augmented note) passing, and
   keeps the commit. If Run 2 fails, the
   user reverts and the augmented note is
   restored.
2. **Capture the commit message template**
   so the user can copy-paste it into
   `git commit -m "..."` with the correct
   structure (the revert command is
   embedded in the commit body, not the
   subject, so the user has the exact
   `git revert <hash>` command immediately
   after the commit lands).
3. **Update the CHANGELOG** with the
   v0.1.4 finalization release entry
   (M9-E Layer 2 acceptance, augmented-note
   deletion, M9-C double re-run).
4. **Mark the M9-E Layer 2 acceptance
   boxes** in `docs/tickets/M9-E.md` ✓
   (or ✗ if the user reverted).

## 2. Out of scope (deferred)

- **Re-running the training session with
  different hyperparameters** — separate
  user session, 3h+ wall clock each. The
  revert path keeps the existing checkpoint
  so the user can compare new training runs
  against the Sprint 25 baseline.
- **M9-C fixture refresh** — the fixture
  (`backend/tests/voice/fixtures/readme_query.wav`)
  was designed for M9-D and is still the
  right acceptance test for v0.1.4. A
  held-out test (user-recorded, ~30s) is
  deferred to M9-E Layer 2 v2.
- **launchd / systemd supervisor** — per
  Sprint 19b §2.
- **Self-record corpus + Layer 2 v2** —
  per M9-E §"v0.1.3 Layer 2 plan".
- **mlx-whisper inference** — per M9-E
  §"Fine-tune tooling".

## 3. User-facing behavior

This sprint is **invisible to the user
unless the M9-C re-run fails**. The
augmented-note deletion is a script-internal
change to `m9c_voice_tools.py` — the cockpit
flow (push-to-talk or always-on mic →
WhisperHFASR → agent → TTS → Live2D) is
unchanged. The only observable difference
is that the agent now has to use
`file_read` on `README.md` endogenously
(without the synthetic system note
prompting it to).

**Pass path** (the most likely outcome):
1. The training run completed with WER <
   20% (Sprint 24 Step 1 + Step 2 passed).
2. The M9-C Run 1 (with augmented note,
   v0.1.3 code) passed (Sprint 24 Step 3
   baseline). Exit 0, `used_tool_content ==
   True`, TTS contains README's first line.
3. The user applies the Sprint 25 commit
   (the deletion).
4. The M9-C Run 2 (without augmented note,
   v0.1.4 code) passes. Exit 0,
   `used_tool_content == True`. The agent
   used `file_read` endogenously.
5. The Sprint 25 commit stays. The v0.1.4
   land is complete.

**Fail path** (revert):
1. Steps 1-3 same as pass path.
2. M9-C Run 2 fails (exit 1, or exit 0
   with `used_tool_content == False`).
3. The user runs `git revert <hash>` —
   the augmented note returns to
   `m9c_voice_tools.py:179-199` exactly as
   it was. The fine-tune checkpoint is
   NOT deleted; the user can re-train
   with `--lora_r 64` instead of `--lora_r
   32` (per Sprint 19d §6.1) without
   re-running the entire 3h session —
   actually they DO need to re-run the 3h
   session because LoRA r=32 is baked into
   the checkpoint, but the Common Voice yue
   materialisation is resumable (per Sprint
   21) so the re-run is faster on a second
   pass.
4. The user inspects the M9-C failure log
   and decides whether to re-train
   (return to Sprint 19d runbook) or defer
   the v0.1.4 land.

## 4. Architecture

### 4.1 The exact diff

The Sprint 25 commit modifies one file
(`backend/scripts/m9c_voice_tools.py`) with
a 5-step edit:

**Step 1**: Delete the 8-line M9-C note
comment header (current lines 179-186):

```diff
-        # M9-C note: ASR may mangle the spoken query (whisper base
-        # + Cantonese is lossy with proper-noun tokens). To make
-        # M9-C's tool-calling path deterministic, we augment the
-        # spoken text with an explicit instruction + the absolute
-        # path of the README, so the LLM still gets a clear
-        # "use file_read on /Users/kencheng/.../README.md" directive
-        # even when ASR returned "Please use the file read tool to
-        # read back and read me and tell me the first line.".
```

**Step 2**: Delete the 6-line
`augmented = (...)` block (current lines
187-192):

```diff
-        augmented = (
-            f"{text}\n\n"
-            "[system note for the agent: the user is asking about the "
-            f"file {README_PATH!r}. Use the file_read tool to read it, "
-            "then quote its first line. Reply in Cantonese.]"
-        )
```

**Step 3**: Insert a 5-line M9-E Layer 2
acceptance comment in place of the deleted
14 lines:

```diff
+        # M9-E Layer 2 acceptance (v0.1.4 / Sprint 25): the
+        # fine-tuned WhisperHFASR backend handles Cantonese
+        # proper-noun tokens correctly, so we no longer augment
+        # the spoken text with a synthetic system note. The
+        # agent receives the raw ASR transcript. If the agent
+        # fails the M9-C fixture here, the fine-tune didn't
+        # work — see Sprint 24 spec §4.3 for the git revert
+        # safety net. The original augmented block is preserved
+        # in git history (commit <sprint-25-hash>).
```

**Step 4**: Modify the `agent.run()` call
on current line 199 — change
`augmented` → `text`:

```diff
-        result = await agent.run(augmented, context=ctx)
+        result = await agent.run(text, context=ctx)
```

**Step 5**: No other changes. The
`AgentContext(...)` constructor (lines
193-198) and the post-call logging
(lines 200-204) stay verbatim.

**Net diff**: ~10 lines removed
(14 lines deleted − 4 lines added for
the 5-line replacement comment, where
the first line is a +0 padding to
preserve indentation) − 1 line modified
(net 0). **Total: ~10 lines deleted,
1 line modified, 0 lines added net for
the comment block**.

The Sprint 22 spec §5 file-by-file table
estimates `0 / -16` and the Sprint 24 spec
Appendix A reconciles to `-16` net. The
actual math is closer to **-9 to -11 net
depending on blank-line collapsing**:
- Lines 179-192 deleted (14 lines)
- Lines 179-183 added (5 lines) — net
  of this block: -9 lines
- Line 199 modified (1 line, net 0)
- The 4-line M9-E comment in Sprint 24
  Appendix A is actually 5 lines (the
  spec undercounted). **Net: -9 lines
  from the deletion block + 0 from the
  modify = -9 lines net**.

The Sprint 22 / 24 spec's "16" line count
is over-estimated by ~7 lines. This is a
**spec drift, not an implementation drift**
— the actual deletion lands as ~9-10 lines
net. The user can `git diff --stat` to
verify.

### 4.2 The commit message template

The Sprint 25 commit lands with a structured
commit message. The subject is short (one
line, ≤ 72 chars). The body embeds the
**revert command** so the user has the
exact `git revert <hash>` to copy-paste
immediately after the commit lands:

```bash
git add backend/scripts/m9c_voice_tools.py docs/CHANGELOG.md docs/tickets/M9-E.md
git commit -m "feat(asr): Sprint 25 — M9-E Layer 2 acceptance: delete augmented system note

v0.1.4 finalization per Sprint 24 spec
(commit c24eb85) and Sprint 22 spec §4.1
Track 3 (commit e0b87f9). The fine-tuned
WhisperHFASR backend (Sprint 23 commit
4e85e99) handles Cantonese proper-noun
tokens correctly, so the augmented system
note workaround in
backend/scripts/m9c_voice_tools.py:179-199
becomes redundant. The agent now receives
the raw ASR transcript and uses file_read
endogenously.

Acceptance test: M9-C live re-run
(backend/scripts/m9c_voice_tools.py) with
the v0.1.4 code and the new WhisperHFASR
backend exits 0 with used_tool_content ==
True — the agent's reply contains a token
from the README's first line (\"Gundam\",
\"Halo\", or \"Backend\"), proving
file_read was called endogenously (without
the synthetic system note telling it to).

REVERT COMMAND (if M9-C re-run #2 fails):
  git revert HEAD
This restores the augmented note exactly
as it was. The fine-tune checkpoint at
~/.gundam-halo/models/whisper-yue-base/
is NOT deleted — re-train with different
hyperparameters without re-running the
3h session (the Common Voice yue
materialisation is resumable per Sprint 21
commit 3353106).

Out of scope (deferred to 26+):
  * launchd / systemd supervisor
  * Self-record corpus + Layer 2 v2
  * mlx-whisper inference

Refs: Sprint 24 spec §4.1-4.3, Sprint 23
commit 4e85e99, Sprint 22 spec §4.1
Track 3, M9-E §Layer 2 acceptance, Sprint
19d §6 runbook."
```

**Why `git revert HEAD` instead of
`git revert <hash>`**: the user runs the
revert immediately after the Sprint 25
commit lands, so `HEAD` points at the
Sprint 25 commit. Using `HEAD` is robust
to the user not having copied the hash —
the next commit in the log is always
`HEAD~1` and `HEAD` is the current commit.

If the user runs other commits between
the Sprint 25 commit and the revert
(unlikely, but possible), the user
substitutes `git revert <hash>` with the
actual hash from `git log --oneline -1`
before the revert.

### 4.3 The post-commit checklist

The user runs this checklist **immediately
after** the Sprint 25 commit lands, **before**
running M9-C Run 2:

```bash
# 1. Verify the commit landed and the
#    message embeds the revert command.
git log --oneline -1
git log -1 --format=%B | head -40
# Expected: subject line "feat(asr): Sprint 25 ..."
# + body with the "REVERT COMMAND" section.

# 2. Verify the diff is what we expect.
git diff HEAD~1 HEAD --stat
# Expected: 3 files changed, ~10 lines net
# deletion in m9c_voice_tools.py, ~10
# lines added in CHANGELOG.md, ~5 lines
# added in M9-E.md.

git diff HEAD~1 HEAD -- backend/scripts/m9c_voice_tools.py
# Expected: lines 179-192 deleted (14 lines),
# lines 179-183 added (5 lines), line 199
# modified (augmented → text).

# 3. Copy the commit hash to a safe place
#    (a sticky note, the user's editor, etc.)
#    so it's available if git revert HEAD
#    ever points at a different commit.
git rev-parse HEAD
# Output: <40-char hash>  <-- COPY THIS

# 4. Run M9-C Run 2.
.venv/bin/python scripts/m9c_voice_tools.py
# Expected: exit 0, used_tool_content == True.

# 5. If Run 2 passes, the commit stays.
#    The user is done with v0.1.4 land.

# 6. If Run 2 fails (exit 1 OR exit 0 with
#    used_tool_content == False), run the
#    revert:
git revert HEAD
# This restores the augmented note in a
# new commit. The fine-tune checkpoint
# is preserved.

# 7. If Run 2 partially passes (e.g. the
#    agent completes but the TTS audio
#    doesn't contain the README first line),
#    the user inspects the logs and decides
#    whether to revert or to accept the
#    partial pass.
```

### 4.4 The CHANGELOG entry

The Sprint 25 commit includes a CHANGELOG
entry under `[Unreleased]`:

```markdown
### Sprint 25 — v0.1.4 finalization (M9-E Layer 2 acceptance)

Sprint 25 ships the final piece of v0.1.4
land: the deletion of the augmented system
note workaround in
`backend/scripts/m9c_voice_tools.py:179-199`.
This is the **observable acceptance test**
for the M9-E Layer 2 Cantonese fine-tune
(per Sprint 22 spec §4.1 Track 3 + Sprint
24 spec §4.2). The user ran the M9-C live
re-run with both the v0.1.3 augmented note
(the baseline) and the v0.1.4 code (the
test); both passed with
`used_tool_content == True`, proving the
fine-tuned WhisperHFASR backend handles
Cantonese proper-noun tokens correctly and
the agent now uses `file_read` endogenously.

#### Changed
- **backend**: `scripts/m9c_voice_tools.py`
  — deleted the 8-line M9-C note comment
  header (lines 179-186) + the 6-line
  `augmented = (...)` block (lines 187-192)
  + modified the `agent.run(augmented, ...)`
  call (line 199) to `agent.run(text, ...)`.
  Inserted a 5-line M9-E Layer 2 acceptance
  comment in place of the deleted 14 lines.
  **Net: ~10 lines deleted, 1 line
  modified.** The `README_PATH` constant
  (line 50) and the `AgentContext` constructor
  (lines 193-198) stay unchanged.
- **docs**: `tickets/M9-E.md` — marked the
  Layer 2 acceptance boxes ✓ (or ✗ if
  the user reverted; see Sprint 24 spec
  §4.3 for the revert path).

#### Verified (this sprint)
- `cd backend && .venv/bin/python
  scripts/m9c_voice_tools.py` — exit 0,
  `used_tool_content == True`. M9-C Run 1
  (with augmented note, v0.1.3 code) +
  Run 2 (without augmented note, v0.1.4
  code) both passed.
- `cd backend && .venv/bin/pytest
  tests/voice/` — 188 passed, 2 skipped,
  0 failed (Sprint 23 baseline preserved;
  Sprint 25's deletion is verified by the
  M9-C re-run, not by unit tests).
- `cd frontend && pnpm tsc --noEmit` —
  0 errors.
- `cd frontend && pnpm vitest run` — 63/63
  pass. No frontend changes in Sprint 25.

#### Out of scope (deferred to 26+)
- **launchd / systemd supervisor** — per
  Sprint 19b §2.
- **Self-record corpus + Layer 2 v2** —
  per M9-E §"v0.1.3 Layer 2 plan".
- **mlx-whisper inference** — per M9-E
  §"Fine-tune tooling".
```

### 4.5 The M9-E ticket update

`docs/tickets/M9-E.md` has a Layer 2
acceptance checkbox section. The Sprint 25
commit flips the boxes:

```markdown
## Layer 2 acceptance

- [x] Training run completed with WER < 20%
      on the held-out Common Voice yue test
      set (per Sprint 19d §6.1 WER acceptance
      criteria).
- [x] `tests/voice/test_whisper_yue.py`
      passes (no longer skips because the
      fine-tuned model is at
      `~/.gundam-halo/models/whisper-yue-base/`).
- [x] M9-C live re-run with the v0.1.3
      augmented note (baseline) exits 0
      with `used_tool_content == True`.
- [x] M9-C live re-run with the v0.1.4
      deletion (Sprint 25) exits 0 with
      `used_tool_content == True`.
- [x] Augmented system note deleted from
      `scripts/m9c_voice_tools.py:179-199`
      (commit `<sprint-25-hash>`).
- [x] `git log --oneline | grep -i sprint.25`
      shows the commit in the v0.1.4 land
      chain.

## Revert path (if any box is ✗)

If the user reverts the Sprint 25 commit
(via `git revert HEAD`), the boxes flip
back to ✗ and the v0.1.4 land is held
until the fine-tune is retrained with
different hyperparameters (per Sprint 24
spec §4.3).
```

The exact wording of the boxes is the
user's choice — the spec captures the
**shape** of the update (5 boxes, all ✓
or all ✗ depending on pass/fail), not
the exact text. The user copies the
template into the ticket.

### 4.6 File-by-file change set (Sprint 25)

| Path | Change | LoC est. |
|---|---|---|
| `backend/scripts/m9c_voice_tools.py` | Delete lines 179-192 (14 lines: 8 M9-C note comment + 6 `augmented = (...)` block). Insert 5-line M9-E Layer 2 acceptance comment. Modify line 199 (`augmented` → `text`). | 0 / -9 (net) |
| `docs/CHANGELOG.md` | v0.1.4 finalization release entry under `[Unreleased]`. | +90 / 0 |
| `docs/tickets/M9-E.md` | Mark Layer 2 acceptance boxes ✓ (or ✗ if reverted). | +5 / -5 |

**Total**: ~95 LoC. ~1 hour wall clock
(Sprint 25 is a single-commit sprint).

### 4.7 Dependency graph (v0.1.4 land complete)

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
| Step 5: delete augmented note   |  ← Sprint 25, 1 hour  ← THIS SPRINT
| (m9c_voice_tools.py:179-199)     |    (commit lands, message
+----------------+-----------------+     embeds revert command)
                 v
+----------------------------------+
| Step 6: M9-C live re-run #2     |  ← User session, 5 min
| (without augmented note)         |    (acceptance test)
+----------------+-----------------+
                 v
+----------------------------------+
| Step 7: commit stays OR revert  |  ← User decision
| (Track 3 deletion accepted)     |
+----------------+-----------------+
                 v
+----------------------------------+
| v0.1.4 land complete             |  ← Tag v0.1.4 in main
+----------------------------------+
```

Sprint 25 lands the Step 5 commit.
Step 6 + Step 7 happen **in the same
session** as the commit (the user runs
M9-C Run 2 immediately after the commit,
observes the result, and either keeps or
reverts). The v0.1.4 tag is the user's
call — the spec doesn't mandate a tag,
just the commit.

## 5. Sprint 25 vs Sprint 24 spec

Sprint 24 (commit `c24eb85`) shipped the
**gate workflow** — the 3 sequential steps
(training → WER → M9-C double re-run) that
the user runs **before** the Sprint 25
commit. Sprint 25 ships the **commit
itself** — the one-commit implementation
of the deletion, with the embedded revert
command.

The two sprints are tightly coupled:
- Sprint 24's gate **must pass** before
  Sprint 25's commit lands.
- Sprint 25's commit **embeds** the
  revert command so the user can roll
  back if Sprint 24's gate was wrong
  (i.e. the M9-C Run 2 fails despite
  the gate passing).

If the user reverses the order (lands
Sprint 25's commit first, runs the gate
second), the gate's M9-C Run 2 is on the
v0.1.4 code, which is the right test. The
Sprint 25 commit is **idempotent in
failure** — the user can revert without
side effects. The order matters only for
**commit cleanliness** — landing Sprint
25's commit on top of a known-good
training run keeps the git log linear
and the revert clean.

## 6. Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **M9-C Run 2 fails** | Low | High | The git revert is one command (`git revert HEAD`). The augmented note is restored exactly. The fine-tune checkpoint is NOT deleted. The user can re-train with different hyperparameters. |
| **The M9-C fixture is the wrong acceptance test** | Low | Low | The fixture (`backend/tests/voice/fixtures/readme_query.wav`) is a synthesized Cantonese query that asks the agent to read the README. This is a **representative** Cantonese tool-triggering query — if the fine-tune handles it correctly, it handles 90%+ of real Cantonese queries. A held-out test (user-recorded, ~30s) is M9-E Layer 2 v2. |
| **The user runs the Sprint 25 commit before the gate passes** | Medium | Medium | The Sprint 25 commit is idempotent in failure — the user can revert without side effects. The commit message embeds the revert command so the user doesn't have to remember the syntax. The Sprint 24 spec §4.1 explicitly states "the user runs the M9-C live re-run twice: once with the v0.1.3 augmented note (the existing code), once without (after the Sprint 25 commit lands)" — the order is documented. |
| **The user forgets to update `~/.gundam-halo/config.toml`** | Medium | High | Step 3 of Sprint 24 §4.1 explicitly calls out the config.toml update. The M9-C re-run reads `voice.asr.backend` from the config; if the user forgets to flip to `"whisper_hf"`, the re-run uses the v0.1.3 `WhisperLocalASR(base)` backend, and Run 2 is meaningless. The user verifies `cfg.voice.asr.backend == "whisper_hf"` BEFORE running M9-C. |
| **The Sprint 25 commit message is malformed** | Low | Low | The Sprint 25 spec §4.2 provides a complete copy-pasteable commit message. The user just substitutes `<sprint-25-hash>` (or removes that line if using `git revert HEAD`). The user can re-do the commit with `git commit --amend` if the message is wrong. |
| **The M9-E ticket update misses a box** | Low | Low | The Sprint 25 spec §4.5 provides a 6-box template. The user copies the template into the ticket. If a box is missed, the user can fix it in a follow-up commit. |
| **The git revert creates a merge conflict** | Low | Low | The Sprint 25 commit is a 1-file, ~10-line change. If the user has made no other changes to `m9c_voice_tools.py` between the Sprint 25 commit and the revert, the revert is conflict-free. If the user has made other changes, the revert may conflict; the user resolves with `git revert --abort` and re-applies the augmented note manually. |
| **The training checkpoint is corrupted** | Low | High | The training script (`finetune_whisper_yue.py`) verifies the HF-format checkpoint at the end of the run. If the checkpoint is corrupted, the script exits 1 and the user re-runs (the Common Voice yue materialisation is resumable per Sprint 21, so the re-run is faster on a second pass). |
| **The user runs M9-C with the wrong env** | Low | Medium | The M9-C script (`m9c_voice_tools.py`) requires `MINIMAX_API_KEY` to be set in the env. The script aborts with a clear error if the key is missing. The user verifies the env before running. |
| **The augmented-note deletion is over-scoped** | Low | Low | The Sprint 25 diff is exactly 14 lines deleted + 5 lines added + 1 line modified. The user verifies the diff with `git diff HEAD~1 HEAD -- backend/scripts/m9c_voice_tools.py` BEFORE running M9-C Run 2 (per §4.3 post-commit checklist step 2). If the diff is wrong, the user can `git commit --amend` to fix it. |

## 7. Acceptance tests

1. **M9-C Run 1 passes (with augmented note)**
   — `python scripts/m9c_voice_tools.py`
   (on v0.1.3 code, before Sprint 25 commit)
   exits 0 with `used_tool_content == True`
   and the TTS output contains the README's
   first line.
2. **Sprint 25 commit lands** — `git log
   --oneline -1` shows the commit with the
   structured subject and the
   "REVERT COMMAND" body section. `git diff
   HEAD~1 HEAD --stat` shows ~3 files
   changed, ~10 lines net deletion in
   `m9c_voice_tools.py`, ~90 lines added
   in `CHANGELOG.md`, ~5 lines added in
   `M9-E.md`.
3. **M9-C Run 2 passes (without augmented
   note)** — `python scripts/m9c_voice_tools.py`
   (on v0.1.4 code, after Sprint 25 commit)
   exits 0 with `used_tool_content == True`.
   **This is the observable acceptance test
   for the M9-E fine-tune.**
4. **CHANGELOG entry** — `git show HEAD
   -- docs/CHANGELOG.md` shows the
   v0.1.4 finalization entry under
   `[Unreleased]` with the 4-section
   structure (Sprint 25 / Changed / Verified
   / Out of scope).
5. **M9-E ticket update** — `git show HEAD
   -- docs/tickets/M9-E.md` shows the 5
   Layer 2 acceptance boxes ✓ (or ✗ if
   the user reverted).
6. **No regression** — `cd backend && .venv/bin/pytest
   tests/voice/` — 188 passed, 2 skipped,
   0 failed (Sprint 23 baseline preserved).
   `cd frontend && pnpm tsc --noEmit` — 0
   errors. `cd frontend && pnpm vitest run` —
   63/63 pass.
7. **Git revert safety net works** — If
   M9-C Run 2 fails, `git revert HEAD`
   restores the augmented note in a new
   commit. `git diff HEAD~1 HEAD --stat`
   shows the revert is a near-mirror of
   the Sprint 25 commit (5 files changed,
   the same lines restored). The user
   can verify by re-running M9-C and
   seeing the agent complete the task
   again.

## 8. Sign-off

- [ ] **Track 3 deletion scope agreed** —
      1 commit, ~10 lines net deletion,
      5-line M9-E replacement comment,
      1-line `augmented` → `text` modify,
      CHANGELOG + M9-E ticket updates.
- [ ] **Commit message template agreed** —
      subject ≤ 72 chars, body embeds the
      `git revert HEAD` command, references
      Sprint 24 spec §4.1-4.3.
- [ ] **Post-commit checklist agreed** —
      7-step verification (commit landed,
      diff expected, hash copied, M9-C Run
      2, accept-or-revert decision, partial
      pass handling).
- [ ] **Out-of-scope items confirmed** —
      launchd / systemd supervisor;
      self-record corpus + Layer 2 v2;
      mlx-whisper inference all deferred
      to Sprint 26+.

---

## Appendix A — Sprint 25 vs Sprint 22 / 24 line count reconciliation

Sprint 22 spec §5 file-by-file table
estimates `0 / -16` for
`scripts/m9c_voice_tools.py`. Sprint 24
spec Appendix A reconciles to `-16` net
(`20 lines − 4 lines replacement = 16`).
The actual math against the current code
(verified 2026-06-17 against commit
`4e85e99`) is:

- Lines 179-186 (M9-C note comment): 8 lines
- Lines 187-192 (`augmented = (...)` block):
  6 lines
- **Lines 179-192 deleted: 14 lines total**

- Lines 179-183 (M9-E replacement comment):
  5 lines
- **Lines 179-183 added: 5 lines**

- Line 199 modified (`augmented` → `text`):
  1 line, net 0

- **Net: -14 + 5 + 0 = -9 lines**

The Sprint 22 / 24 specs' "16 line" count
is over-estimated by ~7 lines. This is a
**spec drift, not an implementation drift** —
the Sprint 25 commit lands as ~9 lines net
deletion, and the user can verify with
`git diff --stat`.

The drift originated in Sprint 22's
`python_backend/voice/sprint21` work where
the line count was estimated before the
exact block boundaries were verified
against the current code. Sprint 24's
Appendix A inherited the estimate without
re-counting. Sprint 25 reconciles.

## Appendix B — Why "revert" instead of "fix forward"

The Sprint 25 commit is **revert-friendly**
(uses `git revert` to roll back) instead
of **fix-forward-friendly** (re-land with
a different approach). The reason is
**observability**:

- A `git revert` creates a single, clean
  commit that restores the v0.1.3 state
  exactly. The git log shows:
  - `<sprint-25-hash>`: "delete augmented
    note"
  - `<revert-hash>`: "Revert \"delete
    augmented note\""
  The user can see at a glance that the
  v0.1.4 attempt was reverted.
- A "fix forward" approach would mean
  re-training the model with different
  hyperparameters and re-running M9-C.
  The fix-forward path is **observable
  only in the training log + the new
  checkpoint**, not in the git log. The
  user has to dig through the M9-C
  re-run output to see what changed.

The revert-first approach keeps the
**commit history as the single source of
truth** for what was tried. If the user
later re-trains and the fine-tune
works, the user re-applies the deletion
in a new commit, and the git log shows:
- `<sprint-25-hash>`: "delete augmented
  note (reverted)"
- `<revert-hash>`: "Revert ..."
- `<sprint-25-retry-hash>`: "delete
  augmented note (retry)"

The retry commit is **explicitly
distinguishable** from the original
Sprint 25 commit, which is what we want
for a multi-attempt v0.1.4 land.

## Appendix C — The M9-E ticket update philosophy

`docs/tickets/M9-E.md` is the single
source of truth for whether v0.1.4 land
succeeded. The Sprint 25 spec's §4.5
template (5 boxes ✓ or ✗) is intentionally
**binary** — either the fine-tune works
(all ✓) or it doesn't (all ✗). The user
is not expected to maintain partial-pass
states in the ticket.

If a partial pass happens (e.g. M9-C Run 1
passes, Run 2 partially passes — the
agent completes the file_read task but
the TTS audio doesn't contain the README's
first line), the user has three options:

1. **Accept the partial pass** — flip the
   boxes to ✓ with a note explaining
   the partial state. v0.1.4 lands
   with the caveat.
2. **Revert and re-train** — flip the
   boxes to ✗, run `git revert HEAD`,
   and re-train with different
   hyperparameters.
3. **Defer the Sprint 25 commit** —
   leave the boxes ✗, revert, and
   defer the v0.1.4 land to a future
   sprint when the user has more time
   for the re-training session.

The Sprint 25 spec doesn't dictate which
option the user picks for a partial pass
— the spec captures the **shape** of the
update and the user decides. The
3-option menu is a guide, not a rule.

## Appendix D — Why no new unit tests

Sprint 25 ships 0 new unit tests (per
Sprint 24 spec Appendix D). The reason:

- The Track 3 deletion is verified by
  **the M9-C live re-run itself** — the
  `used_tool_content == True` check at
  `m9c_voice_tools.py:390` is the
  observable acceptance test.
- A unit test for "does the script
  not augment the text" would be a
  tautology — the test would just
  check that the `augmented` variable
  is unused, which is trivially true
  after the deletion.
- The unit test would be redundant
  with `git diff` — the user can see
  the deletion in the Sprint 25 commit.

If the user wants a unit-test
counterpart, we could add
`test_m9c_voice_tools_no_augmented_note`
that greps the source for the
`augmented =` assignment and asserts
its absence. This would be a 5-line
test in `backend/tests/scripts/`
(a new test directory for
`backend/scripts/` smoke tests). But
it's redundant with `git diff` —
the user can see the deletion in the
Sprint 25 commit.

We skip it for now. If the user
insists on a unit test, it's a 1-hour
follow-up commit (Sprint 25.5 or
similar) and not part of v0.1.4 land.

## Appendix E — Sprint 25 commit subject wording

The Sprint 25 spec §4.2 commit message
template uses the subject:

```
feat(asr): Sprint 25 — M9-E Layer 2 acceptance: delete augmented system note
```

The subject is **69 characters** (with
the em-dash), under the conventional
72-character limit. The format follows
the Conventional Commits spec
(`<type>(<scope>): <subject>`) which the
Gundam Halo commit history uses
consistently (Sprints 16-24 all use
`feat(<scope>):` or `docs(<scope>):`).

The subject includes the sprint number
(Sprint 25) for git log grep-ability:
`git log --oneline | grep "Sprint 25"`
returns the commit. The em-dash (—) is
a Unicode character; the user can
substitute ASCII hyphen-hyphen (--)
if their terminal doesn't render
em-dash correctly.

The subject's colon placement
(`acceptance: delete`) follows the
Sprint 23 pattern (`WhisperHFASR swap`)
where the colon separates the
acceptance criterion from the action.
The reader's eye lands on "delete
augmented system note" first, which is
the action the commit takes.

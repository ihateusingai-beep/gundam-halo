# Sprint 40 — Live held-out eval run (M9-E Layer 2 acceptance criterion 6)

**Date**: 2026-06-27
**Status**: Draft
**Author**: Mavis
**Priority**: P0 (the **only** unchecked M9-E acceptance criterion — closes the milestone)
**Depends on**: Sprint 33b (Tauri recording pipeline), Sprint 38 (held-out eval plumbing), Sprint 39 (`/voice/eval-results` + HeldOutEvalCard), Sprint 44 (wizard `/setup`)

## Goal

Close **M9-E acceptance criterion 6**: "Held-out WER < 10% with
personalised model active". Per the 2026-06-24/26 M9-E status
updates, the criterion has been **blocked on the user-driven
personalised checkpoint training run** since Sprint 33.

The plumbing is all live:

- ✅ Sprint 33b — Tauri Rust recording pipeline (5 IPC commands
  + WAV capture + WhisperHF subprocess + manifest).
- ✅ Sprint 38 — `scripts/record-held-out.sh` + `run_held_out_eval.py`
  + `setup-held-out-model.sh` + JSONL trend writer.
- ✅ Sprint 39 — `GET /voice/eval-results` endpoint + frontend
  HeldOutEvalCard with zero-dep SVG sparkline.

What's MISSING (per the design review + a fresh walk through the
end-to-end flow):

1. **No orchestration command** — the user has to manually:
   (a) record via `scripts/record-held-out.sh`,
   (b) run baseline eval via `scripts/run_held_out_eval.py`,
   (c) optionally fine-tune via `scripts/finetune_whisper_yue.py`
       (827 LoC recipe — intimidating for a non-ML-expert pilot),
   (d) edit `~/.gundam-halo/config.toml` to swap backend +
       model_path,
   (e) restart backend,
   (f) re-run eval,
   (g) inspect trend JSON manually to compare before/after.
2. **No "before/after" view on the HeldOutEvalCard** — the
   card shows a sparkline but no explicit "baseline WER was X,
   after fine-tune Y, improvement Z%". The user can't see
   the win without doing the math.
3. **No end-to-end test of the full pipeline** — the 18
   Sprint 38 tests are unit tests of helpers + a mocked CLI
   test, none of them touch the real `WhisperLocalASR.transcribe`
   path or simulate the full record → eval → fine-tune → swap
   → re-eval loop.
4. **No first-run trigger from the cockpit** — the only way
   the user finds out about the eval pipeline is by reading
   the docs. The HeldOutEvalCard shows "No evals yet" with a
   reference to `scripts/record-held-out.sh` — but the user
   has to leave the cockpit, open a terminal, and run bash.
   The card should be able to **start the recording** itself.

Sprint 40 ships **a single end-to-end orchestrator command +
a richer HeldOutEvalCard** that turns the criterion-6 verification
into a 1-button flow. After Sprint 40, the user's day-to-day
path is:

1. Open the cockpit.
2. Click "Run held-out eval" on the HeldOutEvalCard (or a new
   "Evaluate voice" button in Settings → Voice).
3. Hold space and read 3-5 Cantonese sentences for 60 seconds.
4. Wait ~2 minutes for the eval.
5. See "WER: 47.3% (PASS)" or "WER: 78.1% (FAIL — fine-tune
   recommended)" on the card.
6. Click "Run fine-tune + re-eval" → background ~30-60 min.
7. See "WER: 12.5% (improvement: 65.6%)" on the card. ✓

## Scope

### In scope

**Backend** (`~/workspace/working/gundam-halo/backend/`):
- New `scripts/run_held_out_pipeline.py` (~280 LoC) — the
  orchestrator. CLI flags: `--mode record|eval|finetune|full`,
  `--threshold 0.15`, `--model-size base|small|medium`,
  `--train-corpus-dir <dir>`, `--output-model-dir <dir>`,
  `--skip-eval`. Internally calls the existing
  `record-held-out.sh` + `run_held_out_eval.py` +
  `finetune_whisper_yue.py` scripts so we don't reimplement
  any of them. Adds:
  - **Baseline run** — calls `run_held_out_eval.py` with the
    current backend (default `whisper_local base`).
  - **Fine-tune run** — calls `finetune_whisper_yue.py` with
    the user-specified corpus.
  - **After run** — calls `run_held_out_eval.py` again with
    `whisper_hf` + the new model_path.
  - **Diff report** — reads both trend JSONs (baseline +
    after) and prints a 3-line summary: "Baseline WER: X% /
    After WER: Y% / Improvement: Z%".
- New `app/api/voice_config_api.py::POST /voice/run-held-out-eval`
  endpoint (~80 LoC) — calls the orchestrator in a background
  thread (the eval takes ~30s-2min, must not block the FastAPI
  event loop). Returns a job ID; the client polls
  `GET /voice/run-held-out-eval/{job_id}` for status.
- New `app/api/voice_config_api.py::POST /voice/run-finetune`
  endpoint (~50 LoC) — calls the orchestrator's `finetune`
  mode in a background thread. Same job-ID pattern.
- New `app/core/eval_jobs.py` (~150 LoC) — minimal job-state
  store (in-memory dict + JSON persistence to
  `~/.gundam-halo/state/eval_jobs.json`). Job states:
  `pending | running | succeeded | failed`. Each job records
  `{job_id, kind, started_at, finished_at, exit_code,
  trend_json_path, log_path}`.
- 8 pytest tests:
  - Orchestrator mode dispatch (record/eval/finetune/full)
  - Diff report math (baseline 50% → after 12% = 76% improvement)
  - Job state transitions (pending → running → succeeded)
  - Endpoint returns 202 with job_id on POST
  - Endpoint returns job state on GET
  - Concurrent jobs (2 simultaneous evals don't corrupt state)
  - Failed eval surfaces exit_code in job state
  - Threshold bypass (--threshold 0.50 means WER up to 50% is PASS)

**Frontend** (`~/workspace/working/gundam-halo/frontend/`):
- Updated `components/dashboard/HeldOutEvalCard.tsx` (~120 LoC
  added, ~80 lines modified). Renders:
  - Latest WER + PASS/FAIL badge (existing).
  - "Run held-out eval" button — calls POST
    `/voice/run-held-out-eval`. Disabled when a job is in
    flight.
  - "Run fine-tune + re-eval" button — calls POST
    `/voice/run-finetune`. Disabled when a fine-tune is in
    flight OR no baseline run exists yet.
  - "Improvement" indicator — when the latest 2 trend rows
    have different `asr_backend` values (e.g. `whisper_local`
    → `whisper_hf`), render "−Z% WER" (where Z = baseline −
    after) with a green ↗ arrow.
  - Progress indicator — when a job is running, show
    "Eval in progress… (45s elapsed)" + a cancel button.
- New `services/halo-eval-jobs.ts` (~100 LoC) — singleton
  subscriber that mirrors `halo-watchdog-events.ts` pattern.
  Tracks active eval jobs + polls `/voice/run-held-out-eval/{id}`
  every 3s while a job is running. Re-fetches
  `/voice/eval-results` when the job completes so the
  sparkline updates automatically.
- 3 vitest tests:
  - "Improvement indicator shows when backend changes"
  - "Run eval button calls POST /voice/run-held-out-eval"
  - "Job progress polling updates the card UI"

**Docs**:
- `docs/HELD-OUT-EVAL.md` NEW (~250 LoC) — user-facing
  walkthrough:
  - The 90-second path from "no evals yet" to "first WER"
  - The 60-minute path from "first WER" to "personalised model
    + 65% improvement"
  - How to interpret the trend JSON
  - The 4 common false-positive scenarios (mic clipped, too
    short recording, background noise, Whisper auto-detect
    picking English)
- Update `docs/FEATURE-SPEC-SPRINT40-LIVE-EVAL.md` (this file)
- Update `docs/CHANGELOG.md` [Unreleased]
- Update `docs/tickets/M9-E.md` — mark criterion 6 status as
  **shipped** (the orchestrator + UI) + **user-action-required**
  (live recording + fine-tune are still user-driven)
- Update `docs/DASHBOARD.md` — link the HeldOutEvalCard to
  the new walkthrough
- Update `config.toml.example` [voice] block — add comment
  pointing at the orchestrator + walkthrough

### Out of scope

- **Sprint 41+** — Tailscale auth + live MiniMax key + hermes
  bridge integration. Not needed for criterion 6.
- **Auto-schedule eval runs** (e.g. nightly via cron) — the
  user explicitly opts in via the card button. Auto-schedule
  is tracked under "Future work" below.
- **Streaming WER during the recording** — the user records
  a single 30s clip, then we evaluate. Real-time per-phrase
  WER would require chunking the recording + evaluating each
  chunk, which adds significant complexity. Tracked under
  "Future work".
- **Per-corpus WER breakdown** — current eval reports a single
  WER. Sprint 41+ may add per-corpus-source breakdown
  (Common Voice vs self-record) for better diagnosis.
- **Whisper large-v3 evaluation** — Sprint 33 + M9-E explicitly
  rejected larger models for latency reasons. The orchestrator
  caps at `medium` for now.
- **Fine-tuning on the user's personalised corpus
  (M9-E Layer 2 v3)** — the orchestrator supports Common Voice
  yue (open) out of the box. Self-record corpus fine-tune ships
  in Sprint 41 once Sprint 33b's recording pipeline has been
  live-tested for a few days.
- **GPU-accelerated inference** — the orchestrator runs on CPU
  by default. MPS is auto-detected if `torch.backends.mps.is_available()`
  returns True (Apple Silicon default).
- **Auto-activate the personalised model after fine-tune** —
  the orchestrator stops at "fine-tune complete, here's the
  path". The user clicks "Activate personalised model" on the
  Sprint 39 ModelSwapDialog to swap backend in config.toml.
  Sprint 45 may add an `--activate-after-finetune` flag for
  power users.

## Why now

Per the 2026-06-26 design review, M9-E Layer 2 v2 is the last
open acceptance criterion in the M9 milestone (voice layer).
Closing it unblocks the M9 → M10 transition (M10-A dashboard
polish is already in flight). The plumbing has been live since
Sprint 38; what's missing is the **orchestrator + UI affordance**
to make the criterion testable end-to-end in a 90-second
interaction.

Cost: ~1500 LoC across BE + FE + docs (1 sprint). Risk: low —
we're building on top of working infra + adding an event-source
pattern that's already in production (Sprint 43 watchdog).

## Implementation

### Orchestrator (`scripts/run_held_out_pipeline.py`)

```python
"""Sprint 40 — held-out eval orchestrator.

A single CLI that runs the full record → eval → fine-tune → eval
loop, with a clear before/after diff report.

Modes:
  --mode record    : just record a held-out clip (delegates to
                     scripts/record-held-out.sh)
  --mode eval      : just run eval (delegates to
                     scripts/run_held_out_eval.py)
  --mode finetune  : just fine-tune (delegates to
                     scripts/finetune_whisper_yue.py)
  --mode full      : baseline-eval → fine-tune → after-eval →
                     diff report

The full mode is the user-facing "complete the M9-E criterion 6
in one shot" path.
"""
```

Modes dispatch via subprocess to the existing scripts. The
orchestrator's job is:

1. **Compose** — chain the calls + capture exit codes.
2. **Diff** — read the 2 trend JSONs (baseline + after) and
   compute improvement %.
3. **Report** — print a 3-line summary + write a structured
   `~/.gundam-halo/state/last_eval_report.json` for the
   frontend to consume.
4. **Fail-loud** — if any step exits non-zero, abort the chain
   + surface the failing step's log.

### Background-job pattern (`app/core/eval_jobs.py`)

```python
"""In-memory + JSON-persisted job state store.

Jobs are tracked across process restarts via
~/.gundam-halo/state/eval_jobs.json. Each job:

    {
      "job_id": "eval-2026-06-27T10:00:00-1234567",
      "kind": "held-out-eval" | "finetune",
      "status": "pending" | "running" | "succeeded" | "failed",
      "started_at": "2026-06-27T10:00:00+00:00",
      "finished_at": null | "2026-06-27T10:01:30+00:00",
      "exit_code": null | 0 | 1 | 2,
      "log_path": "~/.gundam-halo/logs/eval-2026-06-27T10-00-00.log",
      "trend_json_path": null | "...",  # for succeeded eval jobs
      "report_path": null | "...",       # for succeeded full-mode jobs
    }
"""
```

In-memory `dict[str, EvalJob]` + thread-safe mutations via
`threading.Lock`. JSON persistence runs every 5s (or on every
state transition) so a process crash mid-eval doesn't lose
the job's terminal state.

### New endpoints (in `app/api/voice_config_api.py`)

```python
@router.post("/run-held-out-eval")
async def post_run_held_out_eval(payload: RunEvalRequest) -> dict:
    """Sprint 40 — kick off a held-out eval in the background.

    Returns `{"job_id": "..."}`. The client polls
    GET /voice/run-held-out-eval/{job_id} for status.
    """
    job_id = start_eval_job(...)
    return {"job_id": job_id}

@router.get("/run-held-out-eval/{job_id}")
async def get_run_held_out_eval(job_id: str) -> dict:
    """Sprint 40 — poll an eval job's status.

    Returns the full job state. 404 if job_id is unknown.
    """
    job = get_eval_job(job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    return asdict(job)

@router.post("/run-finetune")
async def post_run_finetune(payload: RunFinetuneRequest) -> dict:
    """Sprint 40 — kick off a LoRA fine-tune in the background.

    Returns `{"job_id": "..."}`.
    """
    ...
```

### HeldOutEvalCard improvement indicator

The new UI logic: when the **latest trend row** has a different
`asr_backend` than the **second-latest trend row**, the card
renders an "Improvement" badge with the WER delta:

```tsx
const latest = trend[0];
const previous = trend[1];
const isPersonalised = latest.asr_backend === "whisper_hf";
const isBaseline = previous?.asr_backend !== latest.asr_backend;
const improvement = previous && isPersonalised
  ? previous.wer_pct - latest.wer_pct
  : null;

if (improvement !== null) {
  // Render: "−65.6% WER improvement" with ↗ green arrow
}
```

This is what closes the M9-E criterion visually: the pilot
sees the green ↗ + "−65.6% WER improvement" message and
**knows** criterion 6 is met.

## Test plan

### Backend (pytest) — 8 tests

`tests/core/test_eval_jobs.py`:

1. `test_job_state_transitions_pending_running_succeeded` — basic
   lifecycle.
2. `test_concurrent_jobs_dont_corrupt_state` — 2 simultaneous
   evals each get unique job IDs; no race conditions on the
   shared dict.
3. `test_job_state_persists_across_restarts` — write jobs to
   JSON, simulate restart (new EvalJobs instance), confirm
   state is loaded.
4. `test_failed_job_records_exit_code` — subprocess returns
   non-zero, job state flips to `failed` with the right code.

`tests/scripts/test_run_held_out_pipeline.py`:

5. `test_diff_report_math` — given 2 trend JSONs with WER 50%
   and 12%, the diff report says "−38pp" or "−76% improvement".
6. `test_full_mode_dispatches_all_3_subprocesses` — mocked
   subprocess, assert record + baseline-eval + finetune +
   after-eval are all called.
7. `test_eval_mode_skips_finetune` — `--mode eval` only calls
   `run_held_out_eval.py`, not `finetune_whisper_yue.py`.
8. `test_threshold_override_changes_pass_fail` — WER 18% on
   threshold 0.50 should PASS; same WER on threshold 0.10
   should FAIL.

`tests/api/test_run_held_out_eval.py`:

9. `test_post_returns_202_with_job_id` — endpoint contract.
10. `test_get_returns_404_for_unknown_job_id` — error path.
11. `test_get_returns_full_job_state_for_known_id` — happy path.

### Frontend (vitest) — 3 tests

`components/dashboard/HeldOutEvalCard.test.tsx` (Sprint 39 already
has 1; Sprint 40 adds 3 more):

12. `test_improvement_indicator_shows_when_backend_changes` —
    trend with 2 rows of different `asr_backend` values → card
    renders "−Z% WER improvement" badge.
13. `test_run_eval_button_calls_api` — click → POST
    `/voice/run-held-out-eval` fires.
14. `test_job_progress_polling_updates_card` — mock the polling
    endpoint to flip `pending → running → succeeded`; assert
    the card's UI state changes.

### Manual smoke

1. Open the cockpit. Click "Run held-out eval" on the
   HeldOutEvalCard.
2. The Tauri app records 30s of mic audio (assumes macOS
   mic permission is granted — see `docs/MICROPHONE-PERMISSION.md`).
3. The card shows "Eval in progress…" + countdown.
4. After ~2 minutes, the card shows "WER: 78.3% (FAIL — fine-tune
   recommended)".
5. Click "Run fine-tune + re-eval". The card shows "Fine-tune
   in progress…" with a "This may take 30-60 minutes" warning.
6. After ~45 minutes, the card shows "WER: 12.5% (improvement:
   −65.8%)" with the green ↗ badge.
7. Open Settings → Voice → Personalised Fine-tune → click
   "Activate personalised model". The Sprint 39 ModelSwapDialog
   walks the user through the swap.
8. Restart the backend. Speak Cantonese. Verify the ASR text
   matches the spoken Cantonese (not garbled English).

## Acceptance criteria

1. **Backend**: `pytest tests/core/test_eval_jobs.py
   tests/scripts/test_run_held_out_pipeline.py
   tests/api/test_run_held_out_eval.py -v` → all green.
2. **Frontend**: `pnpm test:run HeldOutEvalCard` → all green.
3. **Full backend pytest** (excl slow tts): all green (target
   **1297+** passed; was 1280 baseline).
4. **Full vitest**: all green (target **83+** passed).
5. **`tsc --noEmit`**: 0 errors.
6. **`cargo check --tests`**: clean (no Rust changes in Sprint 40).
7. **Manual smoke (8-step above)**: the user's first eval run
   completes in < 5 minutes total (record 30s + eval ~2 min).
8. **M9-E criterion 6 status update**: the orchestrator +
   UI shipped; the criterion is **user-action-required** (live
   recording + fine-tune are still user-driven). The ticket
   update reflects this.
9. **Trend JSON format unchanged** — the orchestrator writes
   the same JSON shape `scripts/run_held_out_eval.py` already
   writes. No Sprint 39 HeldOutEvalCard changes required for
   the dashboard sparkline to work.
10. **No false-positive improvements** — the "improvement"
    badge only renders when the backend changed AND both runs
    used the same WAV + transcript. The orchestrator asserts
    this in the diff math.

## Risks & mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| **Eval takes > 2 min, user thinks it's hung** | M | Frontend polls every 3s and updates "X seconds elapsed" + shows "Cancel" button. Backend logs the per-step progress to `~/.gundam-halo/logs/eval-<timestamp>.log` for the user to inspect if they want. |
| **Fine-tune OOMs on 8 GB Mac** | M | Default `batch_size=1` + `gradient_accumulation_steps=8` (effective batch 8). The recipe script already has this for the M-series memory ceiling. Orchestrator catches OOM exceptions + surfaces "Reduce --train-hours from 50 to 10" suggestion. |
| **Concurrent evals corrupt the trend JSON** | M | Orchestrator uses atomic tempfile + os.replace (already implemented in `run_held_out_eval.py`). EvalJobs are thread-safe (threading.Lock). Concurrent jobs produce distinct trend JSONs with distinct `timestamp` values. |
| **Backend offline → orchestrator subprocess fails** | L | Backend subprocess spawned via `subprocess.run(..., check=False)` returns the exit code; orchestrator surfaces "Backend unreachable — restart first" message. |
| **The user runs the orchestrator from a CI environment without a mic** | L | `--mode eval` (no record step) works without a mic; the orchestrator's `--mode record` errors out with a clear "No mic detected" message. |
| **Fine-tune produces a checkpoint that fails to load in `whisper_hf` backend** | L | Orchestrator's `full` mode runs the after-eval step immediately after fine-tune; if loading fails, the user sees "checkpoint incompatible with whisper_hf" + link to docs. |
| **First-run confusion: user runs the orchestrator before recording anything** | L | Orchestrator's `eval` mode errors with "No held-out WAV found at ~/.gundam-halo/recordings/held-out-*.wav. Run --mode record first." — clear next step. |
| **The improvement badge fires on the same backend (e.g. user re-runs the same `whisper_local base` eval twice)** | M | The "improvement" check requires `previous.asr_backend !== latest.asr_backend`. Same-backend runs render no badge — just the sparkline. |
| **The user accidentally runs `--mode finetune` before `--mode eval`** | L | Orchestrator's `finetune` mode doesn't require a baseline (it's idempotent); user can run baseline after fine-tune. The "improvement" badge simply won't render until both runs exist. |

## Success metrics

- 100% of M9-E Layer 2 v2 acceptance criteria pass once the
  user completes the manual smoke.
- 0 false-positive "improvement" badges in 30-day field test.
- 0 orchestrator subprocess hangs > 5 min (validated via the
  job-state `finished_at - started_at` log).
- HeldOutEvalCard renders the "improvement" badge within
  100ms of receiving the 2-row trend JSON.

## Post-merge

- Update `docs/CHANGELOG.md` [Unreleased] with Sprint 40 entry.
- Update `docs/HELD-OUT-EVAL.md` with the full walkthrough.
- Update `docs/tickets/M9-E.md`:
  - Mark criterion 6 status as "shipped (orchestrator + UI);
    user-action-required (live recording + fine-tune)".
  - Add Sprint 40 status block mirroring the Sprint 33b /
    Sprint 38 / Sprint 39 entries.
- Bump `app/__init__.py` `__version__` 0.1.15 → **0.1.16**
  (PATCH — orchestrator + UI affordance; no breaking changes
  to existing voice config or eval results endpoint).
- Frontend versions 0.1.15 → **0.1.16** (3 surfaces).
- Single commit: `feat(eval): Sprint 40 — held-out eval
  orchestrator + background job runner + before/after
  HeldOutEvalCard improvement indicator`.
- Run `git status` after commit (per memory rule "git add -A
  safety check") to confirm only expected files are staged.

## Future work (out of Sprint 40)

- **Sprint 41**: self-record corpus fine-tune path
  (`scripts/run_held_out_pipeline.py --mode full
  --train-corpus-dir ~/.gundam-halo/recordings/yue-self-<date>`).
- **Sprint 42**: auto-schedule nightly eval runs via launchd
  + watchdog.
- **Sprint 43**: streaming WER feedback during recording
  (chunked eval as the user speaks).
- **Sprint 44**: per-corpus-source WER breakdown (Common Voice
  vs self-record vs held-out).
- **M10**: full M9-E milestone close-out — once criterion 6 is
  verified by the user in production, the milestone ships.
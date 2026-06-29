# Sprint 46 — Per-corpus WER breakdown + corpus-tagged eval history

**Date**: 2026-06-29
**Status**: Draft
**Author**: Mavis
**Priority**: Medium (deepens M9-E insight; depends on Sprint 45 corpus auto-detect)
**Depends on**: Sprint 38 (held-out eval), Sprint 39 (eval-results endpoint),
Sprint 40 (orchestrator), Sprint 45 (corpus auto-detect + `/voice/self-record-corpora`)

## Goal

Today (post-Sprint 45) the HeldOutEvalCard sparkline shows ONE number per
eval run — the **average WER** across whatever the held-out WAV was.
That hides the corpus dimension:

- Was the fine-tune eval'd on the user's **own voice** (self-record)?
- Was it Common Voice yue test set?
- Was it a synthetic batch?

When the user fine-tunes on `yue-self-2026-06-27/`, the next eval still
just shows "8.0% WER" without indicating **which corpus** the WER was
measured against. The pilot can't tell whether the improvement came from
"the model knows my voice better" or "the test happened to be easier".

Sprint 46 adds a `corpus_id` field to the eval schema, the CLI tags it
automatically from `--train-corpus-dir` / `--wav-path` parents, the
backend computes per-corpus breakdowns, and the dashboard renders a
**stacked bar chart** showing WER per corpus over the last N runs.

## Why now

- Sprint 45 already added corpus auto-detect + the new endpoint — the
  infra is in place to know **which corpus** the user ran against.
- The user has likely been seeing a single WER number and wondering
  "but is the personalised model actually learning *my* voice, or
  is the test set easier?" — the per-corpus breakdown answers that
  question with data.
- The Sprint 40 orchestrator already takes `--train-corpus-dir` and
  `--base-model-path`; extending it to pass `--corpus-id` to the
  eval script is a 5-line change.

## Design

### 1. `EvalResult` schema extension — additive, backwards compat

```python
# backend/app/voice/held_out_eval.py — Sprint 46 change

@dataclass
class EvalResult:
    """One held-out eval run. JSON-serialisable for trend tracking.

    Sprint 46: adds optional `corpus_id` so the dashboard can
    break down WER per training corpus. Existing JSONs (without
    the field) parse fine — the dataclass uses `corpus_id: str = ""`
    as the default.
    """
    timestamp: str
    wav_path: str
    transcript_path: str
    reference: str
    hypothesis: str
    wer: float
    threshold: float
    passed: bool
    duration_s: float = 0.0
    asr_backend: str = ""
    notes: str = ""
    corpus_id: str = ""  # Sprint 46 NEW — empty string means "unattributed"
```

The existing `_parse_summary` already uses `r.get("corpus_id", "")`,
so old JSONs parse without any migration.

### 2. `--corpus-id` CLI flag on `run_held_out_eval.py`

```python
# backend/scripts/run_held_out_eval.py — Sprint 46 change

parser.add_argument(
    "--corpus-id",
    type=str,
    default="",
    help=(
        "Optional tag identifying which corpus the eval WAV came from. "
        "Format convention: 'self:<date>' (self-record), "
        "'common-voice-yue:<version>' (Common Voice), "
        "'synthetic:<name>' (test fixtures). Empty string = "
        "unattributed (legacy runs)."
    ),
)
```

The flag is forwarded to the `EvalResult.now(...)` call as
`corpus_id=args.corpus_id`.

### 3. Orchestrator auto-derives `--corpus-id` from `--train-corpus-dir`

```python
# backend/scripts/run_held_out_pipeline.py — Sprint 46 change

def _corpus_id_from_train_dir(train_dir: Path) -> str:
    """Derive a corpus_id from the --train-corpus-dir path.

    Convention:
      - `.../yue-self-YYYY-MM-DD/`  → "self:YYYY-MM-DD"
      - `.../common-voice-yue/`     → "common-voice-yue"
      - any other path              → "self:<basename>" (fallback)
    """
    name = train_dir.name
    if name.startswith("yue-self-"):
        return f"self:{name[len('yue-self-'):]}"
    if name.startswith("common-voice-yue"):
        return name
    return f"self:{name}"


def _cmd_eval(args, halo_home, log_path):
    cmd = [
        "python", str(script),
        "--threshold", str(args.threshold),
    ]
    corpus_id = _corpus_id_from_train_dir(args.train_corpus_dir)
    if corpus_id:
        cmd += ["--corpus-id", corpus_id]
    ...
```

Convention rationale:
- `"self:<date>"` — explicit prefix prevents confusion with Common Voice
  (a `yue-self-2026-06-27` eval shouldn't be lumped with Common Voice
  v11 results, even if both have WER < 10%).
- `"self:<basename>"` fallback for unusual corpus dir names.

### 4. New `GET /voice/eval-corpus-breakdown` endpoint

```python
# backend/app/api/voice_config_api.py — Sprint 46 NEW endpoint

@router.get("/voice/eval-corpus-breakdown")
async def get_eval_corpus_breakdown(limit: int = 20) -> dict[str, Any]:
    """Per-corpus WER breakdown for the HeldOutEvalCard stacked chart.

    Returns:
        {
          "by_corpus": {
            "self:2026-06-27": {
              "run_count": 3,
              "latest_wer_pct": 8.0,
              "best_wer_pct": 6.5,
              "avg_wer_pct": 7.8,
              "first_seen_ms": 1782408000000,
              "latest_seen_ms": 1782500000000,
              "passed": true
            },
            "common-voice-yue": {
              "run_count": 1,
              ...
            }
          },
          "timeline": [
            {
              "timestamp": "2026-06-27T10:00:00+00:00",
              "timestamp_ms": 1782408000000,
              "wer_pct": 12.0,
              "corpus_id": "common-voice-yue",
              "asr_backend": "whisper_local"
            },
            ...
          ],
          "total_runs": 4
        }

    - `by_corpus`: one entry per unique corpus_id seen in the last
      `limit` runs. Stats computed across only THAT corpus's runs.
    - `timeline`: every run in chronological order (oldest first) with
      its corpus_id. Drives the stacked bar chart.
    - Empty strings (legacy unattributed runs) are bucketed under the
      synthetic key `"unattributed"` so they don't disappear.

    Graceful: missing results dir → `{by_corpus: {}, timeline: [],
    total_runs: 0}`. Malformed JSONs skipped.
    """
    from app.voice.held_out_eval import (
        held_out_results_dir,
        load_eval_history,
    )
    rows = load_eval_history(held_out_results_dir(), limit=limit)
    ...
```

Implementation details:
- Iterate `load_eval_history()` once, build both `by_corpus` (dict of
  corpus_id → stats) and `timeline` (one row per run).
- Sort `by_corpus` by `latest_seen_ms` descending (most recently
  active corpus first).
- Sort `timeline` by `timestamp_ms` ascending (oldest → newest for
  left-to-right chart rendering).
- `corpus_id=""` → bucket as `"unattributed"`.

### 5. HeldOutEvalCard — stacked bar chart

```tsx
// frontend/src/components/dashboard/HeldOutEvalCard.tsx — Sprint 46 change

// New state: per-corpus breakdown for the stacked chart.
const [corpusBreakdown, setCorpusBreakdown] = useState<
  CorpusBreakdownResponse | null
>(null);

const fetchCorpusBreakdown = useCallback(async () => {
  try {
    const res = await api.getEvalCorpusBreakdown(limit: 20);
    setCorpusBreakdown(res);
  } catch (e) {
    console.warn("[HeldOutEvalCard] failed to fetch breakdown:", e);
  }
}, []);

// Fetch alongside the existing eval-results poll.
useEffect(() => {
  void fetchCorpusBreakdown();
  const id = setInterval(fetchCorpusBreakdown, POLL_INTERVAL_MS);
  return () => clearInterval(id);
}, [fetchCorpusBreakdown]);

// In the ready branch, just below the existing sparkline:
{corpusBreakdown && corpusBreakdown.timeline.length > 1 && (
  <CorpusBreakdownChart
    timeline={corpusBreakdown.timeline}
    byCorpus={corpusBreakdown.by_corpus}
    threshold={threshold}
  />
)}
```

`CorpusBreakdownChart` component (NEW, ~80 LoC):
- Recharts `<BarChart>` with `<Bar dataKey="wer_pct">` and one
  `<Cell>` per data point, coloured by `corpus_id` (deterministic
  hash → CSS var).
- Y-axis 0% → max(threshold×2, max WER).
- X-axis: timestamps (formatted as MM-DD).
- Tooltip on hover: shows corpus_id + WER + asr_backend.

### 6. Corpus colour palette

```tsx
// frontend/src/components/dashboard/CorpusBreakdownChart.tsx

const CORPUS_COLORS = [
  "var(--accent)",     // cyan — primary
  "var(--success)",    // green
  "var(--warning)",    // amber
  "var(--danger)",     // rose
  "var(--text-muted)", // grey — unattributed fallback
  "#a78bfa",           // purple
  "#fb923c",           // orange
] as const;

// Stable hash → palette index. Same corpus always gets the same
// colour across refreshes.
function corpusColor(corpus_id: string): string {
  if (!corpus_id || corpus_id === "unattributed") {
    return CORPUS_COLORS[4];
  }
  let hash = 0;
  for (let i = 0; i < corpus_id.length; i++) {
    hash = (hash * 31 + corpus_id.charCodeAt(i)) >>> 0;
  }
  return CORPUS_COLORS[hash % 4];  // first 4 are theme colours
}
```

7 corpus colours handles up to 6 unique corpora + 1 unattributed
fallback. Beyond that, the hash rotates among the 4 theme colours
(might collide — acceptable for v1; rare in practice).

### 7. Legend chip row

```tsx
// Below the chart, render one chip per corpus in `by_corpus`:
// [● self:2026-06-27  3 runs · avg 7.8% WER]  [● unattributed  1 run · 12.0%]
// Each chip is clickable to scroll the cockpit to the relevant
// section (future Sprint 47+).
```

### 8. CLI power-user `--corpus-id` override

The CLI flag is **always** overridable:
```bash
.venv/bin/python scripts/run_held_out_eval.py \
    --wav /path/to/held.wav \
    --corpus-id "synthetic:test-fixture-42"
```

Used by the pytest suite + future tests that want deterministic
corpus tagging independent of the path.

## Files to create / modify

### Backend (~250 LoC)

- `backend/app/voice/held_out_eval.py` (modify — add
  `corpus_id: str = ""` to `EvalResult`; update `_parse_summary`
  with the new field's default).
- `backend/scripts/run_held_out_eval.py` (modify — add
  `--corpus-id` CLI flag; forward to `EvalResult.now(...)`).
- `backend/scripts/run_held_out_pipeline.py` (modify — add
  `_corpus_id_from_train_dir()` helper; auto-derive in
  `_cmd_eval` + `_cmd_finetune`).
- `backend/app/api/voice_config_api.py` (modify — new
  `GET /voice/eval-corpus-breakdown` endpoint + helper).

### Frontend (~200 LoC)

- `frontend/src/components/dashboard/CorpusBreakdownChart.tsx`
  NEW (~140 LoC — Recharts stacked bar + tooltip + legend chips).
- `frontend/src/components/dashboard/HeldOutEvalCard.tsx`
  (modify — fetch breakdown alongside eval-results; render
  the chart below the existing sparkline).
- `frontend/src/lib/api.ts` (modify — add
  `getEvalCorpusBreakdown(limit?: number): Promise<CorpusBreakdownResponse>`).
- `frontend/src/types/api.ts` (modify — add
  `CorpusBreakdown` + `CorpusBreakdownResponse` interfaces).

### Docs (~200 LoC)

- `docs/HELD-OUT-EVAL.md` (modify — add "Per-corpus breakdown"
  section: how the breakdown is computed, the `corpus_id`
  convention, when to use `--corpus-id` override).
- `docs/FEATURE-SPEC-SPRINT46-PER-CORPUS-WER.md` (this file).
- `docs/CHANGELOG.md` (entry under [Unreleased]).

### Tests (~16 new tests)

- `backend/tests/voice/test_held_out_eval.py` (extend Sprint 38 file — +3 tests):
  - `test_corpus_id_round_trips_through_json` — write EvalResult
    with corpus_id, serialise, re-parse, assert equal.
  - `test_corpus_id_defaults_to_empty_string` — legacy JSON
    without the field parses with `corpus_id=""`.
  - `test_load_eval_history_includes_corpus_id` — verify the
    dashboard dict shape exposes the field.

- `backend/tests/scripts/test_run_held_out_eval.py` (extend Sprint 38 file — +2 tests):
  - `test_corpus_id_flag_forwarded_to_eval_result` — `--corpus-id
    "self:2026-06-27"` → EvalResult.corpus_id == "self:2026-06-27".
  - `test_default_corpus_id_is_empty_string` — no flag → `""`.

- `backend/tests/scripts/test_run_held_out_pipeline.py` (extend Sprint 45 file — +4 tests):
  - `test_corpus_id_derived_from_yue_self_dir` —
    `train_dir=yue-self-2026-06-27/` → eval CLI gets
    `--corpus-id "self:2026-06-27"`.
  - `test_corpus_id_fallback_for_unusual_dir_name` —
    `train_dir=foo-bar/` → `self:foo-bar`.
  - `test_orchestrator_passes_explicit_corpus_id_flag` —
    `--train-corpus-dir=...` still auto-tags (overrides nothing;
    the orchestrator ALWAYS derives).
  - `test_empty_train_corpus_dir_yields_empty_corpus_id` —
    empty train_dir → no `--corpus-id` flag (defensive).

- `backend/tests/api/test_voice_corpus_breakdown.py` NEW
  (~120 LoC, 4 tests):
  - `test_empty_results_dir_returns_empty_breakdown`.
  - `test_single_corpus_breakdown_basic` — 3 runs all tagged
    `self:2026-06-27` → by_corpus has 1 entry with run_count=3,
    avg_wer_pct computed correctly.
  - `test_multi_corpus_breakdown_isolates_stats` — 2 runs on
    self + 1 run on common-voice-yue → by_corpus has 2 entries
    with per-corpus averages.
  - `test_unattributed_runs_bucketed_under_key` — 1 legacy run
    with `corpus_id=""` → by_corpus[`"unattributed"`] exists.

- `frontend/src/components/dashboard/CorpusBreakdownChart.test.tsx`
  NEW (~80 LoC, 3 tests):
  - `test_renders_one_bar_per_timeline_entry`.
  - `test_legend_chips_show_run_count_and_avg_wer`.
  - `test_corpus_color_hash_is_stable` — same corpus_id →
    same colour across renders.

## Acceptance criteria

- [ ] `EvalResult.corpus_id` round-trips through JSON
  (write → parse → equal).
- [ ] Legacy JSONs (without `corpus_id`) parse with `corpus_id=""`
  (no migration needed).
- [ ] `run_held_out_eval.py --corpus-id "self:2026-06-27"`
  produces an EvalResult with that corpus_id.
- [ ] `run_held_out_pipeline.py --train-corpus-dir ...`
  auto-derives `--corpus-id "self:YYYY-MM-DD"` for yue-self
  dirs and forwards it to the eval subprocess.
- [ ] `GET /voice/eval-corpus-breakdown?limit=20` returns
  `{by_corpus: {}, timeline: [], total_runs: 0}` on a fresh
  HALO_HOME.
- [ ] Multiple corpora → `by_corpus` has one entry per unique
  corpus_id with isolated stats.
- [ ] HeldOutEvalCard renders the stacked bar chart with
  one bar per run, coloured by corpus_id, with a tooltip
  on hover.
- [ ] Legend chips show corpus name + run count + avg WER.
- [ ] Full backend pytest (excl slow tts) stays green:
  **+13 new tests** vs Sprint 45 baseline of 1330.
- [ ] Frontend tsc 0 errors + vitest +3 new tests
  (101 → 104).
- [ ] `cargo check --tests` clean.

## Version bump

`__version__` 0.1.18 → **0.1.19** (PATCH bump per Mavis memory rule —
additive schema extension + new endpoint + new chart. No new
user-facing feature, just deeper insight into existing eval data.

3 surfaces synced:
- `backend/app/__init__.py` (single source of truth)
- `frontend/package.json`
- `frontend/src-tauri/Cargo.toml` + `tauri.conf.json`

## Out of scope (deferred to future sprints)

- **Auto-schedule nightly evals** — Sprint 47 candidate (per
  SPEC addendum after Sprint 46).
- **Per-chunk WER breakdown within a corpus** — would require
  extending `EvalResult` with `chunks: list[EvalChunk]` and is
  overkill for v1; the aggregate WER is what M9-E criterion 6
  measures.
- **Corpus-configurable `--corpus-id` mapping table** —
  e.g. `[eval.corpus_aliases]` in config.toml where the user
  maps `recordings/foo` → `bar-corpus`. YAGNI for v1; the
  convention-based naming handles 95% of cases.
- **Drilldown to corpus detail page** — the legend chip
  `onClick` placeholder is reserved for Sprint 47+ but
  doesn't navigate anywhere in Sprint 46.
- **Trend prediction** — "if I record 10 more minutes, my WER
  will drop to ~7%" — future ML-driven feature.
- **Corpus overlap detection** — flag if 2 corpora have > 80%
  overlapping audio. Out of scope; would require audio
  fingerprinting.

## After Sprint 46

The dashboard will answer:
1. "Which corpus am I improving on?" — see per-corpus WER trend.
2. "Is the personalised model actually learning MY voice?" —
   compare `self:<date>` WER vs `common-voice-yue` WER across
   the same time window.
3. "Which corpus has the most headroom?" — see `avg_wer_pct`
   per corpus in the legend.

If the personalised model improves on `self:<date>` but not on
`common-voice-yue`, the user has **truly personalised** their
ASR (the model fits their voice better without overfitting the
test set). If both improve together, the fine-tune was
broadening the model (potentially a Common Voice yue retraining
artifact, not personalisation).
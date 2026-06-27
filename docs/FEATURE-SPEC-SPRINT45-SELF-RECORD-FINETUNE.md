# Sprint 45 — Self-record corpus fine-tune path (M9-E criterion 6 user-action)

**Date**: 2026-06-27
**Status**: Draft
**Author**: Mavis
**Priority**: High (closes M9-E Layer 2 criterion 6 user-action path)
**Depends on**: Sprint 38 (held-out eval), Sprint 40 (orchestrator + UI),
Sprint 33b (Tauri recording writes `yue-self-<date>/manifest.jsonl`)

> **Note on numbering**: Sprint 42 was already shipped as backend
> security hardening (`c613c26`). User requested the original "Sprint 42
> candidate" — the self-record corpus fine-tune path — under a clean
> number. This spec uses **Sprint 45** to avoid collision with the
> existing `FEATURE-SPEC-SPRINT42.md` (security) and to follow the
> sprint commit chain `Sprint 39 → 40 → 41 → 43 → 44 → 45`.

## Goal

Wire the existing pieces so the user can:

1. Open the Tauri Record card → record 30s Cantonese chunks.
2. Stop recording → today's `yue-self-<date>/manifest.jsonl` is flushed.
3. **Click one button** on `HeldOutEvalCard` → backend auto-detects the
   most recent self-record corpus dir → runs the full fine-tune
   pipeline (`--train-corpus-dir`) against it.
4. See the diff report (baseline WER vs after-fine-tune WER) on the
   same card.

This is the **user-actionable** end of M9-E Layer 2 acceptance
criterion 6 (WER < 10% with personalised model). Today (post-Sprint 40)
the orchestrator and UI affordance exist, but the user has to:

- Edit `--train-corpus-dir` on the CLI by hand, OR
- Hope the default `~/.gundam-halo/recordings/` directory gets picked up
  (it does, but the orchestrator then `--base_model_path` to
  `~/.gundam-halo/models/whisper-base/` — wrong path; see "Today" below).

Sprint 45 closes both gaps.

## Why now

- `yue-self-<date>/` recording folders are already being written by
  the Tauri pipeline (Sprint 33b).
- The orchestrator (`scripts/run_held_out_pipeline.py`, Sprint 40)
  already accepts `--train-corpus-dir` + `--base_model-path`.
- The fine-tune script (`scripts/finetune_whisper_yue.py`, M9-E Layer
  2) already supports `--train_audio_dir` for `manifest.jsonl`.
- `HeldOutEvalCard` already has a "Run fine-tune + re-eval" button
  wired to `POST /voice/run-finetune` (Sprint 40).
- The pieces fit; only the wiring is missing.

## Today (the actual gap)

### 1. Orchestrator `_cmd_finetune` uses wrong `--base_model_path`

```python
# scripts/run_held_out_pipeline.py:233-237 (Sprint 40)
"--base_model_path",
str(args.train_corpus_dir.parent / "models" / "whisper-base"),
```

If `--train-corpus-dir=~/.gundam-halo/recordings/yue-self-2026-06-27/`,
then `train_corpus_dir.parent = ~/.gundam-halo/recordings/` and the
resulting `--base_model_path = ~/.gundam-halo/recordings/models/whisper-base/`.
**This path does not exist.**

The intended default is `~/.gundam-halo/models/whisper-yue-base/` (the
Common Voice yue checkpoint from the baseline fine-tune). The current
code computes a wrong parent.

### 2. `--base_model_path` is missing as a CLI flag

The orchestrator's `parse_args` accepts `--train-corpus-dir`,
`--output-model-dir`, `--threshold`, `--model-size`, `--dry-run`,
`--halo-home`, `--skip-finetune-eval`, `--log-file`, `--mode` — but
**not** `--base-model-path`. The current `_cmd_finetune` hard-codes
the (wrong) default. The user can't override it without editing the
script.

### 3. Backend `POST /voice/run-finetune` doesn't pass `--train-corpus-dir`

```python
# backend/app/api/voice_config_api.py (Sprint 40)
@router.post("/voice/run-finetune")
async def run_finetune(payload: RunFinetuneRequest) -> ...:
    cmd = [
        "python",
        str(SCRIPTS / "run_held_out_pipeline.py"),
        "--mode", "finetune",
        # --train-corpus-dir is NOT passed!
        ...
    ]
```

When the user clicks "Fine-tune + re-eval", the orchestrator defaults
to `--train-corpus-dir=~/.gundam-halo/recordings/` (the parent). If
the user recorded into `yue-self-2026-06-27/`, the manifest is in the
child, not the parent → manifest not found → fine-tune script falls
back to Common Voice yue (the original baseline).

### 4. No "auto-detect latest corpus" helper

The frontend doesn't tell the user which `yue-self-<date>/` dir will
be picked up. If the user recorded yesterday AND today, it's not
obvious which corpus the backend will use.

### 5. Manifest validation not surfaced to UI

The orchestrator's `finetune_whisper_yue.py` validates the manifest
at load time, but rejects the entire script on the first bad row.
The user finds out the corpus is broken only after waiting 30+ min
for the LoRA setup.

## Design

### 1. Orchestrator: fix `--base_model_path` default + add as a CLI flag

```python
# scripts/run_held_out_pipeline.py — Sprint 45 changes

DEFAULT_BASE_MODEL_PATH = (
    DEFAULT_HALO_HOME / "models" / "whisper-yue-base"
)

def parse_args(argv):
    ...
    p.add_argument(
        "--base-model-path",
        type=Path,
        default=DEFAULT_BASE_MODEL_PATH,
        help=(
            "Base HF-format Whisper checkpoint to fine-tune from. "
            "Default: %(default)s — the Common Voice yue baseline "
            "checkpoint. For pure self-record fine-tunes, pass an "
            "empty string ('') to skip the CV base."
        ),
    )
    ...

def _cmd_finetune(args, halo_home, log_path):
    ...
    cmd = [
        "python", str(script),
        "--train_audio_dir", str(args.train_corpus_dir),
        "--output_dir",      str(args.output_model_dir),
        "--num_train_epochs","1",
    ]
    if str(args.base_model_path).strip():
        cmd += ["--base_model_path", str(args.base_model_path)]
    ...
```

Edge case: if `args.base_model_path` is `""` (empty string), skip the
flag — `finetune_whisper_yue.py` defaults to the HF Hub
`openai/whisper-base` (English-only weights). Useful for pure self-record
experiments that don't want the CV-yue prior.

### 2. Backend: accept and forward `--train-corpus-dir` + `--base-model-path`

```python
# backend/app/api/voice_config_api.py — Sprint 45 changes

class RunFinetuneRequest(BaseModel):
    threshold: float = 0.15
    model_size: str = "base"
    # NEW: allow the frontend (or curl) to override the auto-detected paths.
    train_corpus_dir: str | None = None
    base_model_path: str | None = None
    output_model_dir: str | None = None

@router.post("/voice/run-finetune")
async def run_finetune(payload: RunFinetuneRequest, background: BackgroundTasks) -> RunJobResponse:
    ...
    cmd = [
        "python", str(SCRIPTS / "run_held_out_pipeline.py"),
        "--mode", "finetune",
    ]
    if payload.train_corpus_dir:
        cmd += ["--train-corpus-dir", payload.train_corpus_dir]
    if payload.base_model_path:
        cmd += ["--base-model-path", payload.base_model_path]
    if payload.output_model_dir:
        cmd += ["--output-model-dir", payload.output_model_dir]
    ...
```

The `HeldOutEvalCard` UI never sets these fields — it relies on the
auto-detected defaults (see §3 below). The new optional fields are
there for CLI power users (`curl -d '{"train_corpus_dir":"..."}'`).

### 3. Backend: new `GET /voice/self-record-corpora` endpoint

```python
# backend/app/api/voice_config_api.py — Sprint 45 NEW endpoint

@dataclass(frozen=True)
class SelfRecordCorpusSummary:
    """One 'yue-self-<date>/' directory in $HALO_HOME/recordings."""
    path: str                # absolute path
    date: str                # YYYY-MM-DD (from dir name suffix)
    chunk_count: int         # count of chunk-NNN.wav files
    manifest_chunks: int     # count of valid JSONL rows
    total_duration_s: float  # sum of duration_s in manifest
    rejected_lines: int      # manifest format errors
    is_latest: bool          # the most recent by mtime

@router.get("/voice/self-record-corpora", response_model=list[SelfRecordCorpusSummary])
async def list_self_record_corpora() -> list[SelfRecordCorpusSummary]:
    """Scan $HALO_HOME/recordings/yue-self-* and summarise each.

    Returns an empty list if no corpus dirs exist yet (the user
    hasn't recorded anything). Order is newest-first by dir mtime.
    The frontend's HeldOutEvalCard reads this to display a "You
    have N corpora; latest: yue-self-2026-06-27 (12 chunks, 6.0min)"
    affordance above the "Run fine-tune + re-eval" button.
    """
    from app.voice.self_record_manifest import summarise as manifest_summarise
    halo_home = Path(os.environ.get("HALO_HOME") or Path.home() / ".gundam-halo")
    recordings = halo_home / "recordings"
    if not recordings.is_dir():
        return []

    corpora = []
    for d in sorted(recordings.glob("yue-self-*"), key=lambda p: p.stat().st_mtime, reverse=True):
        if not d.is_dir():
            continue
        # Count chunk files (chunk-NNN.wav).
        chunk_files = list(d.glob("chunk-*.wav"))
        manifest = d / "manifest.jsonl"
        if manifest.is_file():
            ms = manifest_summarise(manifest)
            manifest_chunks = ms.total_chunks
            total_duration = ms.total_duration_s
            rejected = ms.rejected_lines
        else:
            manifest_chunks = 0
            total_duration = 0.0
            rejected = 0
        # Extract date from dir name "yue-self-YYYY-MM-DD".
        date = d.name[len("yue-self-"):]
        corpora.append(SelfRecordCorpusSummary(
            path=str(d),
            date=date,
            chunk_count=len(chunk_files),
            manifest_chunks=manifest_chunks,
            total_duration_s=total_duration,
            rejected_lines=rejected,
            is_latest=(corpora == [] or True),  # first item is latest by mtime sort
        ))
    # Mark only the very first (newest) as is_latest.
    if corpora:
        corpora = [dataclasses.replace(c, is_latest=(i == 0)) for i, c in enumerate(corpora)]
    return corpora
```

### 4. `RunFinetuneRequest` auto-detection fallback in the endpoint

```python
# backend/app/api/voice_config_api.py — auto-detect if not provided

async def _resolve_train_corpus_dir(payload: RunFinetuneRequest) -> Path:
    """Resolve the --train-corpus-dir flag.

    Priority:
      1. payload.train_corpus_dir (explicit override).
      2. Latest 'yue-self-*' dir under $HALO_HOME/recordings/.
      3. $HALO_HOME/recordings/ itself (parent fallback — works if
         the manifest is flat-laid there).
      4. Raise HTTP 400 if none of the above exist.
    """
    if payload.train_corpus_dir:
        return Path(payload.train_corpus_dir)

    halo_home = Path(os.environ.get("HALO_HOME") or Path.home() / ".gundam-halo")
    recordings = halo_home / "recordings"
    if recordings.is_dir():
        dated = sorted(
            recordings.glob("yue-self-*"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if dated:
            return dated[0]

    if recordings.is_dir() and (recordings / "manifest.jsonl").is_file():
        return recordings

    raise HTTPException(
        status_code=400,
        detail=(
            "No self-record corpus found. Record at least one chunk via the "
            "Tauri Record card, or pass --train-corpus-dir explicitly."
        ),
    )
```

Same pattern for `--base-model-path`: defaults to
`~/.gundam-halo/models/whisper-yue-base/` if it exists, else empty
string (falls through to HF Hub `openai/whisper-base`).

### 5. HeldOutEvalCard: show latest corpus + button label

```tsx
// frontend/src/components/dashboard/HeldOutEvalCard.tsx — Sprint 45 changes

// New state: latest corpus summary from GET /voice/self-record-corpora
const [latestCorpus, setLatestCorpus] = useState<SelfRecordCorpusSummary | null>(null);

useEffect(() => {
  if (!evalResults || evalResults.length === 0) return;  // only show when backend has run once
  let cancelled = false;
  (async () => {
    try {
      const corpora = await api.listSelfRecordCorpora();
      if (!cancelled && corpora.length > 0) {
        setLatestCorpus(corpora[0]);  // already sorted newest-first
      }
    } catch (e) {
      console.warn("[HeldOutEvalCard] failed to list corpora:", e);
    }
  })();
  return () => { cancelled = true; };
}, [evalResults]);

// In the JSX, just above the existing "Run fine-tune + re-eval" button:
{latestCorpus && (
  <div data-testid="latest-corpus-hint" className="text-xs text-text-muted">
    Will fine-tune on: <span className="text-accent">{latestCorpus.path}</span>
    <br />
    ({latestCorpus.manifest_chunks} chunks · {latestCorpus.total_duration_s.toFixed(1)}s
    {latestCorpus.rejected_lines > 0 && (
      <> · <span className="text-warning">{latestCorpus.rejected_lines} rejected</span></>
    )})
  </div>
)}
```

When the user clicks the button, the existing `api.startFinetune()`
call goes through unchanged — auto-detection happens server-side.

### 6. Manifest validation: pre-flight check

```python
# backend/app/api/voice_config_api.py — before launching orchestrator

def _preflight_validate_manifest(train_dir: Path) -> str | None:
    """Validate the manifest. Returns None if OK, error message string if not.

    The error message is appended to the orchestrator job log + returned
    to the frontend as the immediate job-failure reason. Without this,
    the user waits 30-60s for the orchestrator to spawn, then the
    finetune script rejects the corpus, and the user has to dig through
    `~/.gundam-halo/logs/finetune-<job_id>.log` to find out why.
    """
    manifest = train_dir / "manifest.jsonl"
    if not manifest.is_file():
        return f"manifest.jsonl not found in {train_dir}. Did the Record card finish flushing?"
    from app.voice.self_record_manifest import iter_manifest, ManifestFormatError
    rows = 0
    try:
        for sample in iter_manifest(manifest):
            rows += 1
        if rows == 0:
            return f"manifest is empty: {manifest}"
    except FileNotFoundError as e:
        return str(e)
    return None
```

The pre-flight check is fast (just reads the JSONL). Returns
None on success; an error string on failure. The endpoint:
- Logs the error to the orchestrator job log.
- Marks the job as `failed` with `error: <error_message>`.
- Returns the error to the frontend immediately.

The frontend's `HeldOutEvalCard` displays the error inline (no
need to dig through logs).

## Files to create / modify

### Backend (~400 LoC)

- `backend/scripts/run_held_out_pipeline.py` (modify — fix
  `--base-model-path` default; add as CLI flag; allow empty string
  to skip the CV base).
- `backend/app/api/voice_config_api.py` (modify — extend
  `RunFinetuneRequest`; new `GET /voice/self-record-corpora`
  endpoint; `_resolve_train_corpus_dir()` helper;
  `_preflight_validate_manifest()`).
- `backend/app/voice/self_record_manifest.py` (no change — Sprint 33b
  is already production-ready and exposes `summarise()` /
  `iter_manifest()` for the new endpoints).
- `backend/app/core/eval_jobs.py` (modify — add `error` field to
  `EvalJob` dataclass if missing; ensure pre-flight errors land in
  the job record).

### Frontend (~80 LoC)

- `frontend/src/components/dashboard/HeldOutEvalCard.tsx` (modify —
  fetch + display `latestCorpus` summary above the button).
- `frontend/src/lib/api.ts` (modify — add
  `listSelfRecordCorpora(): Promise<SelfRecordCorpusSummary[]>`).
- `frontend/src/types/api.ts` (modify — add
  `SelfRecordCorpusSummary` interface).

### Docs (~280 LoC)

- `docs/HELD-OUT-EVAL.md` (modify — add "Self-record corpus
  fine-tune" section: how the auto-detection works, what
  `yue-self-<date>/` becomes, the diff report output now points at
  the corpus explicitly).
- `docs/FEATURE-SPEC-SPRINT45-SELF-RECORD-FINETUNE.md` (this file).
- `docs/CHANGELOG.md` (entry under [Unreleased]).

### Tests (~16 new tests)

- `backend/tests/scripts/test_run_held_out_pipeline.py` (extend
  Sprint 40 file — +4 tests):
  - `test_base_model_path_default_is_whisper_yue_base_not_recordings_models` —
    regression for the Sprint 40 parent-walk bug.
  - `test_base_model_path_flag_overrides_default` — explicit
    `--base-model-path=...` is honored.
  - `test_empty_base_model_path_skips_flag` — `--base-model-path=""`
    omits the flag in the spawned command (lets the script use HF
    Hub default).
  - `test_resolve_train_corpus_dir_helper_picks_latest_yue_self`
    — covered indirectly by the new endpoint test below, but a
    unit test on the helper is faster.

- `backend/tests/api/test_voice_self_record_corpora.py` NEW (~120 LoC,
  5 tests):
  - `test_no_recordings_dir_returns_empty_list`.
  - `test_single_corpus_summarised_correctly` — write a fake
    `yue-self-2026-06-27/` with 3 chunk files + 3 valid manifest rows.
  - `test_multiple_corpora_sorted_newest_first` — write 3 corpora
    with different mtimes; assert order.
  - `test_latest_flag_only_on_first` — the `is_latest` field is
    True only on the newest.
  - `test_corpus_with_rejected_manifest_lines_reports_count` —
    1 valid + 1 bad JSONL row; rejected_lines=1, manifest_chunks=1.

- `backend/tests/api/test_voice_finetune_preflight.py` NEW (~80 LoC,
  4 tests):
  - `test_preflight_passes_with_valid_manifest` — no error.
  - `test_preflight_fails_with_missing_manifest_jsonl` — error
    message starts with "manifest.jsonl not found".
  - `test_preflight_fails_with_empty_manifest` — "manifest is
    empty".
  - `test_preflight_fails_with_garbage_jsonl` — schema violation
    propagates.

- `frontend/src/components/dashboard/HeldOutEvalCard.test.tsx`
  (extend Sprint 40 file — +3 tests):
  - `test_displays_latest_corpus_path_and_chunks` — mock
    `listSelfRecordCorpora`; assert hint text.
  - `test_hides_hint_when_no_corpora` — empty list → hint not
    rendered.
  - `test_warns_on_rejected_lines` — `rejected_lines > 0` →
    amber span present.

## Acceptance criteria

- [ ] `GET /voice/self-record-corpora` returns a list of all
  `yue-self-*/` dirs under `$HALO_HOME/recordings/`, sorted
  newest-first.
- [ ] Clicking "Run fine-tune + re-eval" on `HeldOutEvalCard` (with
  no explicit corpus override) auto-uses the newest `yue-self-*/`
  dir; the hint shows the path + chunk count above the button.
- [ ] If no self-record corpus exists, the button shows an inline
  error pointing at the Record card.
- [ ] The orchestrator's default `--base-model-path` is now
  `~/.gundam-halo/models/whisper-yue-base/` (Common Voice yue
  baseline), NOT `~/.gundam-halo/recordings/models/whisper-base/`.
- [ ] `python scripts/run_held_out_pipeline.py --mode finetune
  --train-corpus-dir ~/.gundam-halo/recordings/yue-self-2026-06-27/`
  succeeds with the correct `--base_model_path` flag.
- [ ] Manifest pre-flight rejects broken corpora **before** the
  orchestrator spawns, with the error returned inline to the UI.
- [ ] Full backend pytest (excl slow tts) stays green: **+13 new
  tests** vs Sprint 41 baseline of 1317.
- [ ] Frontend tsc 0 errors + vitest +3 new tests (98 → 101).
- [ ] `cargo check --tests` clean.

## Version bump

`__version__` 0.1.17 → **0.1.18** (PATCH bump per Mavis memory rule —
this is wiring + bugfix + new endpoint, but it's polishing the
existing fine-tune path rather than a new user-facing feature. PATCH
reflects "small fixup to existing infrastructure").

3 surfaces synced:
- `backend/app/__init__.py` (single source of truth)
- `frontend/package.json`
- `frontend/src-tauri/Cargo.toml` + `tauri.conf.json`

## Out of scope (deferred to future sprints)

- **Per-corpus WER breakdown** (Common Voice yue vs self-record
  side-by-side in the dashboard) — Sprint 46 candidate.
- **Auto-schedule nightly evals** on the latest corpus — Sprint 47
  candidate.
- **Manifest editing UI** (delete bad chunks, retrain on subset) —
  future; CLI `jq` is enough for v1.
- **Multi-corpus training** (concat 2 `yue-self-*/` dirs into one
  fine-tune) — future; the orchestrator already supports it via
  `--train-corpus-dir` pointing at the parent if the manifest is
  concat'd (offline `cat manifest*.jsonl > manifest.json`).
- **Audio-side preflight** (verify WAV sample rate matches manifest
  `sample_rate` claim) — Sprint 33b already probes `chunk-NNN.wav`
  headers at write time; redundant in v1.
- **Streaming WER feedback** during fine-tune (parse LoRA trainer
  log every 10s, show current step) — future; current
  `eval_jobs.py` captures the log file tail every 3s but doesn't
  parse WER specifically.

## After Sprint 45

Once user runs the full pipeline (record 30s → fine-tune → re-eval),
M9-E Layer 2 criterion 6 closes if WER < 10% with personalised model.
The `HeldOutEvalCard` already shows "✓ M9-E criterion 6 MET" when
that condition is met (Sprint 40 indicator logic). User-action path
becomes: **record one chunk → click two buttons → wait 1 hour → see
green checkmark**.
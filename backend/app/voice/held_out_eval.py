"""Sprint 38 — held-out Cantonese eval helpers (shared module).

M9-E acceptance criterion 6 — "Held-out WER < 10% with
personalised model active". Sprint 38 ships the eval
plumbing; the live training run + personalised-checkpoint
swap are user-driven follow-ups (see
`docs/FEATURE-SPEC-SPRINT38.md`).

Three call sites share these helpers:

1. `tests/voice/test_held_out_eval.py` — the pytest
   surface (Sprint 32; skips when no held-out WAV).
2. `scripts/run_held_out_eval.py` — the CLI runner
   (Sprint 38; runs real `WhisperLocalASR.transcribe` +
   computes WER + writes a results JSON).
3. `tests/scripts/test_run_held_out_eval.py` — the
   mocked-pytest surface for the CLI.

The functions here are pure-Python (no Tauri / no shell),
so they're trivially unit-testable. Bash scripts
(`scripts/record-held-out.sh`,
`scripts/setup-held-out-model.sh`) call a subset of
these helpers to do the testable parts (file naming,
threshold resolution, model-cache check); the
interactive parts of the bash scripts are not tested
here.
"""
from __future__ import annotations

import json
import re
import wave
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

# Where the user records. Honours HALO_HOME (set by tests/conftest.py
# to a tmp_path). Default: ~/.gundam-halo/recordings/.
DEFAULT_HALO_HOME = Path.home() / ".gundam-halo"
RECORDINGS_DIRNAME = "recordings"
HELDOUT_PREFIX = "held-out-"

# Default threshold per Sprint 26 §4.3 acceptance
# criterion 2 (WER < 15% on the base model).
DEFAULT_WER_THRESHOLD = 0.15

# Where to find the test-config.toml override file.
TEST_CONFIG_FILENAME = "test-config.toml"

# Snapshot of the openai-whisper / WhisperHFASR contract:
# 16 kHz mono int16 PCM.
SAMPLE_RATE = 16_000

# openai-whisper cache layout (~/.cache/whisper/<size>.pt).
WHISPER_CACHE_DIRNAME = ".cache"
WHISPER_CACHE_WHISPER_SUBDIR = "whisper"


# ---------------------------------------------------------------------------
# Path helpers (shared by tests, CLI, and bash scripts via Python call)
# ---------------------------------------------------------------------------


def halo_home() -> Path:
    """Resolve the halo home dir (honours HALO_HOME override)."""
    import os

    halo_home_env = os.environ.get("HALO_HOME")
    if halo_home_env:
        return Path(halo_home_env).expanduser().resolve()
    return DEFAULT_HALO_HOME.resolve()


def recordings_dir() -> Path:
    """The dir where `record-held-out.sh` drops the held-out set."""
    return halo_home() / RECORDINGS_DIRNAME


def latest_heldout_wav() -> Path | None:
    """Return the latest held-out-<date>.wav by mtime, or None.

    The user may record multiple times (different dates);
    Sprint 26 §4.3 acceptance criterion calls for the
    **latest** recording to be the one the eval grades.
    Earlier recordings are kept (the eval never deletes
    them) but ignored.
    """
    rd = recordings_dir()
    if not rd.is_dir():
        return None
    candidates = list(rd.glob(f"{HELDOUT_PREFIX}*.wav"))
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def heldout_paths() -> tuple[Path | None, Path | None]:
    """Return (wav_path, transcript_path) — both None when missing.

    Mirrors `tests/voice/test_held_out_eval.py:_latest_heldout_wav`
    but returns both halves (the WAV and the matching .txt
    sidecar). Either may be None independently.
    """
    wav = latest_heldout_wav()
    if wav is None:
        return None, None
    txt = wav.with_suffix(".txt")
    return wav, (txt if txt.is_file() else None)


# ---------------------------------------------------------------------------
# WER math (Levenshtein DP — same algo as test_wer_helpers.py)
# ---------------------------------------------------------------------------


def word_error_rate(reference: str, hypothesis: str) -> float:
    """Levenshtein-based word error rate.

    Computes `WER = (S + D + I) / N` where N = reference
    word count, S/D/I = substitutions/deletions/insertions
    from the dynamic-programming edit distance.

    Edge cases:
    - Empty reference + empty hypothesis → 0.0
    - Empty reference + non-empty hypothesis → 1.0
      (treat as 100% insertion error)
    - Empty hypothesis + non-empty reference → 1.0
      (100% deletion error)

    Mirrors `tests/voice/test_wer_helpers.py:word_error_rate`
    (which the tests import directly). Defined here too
    so the CLI doesn't have to import from the tests dir.
    """
    ref_words = reference.split()
    hyp_words = hypothesis.split()
    if not ref_words:
        return 0.0 if not hyp_words else 1.0

    # DP table — (len(ref)+1) x (len(hyp)+1). Entry [i][j] =
    # min edit distance to align ref[:i] with hyp[:j].
    n_ref = len(ref_words)
    n_hyp = len(hyp_words)
    # Use a flat list of length (n_ref+1)*(n_hyp+1) for speed.
    INF = n_ref + n_hyp + 1
    dp = [[INF] * (n_hyp + 1) for _ in range(n_ref + 1)]
    for i in range(n_ref + 1):
        dp[i][0] = i  # delete all ref words to align with empty hyp
    for j in range(n_hyp + 1):
        dp[0][j] = j  # insert all hyp words to align with empty ref
    for i in range(1, n_ref + 1):
        for j in range(1, n_hyp + 1):
            if ref_words[i - 1] == hyp_words[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]  # match — no cost
            else:
                dp[i][j] = 1 + min(
                    dp[i - 1][j],  # deletion
                    dp[i][j - 1],  # insertion
                    dp[i - 1][j - 1],  # substitution
                )
    return dp[n_ref][n_hyp] / n_ref


# ---------------------------------------------------------------------------
# Threshold resolution (mirrors test_held_out_eval.py:_load_wer_threshold)
# ---------------------------------------------------------------------------


def load_wer_threshold() -> float:
    """Read WER threshold from `~/.gundam-halo/test-config.toml`.

    Looks for `[held_out_eval].wer_threshold` (float in [0, 1]).
    Falls back to `DEFAULT_WER_THRESHOLD` (15%) on any error.

    Lazily imports tomlkit / tomllib / tomli; falls back to
    the default if none is available.
    """
    config_path = halo_home() / TEST_CONFIG_FILENAME
    if not config_path.is_file():
        return DEFAULT_WER_THRESHOLD
    try:
        try:
            import tomlkit  # type: ignore

            data = tomlkit.loads(config_path.read_text(encoding="utf-8"))
        except ImportError:
            try:
                import tomllib  # type: ignore

                data = tomllib.loads(config_path.read_text(encoding="utf-8"))
            except ImportError:
                try:
                    import tomli as tomllib  # type: ignore

                    data = tomllib.loads(
                        config_path.read_text(encoding="utf-8")
                    )
                except ImportError:
                    return DEFAULT_WER_THRESHOLD
        section = data.get("held_out_eval", {})
        threshold = section.get("wer_threshold", DEFAULT_WER_THRESHOLD)
        if not isinstance(threshold, (int, float)):
            return DEFAULT_WER_THRESHOLD
        if not 0.0 <= threshold <= 1.0:
            return DEFAULT_WER_THRESHOLD
        return float(threshold)
    except Exception:
        return DEFAULT_WER_THRESHOLD


# ---------------------------------------------------------------------------
# WAV reading (16 kHz mono s16le PCM)
# ---------------------------------------------------------------------------


def wav_to_pcm_bytes(path: Path) -> tuple[bytes, int]:
    """Read a 16 kHz mono s16le WAV into raw PCM bytes.

    Mirrors the helper in `tests/voice/test_held_out_eval.py`.
    The Whisper contract is `transcribe(audio: bytes,
    sample_rate: int = 16000)` and the bytes must be 16-bit
    signed little-endian mono PCM at 16 kHz.

    Raises ValueError on format mismatch — caller surfaces
    a clear "not a 16 kHz mono s16le WAV" message.
    """
    with wave.open(str(path), "rb") as wf:
        if wf.getnchannels() != 1:
            raise ValueError(
                f"WAV {path} has {wf.getnchannels()} channels; expected mono (1)"
            )
        if wf.getsampwidth() != 2:
            raise ValueError(
                f"WAV {path} has {wf.getsampwidth()}-byte samples; "
                "expected s16le (16-bit)"
            )
        if wf.getframerate() != SAMPLE_RATE:
            raise ValueError(
                f"WAV {path} sample rate is {wf.getframerate()} Hz; "
                f"expected {SAMPLE_RATE} Hz"
            )
        pcm = wf.readframes(wf.getnframes())
    return pcm, SAMPLE_RATE


# ---------------------------------------------------------------------------
# Whisper model cache check (used by setup-held-out-model.sh)
# ---------------------------------------------------------------------------


def whisper_cache_dir() -> Path:
    """Return `~/.cache/whisper/` (the openai-whisper default cache).

    Unlike `halo_home()` (which honours `HALO_HOME` for
    test redirection), the whisper cache is rooted at
    **system `~`** — openai-whisper's `download_root`
    defaults to `Path.home() / ".cache" / "whisper"` and
    the package doesn't honour `HALO_HOME`. If the user
    set `WHISPER_CACHE` env var (openai-whisper does
    honour this), use that instead.
    """
    import os

    env = os.environ.get("WHISPER_CACHE")
    if env:
        return Path(env).expanduser().resolve()
    return Path.home() / WHISPER_CACHE_DIRNAME / WHISPER_CACHE_WHISPER_SUBDIR


def check_cached_whisper_model(size: str = "base") -> Path | None:
    """Check if `<whisper_cache_dir>/<size>.pt` exists.

    Returns the Path on hit, None on miss. Used by the
    bash `setup-held-out-model.sh` to decide whether to
    print the "run whisper.load_model() to download" hint.
    """
    candidate = whisper_cache_dir() / f"{size}.pt"
    return candidate if candidate.is_file() else None


# ---------------------------------------------------------------------------
# Recording filename helpers (used by record-held-out.sh)
# ---------------------------------------------------------------------------


_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def today_iso_date() -> str:
    """Return today's local date as `YYYY-MM-DD`.

    Used by `record-held-out.sh` to construct the
    held-out-<date>.wav filename. Local-time (not UTC)
    so the filename matches the user's wall clock.
    """
    return datetime.now().date().isoformat()


def heldout_filename(date_str: str, ext: str = "wav") -> str:
    """Build `held-out-<date>.<ext>` from a date string.

    Validates the date is `YYYY-MM-DD` to avoid filesystem
    surprises. `ext` must be a simple alphanumeric token
    (no path separators) — bash passes "wav" / "txt".
    """
    if not _DATE_RE.match(date_str):
        raise ValueError(
            f"date_str {date_str!r} must be YYYY-MM-DD"
        )
    if not re.match(r"^\w+$", ext):
        raise ValueError(f"ext {ext!r} must be alphanumeric (no path separators)")
    return f"{HELDOUT_PREFIX}{date_str}.{ext}"


def next_heldout_path(date_str: str, ext: str = "wav") -> Path:
    """Return `recordings_dir() / held-out-<date>.<ext>`.

    Caller is responsible for ensuring the parent dir
    exists (the bash script does `mkdir -p`).
    """
    return recordings_dir() / heldout_filename(date_str, ext)


# ---------------------------------------------------------------------------
# Eval result shape (CLI + tests use the same JSON format)
# ---------------------------------------------------------------------------


@dataclass
class EvalResult:
    """One held-out eval run. JSON-serialisable for trend tracking.

    Sprint 46: adds optional `corpus_id` so the dashboard can
    break down WER per training corpus. Existing JSONs (without
    the field) parse fine — the dataclass uses
    `corpus_id: str = ""` as the default. Convention:
      - "self:<YYYY-MM-DD>"  — self-record corpus
      - "common-voice-yue"  — Common Voice Cantonese test set
      - "synthetic:<name>"  — pytest fixtures / dry-runs
      - ""  — unattributed (legacy runs)
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
    corpus_id: str = ""

    @classmethod
    def now(cls, **kwargs) -> "EvalResult":
        kwargs.setdefault(
            "timestamp", datetime.now(timezone.utc).isoformat()
        )
        return cls(**kwargs)


@dataclass
class EvalRunSummary:
    """Aggregate over multiple EvalResults (one per CLI invocation)."""

    timestamp: str
    results: list[EvalResult] = field(default_factory=list)

    @classmethod
    def now(cls, results: Iterable[EvalResult]) -> "EvalRunSummary":
        return cls(
            timestamp=datetime.now(timezone.utc).isoformat(),
            results=list(results),
        )

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Default results directory (under tests/voice/held_out_results/)
# ---------------------------------------------------------------------------


HELD_OUT_RESULTS_DIRNAME = "held_out_results"


def held_out_results_dir() -> Path:
    """Default output dir for run_held_out_eval.py JSON summaries.

    Lives under `tests/voice/held_out_results/` so the
    JSON files are version-controllable trend data
    (small — ~1-2 KB each).
    """
    # backend dir = parent of `app/` = parent of `voice/`
    return Path(__file__).resolve().parent.parent.parent / "tests" / "voice" / HELD_OUT_RESULTS_DIRNAME


# ---------------------------------------------------------------------------
# Trend JSON loader (Sprint 39 — for /api/voice/eval-results)
# ---------------------------------------------------------------------------


def _summary_avg_wer(summary: EvalRunSummary) -> float:
    """Average WER across all results in a summary (single result
    case is just the one value).

    The CLI currently writes 1 result per summary (one
    held-out recording → one eval), but the dataclass
    supports N — average keeps the dashboard math stable
    if/when the CLI evolves to run multiple WAVs per
    invocation (e.g. a held-out test-set of 5 recordings).
    """
    if not summary.results:
        return 0.0
    return sum(r.wer for r in summary.results) / len(summary.results)


def _parse_summary(path: Path) -> EvalRunSummary | None:
    """Parse one trend JSON file. Returns None on any parse error.

    The CLI writes a flat dataclass dump via `to_json()`,
    which matches `EvalRunSummary` field-for-field. We
    parse defensively: missing required fields → None
    (logged at the caller, then skipped — never crash
    the whole trend endpoint on one bad file).
    """
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return None
        # Required fields for EvalRunSummary:
        if "timestamp" not in raw or not isinstance(raw["timestamp"], str):
            return None
        results_raw = raw.get("results", [])
        if not isinstance(results_raw, list):
            return None
        # Re-hydrate each EvalResult; skip this whole summary
        # if any result is malformed (one bad row shouldn't
        # pull the whole trend, but we don't half-parse a
        # summary either — atomic per summary).
        results: list[EvalResult] = []
        for r in results_raw:
            if not isinstance(r, dict):
                return None
            try:
                results.append(
                    EvalResult(
                        timestamp=str(r.get("timestamp", "")),
                        wav_path=str(r.get("wav_path", "")),
                        transcript_path=str(r.get("transcript_path", "")),
                        reference=str(r.get("reference", "")),
                        hypothesis=str(r.get("hypothesis", "")),
                        wer=float(r.get("wer", 0.0)),
                        threshold=float(r.get("threshold", 0.0)),
                        passed=bool(r.get("passed", False)),
                        duration_s=float(r.get("duration_s", 0.0)),
                        asr_backend=str(r.get("asr_backend", "")),
                        notes=str(r.get("notes", "")),
                        # Sprint 46: optional corpus tag. Missing in
                        # legacy JSONs → empty string (bucketed as
                        # "unattributed" by the breakdown endpoint).
                        corpus_id=str(r.get("corpus_id", "")),
                    )
                )
            except (TypeError, ValueError):
                return None
        return EvalRunSummary(timestamp=raw["timestamp"], results=results)
    except (json.JSONDecodeError, OSError):
        return None


def load_eval_history(
    results_dir: Path | None = None,
    limit: int = 7,
) -> list[dict]:
    """Load the most recent N trend JSONs as dashboard-ready dicts.

    Returns a list of `{timestamp, timestamp_ms, wer_pct, passed,
    wav_path, asr_backend, duration_sec, source_path}` dicts,
    sorted by `timestamp_ms` descending (newest first). The
    frontend treats each dict as one sparkline point.

    Skips corrupted JSONs gracefully (missing fields, bad
    timestamps, malformed results) — they're logged at WARNING
    level and the rest of the trend still loads.

    Returns `[]` when:
      - `results_dir` is None
      - `results_dir` does not exist
      - `results_dir` is empty (no `*.json` files)
      - all JSONs are corrupted

    Sprint 39: this drives `/api/voice/eval-results`. The
    sparkline shape is intentionally tiny (60×24 px, 7
    points) so we don't need pagination — `limit=7` is
    the maximum the UI ever requests.
    """
    import logging

    log = logging.getLogger(__name__)
    if results_dir is None:
        results_dir = held_out_results_dir()
    if not results_dir.is_dir():
        return []
    json_paths = sorted(results_dir.glob("*.json"))
    if not json_paths:
        return []

    rows: list[dict] = []
    for p in json_paths:
        summary = _parse_summary(p)
        if summary is None:
            log.warning(
                "held_out_eval: skipping malformed trend JSON %s", p
            )
            continue
        # ISO 8601 → epoch ms for stable sort key. The CLI
        # writes UTC (`+00:00` suffix), but tolerate offset
        # variants from older runs.
        try:
            ts = datetime.fromisoformat(summary.timestamp)
            ts_ms = int(ts.timestamp() * 1000)
        except (TypeError, ValueError):
            log.warning(
                "held_out_eval: skipping %s — bad timestamp %r",
                p,
                summary.timestamp,
            )
            continue
        # Use the first result's fields for the dashboard
        # card (the CLI currently writes exactly 1 result per
        # summary; multi-result is future-proofing).
        head = summary.results[0] if summary.results else None
        rows.append(
            {
                "timestamp": summary.timestamp,
                "timestamp_ms": ts_ms,
                # Average across all results in the summary
                # — handles the future N-results case.
                "wer_pct": round(_summary_avg_wer(summary) * 100, 2),
                "passed": all(r.passed for r in summary.results)
                if summary.results
                else False,
                "wav_path": head.wav_path if head else "",
                "asr_backend": head.asr_backend if head else "",
                "duration_sec": round(
                    sum(r.duration_s for r in summary.results), 2
                ),
                "source_path": str(p),
                # Sprint 46: per-corpus tagging. Empty string
                # for legacy runs (Sprint 38-45).
                "corpus_id": head.corpus_id if head else "",
            }
        )

    # Sort newest first, take top N.
    rows.sort(key=lambda r: r["timestamp_ms"], reverse=True)
    return rows[:limit] if limit > 0 else rows

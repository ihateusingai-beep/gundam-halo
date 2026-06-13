"""Cantonese eval scorer — M12.1.

Runs the 25-case eval set against the configured LLM (default:
MiniMax API) and grades each response against 3 deterministic
rules. No LLM judge — every check is a regex / heuristic so the
output is reproducible and the regression delta is meaningful.

Usage:
    cd backend && uv run python scripts/cantonese_eval.py
    cd backend && uv run python scripts/cantonese_eval.py --set path/to/eval_set.yaml
    cd backend && uv run python scripts/cantonese_eval.py --out path/to/results.json
    cd backend && uv run python scripts/cantonese_eval.py --case CANT-001
    cd backend && uv run python scripts/cantonese_eval.py --dry-run

Output:
    JSON summary printed to stdout; full per-case detail dumped to
    ``backend/tests/cantonese/results/<timestamp>.json``.

Rules (see docs/tickets/M12.1.md):
    V1 — must_have_any: response must contain ≥min_marker_count
         markers from the allowed list
    V2 — must_not_have: response must NOT contain any forbidden
         token (hard fail)
    V3 — grammar heuristics: 廣東話特有句式檢查
         (e.g. 「畀本書我」雙賓語 vs 普通話「給我一本書」)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# Path bootstrap — let `python scripts/cantonese_eval.py` find `app.*`
# ---------------------------------------------------------------------------

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import LLMConfig, load_config  # noqa: E402
from app.core.types import Message, Role  # noqa: E402
from app.engines.minimax import MiniMaxEngine  # noqa: E402

logger = logging.getLogger("cantonese_eval")

# ---------------------------------------------------------------------------
# Eval set loader
# ---------------------------------------------------------------------------

DEFAULT_EVAL_SET = (
    BACKEND_DIR / "tests" / "cantonese" / "eval_set.yaml"
)
DEFAULT_RESULTS_DIR = BACKEND_DIR / "tests" / "cantonese" / "results"

# 4Cantonese markers — counted toward V1 min_marker_count.
# Keep this regex in sync with the 4Cantonese Cantonese project baseline.
# NOT including Auntie/叔叔/靚仔/靚女 per Ken 2026-06-13 (product tone
# 鎖死成年人，不需要稱呼 marker).
MARKER_PATTERN = re.compile(
    r"(?:"
    r"嘅|喎|嘛|咩|啦|㗎|咁|喇|㗎嘛|嘅嘛|嘛喎|啲|咗|嘅|冇|睇|嚟|攰|噉|喺|唔|俾|畀|諗|搞|點|做|食|瞓|行|傾|傾偈|傾下|傾下偈"
    r")"
)


@dataclass
class EvalCase:
    id: str
    category: str
    input: str
    must_have_any: list[str]
    must_not_have: list[str]
    min_marker_count: int = 2
    notes: str = ""


def load_eval_set(path: Path) -> list[EvalCase]:
    """Load eval cases from a YAML file."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    cases = []
    for c in raw.get("cases", []):
        cases.append(
            EvalCase(
                id=c["id"],
                category=c["category"],
                input=c["input"],
                must_have_any=c.get("must_have_any", []),
                must_not_have=c.get("must_not_have", []),
                min_marker_count=c.get("min_marker_count", 2),
                notes=c.get("notes", ""),
            )
        )
    return cases


# ---------------------------------------------------------------------------
# Scorer — 3 deterministic rules
# ---------------------------------------------------------------------------


@dataclass
class CaseResult:
    case_id: str
    category: str
    input: str
    response: str
    v1_pass: bool
    v1_found_markers: list[str]
    v1_marker_count: int
    v2_pass: bool
    v2_violations: list[str]
    v3_pass: bool
    v3_violations: list[str]
    pass_: bool
    notes: str = ""


def _count_markers(text: str) -> list[str]:
    """Return the list of Cantonese markers found in `text`."""
    return MARKER_PATTERN.findall(text)


def _v1_marker_density(response: str, case: EvalCase) -> tuple[bool, list[str], int]:
    """V1: response must contain >= min_marker_count markers from MARKER_PATTERN.

    Returns (pass_, found_marker_list, unique_count).
    """
    found = _count_markers(response)
    # Unique markers — the same marker repeated 3 times still counts once
    # for the per-marker "marker density" signal. We sum occurrences to
    # honor the "min_marker_count" which is density-style (>=2).
    count = len(found)
    return count >= case.min_marker_count, found, count


def _v2_no_forbidden(response: str, case: EvalCase) -> tuple[bool, list[str]]:
    """V2: response must NOT contain any forbidden token.

    Forbidden tokens are checked as substrings (case-insensitive for
    English/中文混雜). 強烈希望 V2 false negative 為 0, 寧可寬鬆。
    """
    text = response
    violations = []
    for tok in case.must_not_have:
        if tok and tok in text:
            violations.append(tok)
    return len(violations) == 0, violations


# 廣東話特有 pattern — V3 grammar check
# 禁普通話 / 書面語句式 marker (substring match)
V3_FORBIDDEN_PATTERNS: list[tuple[str, str]] = [
    (r"我.{0,3}認為", "書面語「我認為」"),
    (r"這是", "普通話「這是」"),
    (r"那是", "普通話「那是」"),
    (r"這裏", "普通話「這裏」"),
    (r"那裏", "普通話「那裏」"),
    (r"正在", "普通話進行式「正在」(應用「做緊/諗緊」)"),
    (r"什麼是", "普通話「什麼是」(應用「咩係」)"),
    (r"為什麼", "普通話「為什麼」(應用「點解」)"),
    (r"沒有", "普通話「沒有」(應用「冇」)"),
    (r"不會", "普通話「不會」(應用「唔會」)"),
    (r"不能", "普通話「不能」(應用「唔可以/唔能夠」)"),
    (r"已經", "普通話「已經」(應用「已經」可，但常見「咗」更地道)"),
]


def _v3_grammar(response: str) -> tuple[bool, list[str]]:
    """V3: 廣東話特有句式檢查。

    Heuristic rules — catch 4 obvious 普通話 / 書面語 leaks. NOT
    exhaustive; 留 slot 將來加。
    """
    violations: list[str] = []
    for pattern, reason in V3_FORBIDDEN_PATTERNS:
        if re.search(pattern, response):
            violations.append(reason)
    return len(violations) == 0, violations


def score_response(response: str, case: EvalCase) -> CaseResult:
    """Apply the 3-rule scorer to a single response."""
    v1_pass, v1_markers, v1_count = _v1_marker_density(response, case)
    v2_pass, v2_violations = _v2_no_forbidden(response, case)
    v3_pass, v3_violations = _v3_grammar(response)

    # A case passes only if all 3 rules pass.
    pass_all = v1_pass and v2_pass and v3_pass

    return CaseResult(
        case_id=case.id,
        category=case.category,
        input=case.input,
        response=response,
        v1_pass=v1_pass,
        v1_found_markers=v1_markers,
        v1_marker_count=v1_count,
        v2_pass=v2_pass,
        v2_violations=v2_violations,
        v3_pass=v3_pass,
        v3_violations=v3_violations,
        pass_=pass_all,
        notes=case.notes,
    )


# ---------------------------------------------------------------------------
# LLM driver
# ---------------------------------------------------------------------------

# Minimal system prompt — baseline measurement. M12.2 will harden this.
BASELINE_SYSTEM_PROMPT = (
    "你係一個廣東話 AI 助手。用廣東話回應用戶。"
)


async def _call_llm(case_input: str, llm_cfg: LLMConfig) -> str:
    """Single-turn LLM call. Returns the assistant text content."""
    engine = MiniMaxEngine(
        api_key=llm_cfg.api_key,
        base_url=llm_cfg.base_url,
        model=llm_cfg.default_model,
    )
    messages = [
        Message(role=Role.SYSTEM, content=BASELINE_SYSTEM_PROMPT),
        Message(role=Role.USER, content=case_input),
    ]
    reply = await engine.chat(messages, temperature=0.7, max_tokens=512)
    return reply.content or ""


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


@dataclass
class EvalSummary:
    timestamp: str
    model: str
    base_url: str
    system_prompt: str
    total: int
    passed: int
    pass_rate: float
    v1_fail_ids: list[str] = field(default_factory=list)
    v2_fail_ids: list[str] = field(default_factory=list)
    v3_fail_ids: list[str] = field(default_factory=list)
    cases: list[CaseResult] = field(default_factory=list)


def _summarize(results: list[CaseResult], llm_cfg: LLMConfig) -> EvalSummary:
    import datetime as _dt

    total = len(results)
    passed = sum(1 for r in results if r.pass_)
    return EvalSummary(
        timestamp=_dt.datetime.now(_dt.UTC).isoformat(),
        model=llm_cfg.default_model,
        base_url=llm_cfg.base_url,
        system_prompt=BASELINE_SYSTEM_PROMPT,
        total=total,
        passed=passed,
        pass_rate=(passed / total) if total else 0.0,
        v1_fail_ids=[r.case_id for r in results if not r.v1_pass],
        v2_fail_ids=[r.case_id for r in results if not r.v2_pass],
        v3_fail_ids=[r.case_id for r in results if not r.v3_pass],
        cases=results,
    )


async def run_eval(
    cases: list[EvalCase],
    llm_cfg: LLMConfig,
    *,
    only_id: str | None = None,
    on_result=None,
) -> list[CaseResult]:
    """Run each case through the LLM and score the response."""
    results: list[CaseResult] = []
    for case in cases:
        if only_id and case.id != only_id:
            continue
        logger.info(f"[{case.id}] running: {case.input!r}")
        t0 = time.time()
        try:
            response = await _call_llm(case.input, llm_cfg)
        except Exception as e:
            logger.error(f"[{case.id}] LLM error: {e}")
            response = f"[LLM_ERROR: {e}]"
        dt = time.time() - t0
        result = score_response(response, case)
        result.notes = f"({dt:.1f}s) " + result.notes
        results.append(result)
        status = "PASS" if result.pass_ else "FAIL"
        logger.info(
            f"[{case.id}] {status}  v1={result.v1_marker_count}  "
            f"v2={'OK' if result.v2_pass else result.v2_violations}  "
            f"v3={'OK' if result.v3_pass else result.v3_violations}"
        )
        if on_result:
            on_result(result)
    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _print_summary(summary: EvalSummary, file=sys.stdout) -> None:
    print("\n" + "=" * 60, file=file)
    print("Cantonese Eval — Summary", file=file)
    print("=" * 60, file=file)
    print(f"Model        : {summary.model}", file=file)
    print(f"Base URL     : {summary.base_url}", file=file)
    print(f"Total / Pass : {summary.passed} / {summary.total}", file=file)
    print(f"Pass rate    : {summary.pass_rate * 100:.1f}%", file=file)
    print(
        f"V1 fails     : {len(summary.v1_fail_ids)}  {summary.v1_fail_ids}",
        file=file,
    )
    print(
        f"V2 fails     : {len(summary.v2_fail_ids)}  {summary.v2_fail_ids}",
        file=file,
    )
    print(
        f"V3 fails     : {len(summary.v3_fail_ids)}  {summary.v3_fail_ids}",
        file=file,
    )
    print("=" * 60, file=file)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--set",
        type=Path,
        default=DEFAULT_EVAL_SET,
        help="Path to eval_set.yaml",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output JSON path (default: tests/cantonese/results/<ts>.json)",
    )
    parser.add_argument(
        "--case",
        type=str,
        default=None,
        help="Run a single case by id (e.g. CANT-001)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate the eval set without calling the LLM",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose logging",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    )

    cases = load_eval_set(args.set)
    logger.info(f"Loaded {len(cases)} cases from {args.set}")

    if args.dry_run:
        print(f"Dry run OK: {len(cases)} cases loaded from {args.set}")
        for c in cases:
            print(f"  - {c.id:12s} [{c.category:18s}] {c.input}")
        return 0

    # LLM config — read from global config, env vars override
    llm_cfg = load_config().llm
    if not llm_cfg.api_key:
        logger.error(
            "No MiniMax API key found. Set MINIMAX_API_KEY env var or "
            "configure ~/.gundam-halo/config.toml [llm].api_key."
        )
        return 2

    results = asyncio.run(run_eval(cases, llm_cfg, only_id=args.case))
    summary = _summarize(results, llm_cfg)
    _print_summary(summary)

    # Write JSON output
    if args.out:
        out_path = args.out
    else:
        DEFAULT_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        out_path = DEFAULT_RESULTS_DIR / f"{ts}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(asdict(summary), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nWrote: {out_path}")

    # Exit non-zero if pass_rate < threshold — useful for CI gate
    if summary.pass_rate < 0.5:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

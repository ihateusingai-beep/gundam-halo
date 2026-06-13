"""Unit tests for the Cantonese 3-rule scorer.

Pure rule tests — NO LLM calls, NO API keys required. Run with:

    cd backend && uv run pytest tests/cantonese/test_cantonese_scorer.py -v

These tests pin down the exact behavior of the scorer against
hand-curated gold responses. If you change the rules, update
the gold cases here too.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make scripts/ importable
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
SCRIPTS_DIR = BACKEND_DIR / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from cantonese_eval import (  # noqa: E402
    V3_FORBIDDEN_PATTERNS,
    EvalCase,
    _count_markers,
    _v1_marker_density,
    _v2_no_forbidden,
    _v3_grammar,
    load_eval_set,
    score_response,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _mk_case(
    *,
    case_id: str = "TEST-001",
    must_have_any: list[str] | None = None,
    must_not_have: list[str] | None = None,
    min_marker_count: int = 2,
    input_: str = "test input",
) -> EvalCase:
    return EvalCase(
        id=case_id,
        category="test",
        input=input_,
        must_have_any=must_have_any or [],
        must_not_have=must_not_have or [],
        min_marker_count=min_marker_count,
        notes="unit test",
    )


# ---------------------------------------------------------------------------
# V1: marker density
# ---------------------------------------------------------------------------


class TestV1MarkerDensity:
    def test_passes_when_enough_markers(self):
        case = _mk_case(min_marker_count=2)
        response = "我今日做咗好多嘢，攰到死啦"  # 咗, 好多, 攰, 啦
        passed, found, count = _v1_marker_density(response, case)
        assert passed
        assert count >= 2
        # Should find 咗, 攰, 啦
        assert "咗" in found
        assert "啦" in found

    def test_fails_when_too_few_markers(self):
        case = _mk_case(min_marker_count=2)
        response = "今日做了很多事情"  # 0 markers
        passed, _found, count = _v1_marker_density(response, case)
        assert not passed
        assert count < 2

    def test_zero_markers_when_all_mandarin(self):
        case = _mk_case(min_marker_count=1)
        response = "我今天很累, 需要休息"
        _passed, _found, count = _v1_marker_density(response, case)
        assert count == 0

    def test_min_marker_count_honored(self):
        case = _mk_case(min_marker_count=3)
        response = "咗啦"  # only 2 markers
        passed, _found, count = _v1_marker_density(response, case)
        assert count == 2
        assert not passed

    def test_count_markers_returns_list(self):
        markers = _count_markers("咗咗啦嘛")  # 4 marker chars
        assert len(markers) == 4
        assert markers == ["咗", "咗", "啦", "嘛"]


# ---------------------------------------------------------------------------
# V2: forbidden tokens
# ---------------------------------------------------------------------------


class TestV2Forbidden:
    def test_passes_when_no_forbidden(self):
        case = _mk_case(must_not_have=["了", "什麼"])
        response = "今日做咗好多嘢"
        passed, violations = _v2_no_forbidden(response, case)
        assert passed
        assert violations == []

    def test_fails_when_single_violation(self):
        case = _mk_case(must_not_have=["了", "什麼"])
        response = "今日做了很多事情"
        passed, violations = _v2_no_forbidden(response, case)
        assert not passed
        assert "了" in violations

    def test_fails_with_multiple_violations(self):
        case = _mk_case(must_not_have=["了", "什麼", "請問"])
        response = "請問什麼是 LoRA 呢？"
        passed, violations = _v2_no_forbidden(response, case)
        assert not passed
        assert set(violations) == {"什麼", "請問"}

    def test_empty_forbidden_list_always_passes(self):
        case = _mk_case(must_not_have=[])
        response = "任何文字都得"
        passed, _violations = _v2_no_forbidden(response, case)
        assert passed

    def test_forbidden_token_must_be_substring(self):
        # 囗 works as substring match — e.g. 「了」 匹配到「完成」唔會誤中
        # 但 「完成」 包含 「了」 會誤中。Spec 接受 substring，test 確認行為。
        case = _mk_case(must_not_have=["完成"])
        response = "我搞掂咗個 task"
        passed, violations = _v2_no_forbidden(response, case)
        # 「完成」不在 response → pass
        assert passed
        assert violations == []


# ---------------------------------------------------------------------------
# V3: grammar heuristics
# ---------------------------------------------------------------------------


class TestV3Grammar:
    def test_detects_mandarin_thinking_phrase(self):
        # 「我認為」 是 書面語
        response = "我認為呢個方法唔得"
        passed, violations = _v3_grammar(response)
        assert not passed
        assert any("我認為" in v for v in violations)

    def test_detects_zheng_zai(self):
        response = "我正在寫緊個 report"
        passed, violations = _v3_grammar(response)
        # 「正在」 + 「寫緊」 共存 — V3 應該 catch「正在」
        assert not passed
        assert any("正在" in v for v in violations)

    def test_passes_clean_cantonese(self):
        response = "我而家做緊嘢，唔好打擾我啦"
        passed, violations = _v3_grammar(response)
        assert passed
        assert violations == []

    def test_detects_shen_me_shi(self):
        response = "什麼是 LoRA 呢?"
        passed, violations = _v3_grammar(response)
        assert not passed
        assert any("什麼是" in v for v in violations)

    def test_v3_patterns_list_is_nonempty(self):
        # 防止 future regression — V3 至少要有 5 個 pattern
        assert len(V3_FORBIDDEN_PATTERNS) >= 5


# ---------------------------------------------------------------------------
# Integration: score_response
# ---------------------------------------------------------------------------


class TestScoreResponse:
    def test_all_pass_for_gold_cantonese(self):
        case = _mk_case(
            must_have_any=["咗", "啦"],
            must_not_have=["了", "什麼"],
            min_marker_count=2,
        )
        response = "我今日做咗好多嘢，攰到死啦"  # 咗, 攰, 啦
        result = score_response(response, case)
        assert result.v1_pass
        assert result.v2_pass
        assert result.v3_pass
        assert result.pass_

    def test_fails_on_v1_only(self):
        case = _mk_case(
            must_have_any=["咗"],
            must_not_have=[],
            min_marker_count=2,
        )
        response = "做了很多事"  # 0 markers
        result = score_response(response, case)
        assert not result.v1_pass
        assert result.v2_pass  # trivially passes (no forbids)
        assert result.v3_pass
        assert not result.pass_

    def test_fails_on_v2_only(self):
        case = _mk_case(
            must_have_any=[],
            must_not_have=["了"],
            min_marker_count=1,
        )
        response = "咗啦"  # 2 markers, but 没了
        # wait — response 是「咗啦」冇「了」. 改
        response = "咗啦了"  # contains 了
        result = score_response(response, case)
        assert result.v1_pass
        assert not result.v2_pass
        assert result.v3_pass
        assert not result.pass_

    def test_fails_on_v3_only(self):
        case = _mk_case(
            must_have_any=[],
            must_not_have=[],
            min_marker_count=0,
        )
        response = "咗啦我認為呢個方法得"
        result = score_response(response, case)
        # 0 markers required → V1 passes
        assert result.v1_pass
        # No forbids → V2 passes
        assert result.v2_pass
        # V3 fails on 我認為
        assert not result.v3_pass
        assert not result.pass_

    def test_returns_all_violations(self):
        case = _mk_case(
            must_have_any=[],
            must_not_have=["了", "什麼", "請問"],
            min_marker_count=0,
        )
        # 「了」是 substring, 所以要喺 response 入面 actually 出現
        # 「什麼是」 會 hit 「什麼」 (substring), 「請問」 顯式 hit
        # 「了」 需要 顯式寫, 所以 response 加「了」
        response = "請問什麼是 X 呢？我已經知道了"
        result = score_response(response, case)
        assert sorted(result.v2_violations) == ["了", "什麼", "請問"]


# ---------------------------------------------------------------------------
# Eval set loader
# ---------------------------------------------------------------------------


class TestLoadEvalSet:
    @pytest.fixture
    def eval_set_path(self) -> Path:
        return BACKEND_DIR / "tests" / "cantonese" / "eval_set.yaml"

    def test_loads_25_cases(self, eval_set_path: Path):
        cases = load_eval_set(eval_set_path)
        assert len(cases) == 25

    def test_case_ids_unique(self, eval_set_path: Path):
        cases = load_eval_set(eval_set_path)
        ids = [c.id for c in cases]
        assert len(set(ids)) == 25

    def test_categories_match_distribution(self, eval_set_path: Path):
        cases = load_eval_set(eval_set_path)
        from collections import Counter

        dist = Counter(c.category for c in cases)
        # Spec 規定嘅 分佈
        assert dist["casual_chat"] == 6
        assert dist["tech_help"] == 5
        assert dist["emotional"] == 4
        assert dist["mixed_lang"] == 4
        assert dist["edge_case"] == 3
        assert dist["instruction_follow"] == 3

    def test_every_case_has_input(self, eval_set_path: Path):
        cases = load_eval_set(eval_set_path)
        for c in cases:
            assert c.input.strip(), f"{c.id} has empty input"

    def test_every_case_has_marker_requirement(self, eval_set_path: Path):
        cases = load_eval_set(eval_set_path)
        for c in cases:
            assert c.must_have_any, f"{c.id} has no must_have_any markers"
            assert c.min_marker_count >= 1, f"{c.id} min_marker_count < 1"

"""Sprint 40 — run_held_out_pipeline orchestrator tests.

Coverage (4 tests):
1. diff_report math (baseline 50% → after 12% = correct improvement delta)
2. full mode dispatches all 3 subprocesses (record/eval/finetune skipped
   per spec — record is a separate step in the cockpit; full is
   baseline → finetune → after)
3. eval mode only calls run_held_out_eval.py (not finetune)
4. Threshold override changes pass/fail (within orchestrator + the
   subprocess chain — mocked)

We mock subprocess.run so no real recording / fine-tune happens.
The diff_report function is exercised against real JSON files
written into tmp_path.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from scripts.run_held_out_pipeline import (
    _latest_two_trends,
    _summary_wer,
    _summary_backend,
    _print_diff_report,
    main,
    parse_args,
)


def _write_trend(path: Path, wer: float, backend: str, ts: str = "2026-06-27T10:00:00+00:00") -> None:
    """Write a fake trend JSON in the EvalRunSummary shape."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "timestamp": ts,
                "results": [
                    {
                        "timestamp": ts,
                        "wav_path": "/tmp/held.wav",
                        "transcript_path": "/tmp/held.txt",
                        "reference": "你好 世界",
                        "hypothesis": "你好 世界",
                        "wer": wer,
                        "threshold": 0.15,
                        "passed": wer < 0.15,
                        "duration_s": 0.1,
                        "asr_backend": backend,
                        "notes": "",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Diff math tests
# ---------------------------------------------------------------------------


def test_diff_report_math_baseline_vs_after(tmp_path: Path, capsys):
    """Baseline WER 50%, after WER 12% → diff says −38pp / −76%."""
    results_dir = tmp_path / "tests" / "voice" / "held_out_results"
    _write_trend(results_dir / "baseline.json", wer=0.50, backend="whisper_local", ts="2026-06-27T09:00:00+00:00")
    _write_trend(results_dir / "after.json", wer=0.12, backend="whisper_hf", ts="2026-06-27T11:00:00+00:00")

    _print_diff_report(results_dir)
    out = capsys.readouterr().out
    assert "WER = 50.0%  (backend: whisper_local)" in out
    assert "WER = 12.0%  (backend: whisper_hf)" in out
    assert "−38.0pp WER" in out
    assert "−76.0%" in out or "−76%" in out


def test_diff_report_m9e_criterion_met(tmp_path: Path, capsys):
    """When after WER is < 10%, the report flags M9-E criterion 6 as MET."""
    results_dir = tmp_path / "tests" / "voice" / "held_out_results"
    _write_trend(results_dir / "b.json", wer=0.50, backend="whisper_local")
    _write_trend(results_dir / "a.json", wer=0.08, backend="whisper_hf")
    _print_diff_report(results_dir)
    out = capsys.readouterr().out
    assert "M9-E Layer 2 acceptance criterion 6 MET" in out


def test_diff_report_no_change_when_same_backend(tmp_path: Path, capsys):
    """Same backend → no 'improvement' claim (would be noise)."""
    results_dir = tmp_path / "tests" / "voice" / "held_out_results"
    _write_trend(results_dir / "b.json", wer=0.50, backend="whisper_local")
    _write_trend(results_dir / "a.json", wer=0.30, backend="whisper_local")
    _print_diff_report(results_dir)
    out = capsys.readouterr().out
    assert "same backend" in out
    assert "Improvement: −20.0pp" in out


def test_diff_report_regression_message(tmp_path: Path, capsys):
    """After > baseline → 'regression' message."""
    results_dir = tmp_path / "tests" / "voice" / "held_out_results"
    _write_trend(results_dir / "b.json", wer=0.10, backend="whisper_local")
    _write_trend(results_dir / "a.json", wer=0.30, backend="whisper_hf")
    _print_diff_report(results_dir)
    out = capsys.readouterr().out
    assert "Regression" in out


def test_summary_wer_averages_multiple_results():
    """A summary with N results → average WER × 100."""
    summary = {
        "results": [
            {"wer": 0.10, "asr_backend": "whisper_local"},
            {"wer": 0.20, "asr_backend": "whisper_local"},
            {"wer": 0.30, "asr_backend": "whisper_local"},
        ]
    }
    assert _summary_wer(summary) == 20.0
    assert _summary_backend(summary) == "whisper_local"


def test_latest_two_trends_returns_newest_first(tmp_path: Path):
    """The two most recent files (by mtime) are returned as (latest, previous)."""
    results_dir = tmp_path / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    old = results_dir / "old.json"
    new = results_dir / "new.json"
    _write_trend(old, wer=0.50, backend="whisper_local")
    _write_trend(new, wer=0.12, backend="whisper_hf")
    # Force mtime ordering: old = 1000s ago, new = now.
    import os, time

    old_mtime = time.time() - 1000
    os.utime(old, (old_mtime, old_mtime))
    new_mtime = time.time()
    os.utime(new, (new_mtime, new_mtime))

    latest, previous = _latest_two_trends(results_dir)
    assert latest is not None and previous is not None
    assert _summary_wer(latest) == pytest.approx(_summary_wer(_read(new)))
    assert _summary_wer(previous) == pytest.approx(_summary_wer(_read(old)))


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Mode dispatch tests
# ---------------------------------------------------------------------------


def test_eval_mode_dispatches_only_run_held_out_eval(tmp_path: Path):
    """`--mode eval` runs run_held_out_eval.py exactly once, never finetune."""
    with patch("scripts.run_held_out_pipeline.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        rc = main(["--mode", "eval", "--halo-home", str(tmp_path)])
    assert rc == 0
    # Subprocess was called exactly once.
    assert mock_run.call_count == 1
    cmd = mock_run.call_args[0][0]
    assert "run_held_out_eval.py" in " ".join(cmd)
    assert "finetune_whisper_yue.py" not in " ".join(cmd)


def test_full_mode_dispatches_baseline_then_finetune_then_eval(tmp_path: Path):
    """`--mode full` runs run_held_out_eval.py twice (baseline + after)
    + finetune_whisper_yue.py once = 3 total subprocess calls."""
    with patch("scripts.run_held_out_pipeline.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        rc = main(["--mode", "full", "--halo-home", str(tmp_path)])
    assert rc == 0
    assert mock_run.call_count == 3
    cmds = [" ".join(c[0][0]) for c in mock_run.call_args_list]
    # 1st call = baseline eval, 2nd = finetune, 3rd = after eval.
    assert sum("run_held_out_eval.py" in c for c in cmds) == 2
    assert sum("finetune_whisper_yue.py" in c for c in cmds) == 1
    # The finetune call is in the middle.
    assert "finetune_whisper_yue.py" in cmds[1]


def test_full_mode_skips_after_eval_with_flag(tmp_path: Path):
    """`--mode full --skip-finetune-eval` runs only baseline + finetune (2 calls)."""
    with patch("scripts.run_held_out_pipeline.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        rc = main(
            ["--mode", "full", "--skip-finetune-eval", "--halo-home", str(tmp_path)]
        )
    assert rc == 0
    assert mock_run.call_count == 2


def test_full_mode_propagates_baseline_missing_wav(tmp_path: Path):
    """When baseline eval returns rc=2 (no WAV), full mode aborts
    with rc=2 and does NOT proceed to finetune."""
    with patch("scripts.run_held_out_pipeline.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=2, stdout="", stderr="")
        rc = main(["--mode", "full", "--halo-home", str(tmp_path)])
    assert rc == 2
    # Only the baseline eval ran — no finetune, no after eval.
    assert mock_run.call_count == 1


def test_full_mode_propagates_finetune_failure(tmp_path: Path):
    """When finetune returns non-zero, full mode aborts with rc=3."""
    with patch("scripts.run_held_out_pipeline.subprocess.run") as mock_run:
        # 1st call (baseline) returns 0, 2nd call (finetune) returns 1.
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="", stderr=""),
            MagicMock(returncode=1, stdout="", stderr=""),
        ]
        rc = main(["--mode", "full", "--halo-home", str(tmp_path)])
    assert rc == 3
    assert mock_run.call_count == 2  # baseline + finetune, no after


def test_record_mode_dispatches_bash_script(tmp_path: Path):
    """`--mode record` runs record-held-out.sh via bash."""
    with patch("scripts.run_held_out_pipeline.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        rc = main(["--mode", "record", "--halo-home", str(tmp_path)])
    assert rc == 0
    cmd = mock_run.call_args[0][0]
    assert cmd[0] == "bash"
    assert "record-held-out.sh" in cmd[1]


def test_finetune_mode_dispatches_finetune_script(tmp_path: Path):
    """`--mode finetune` runs finetune_whisper_yue.py with the right args."""
    with patch("scripts.run_held_out_pipeline.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        rc = main(["--mode", "finetune", "--halo-home", str(tmp_path)])
    assert rc == 0
    cmd = mock_run.call_args[0][0]
    assert "finetune_whisper_yue.py" in cmd[1]
    assert "--train_audio_dir" in cmd
    assert "--output_dir" in cmd


# ---------------------------------------------------------------------------
# Threshold test
# ---------------------------------------------------------------------------


def test_threshold_override_passed_to_subprocess(tmp_path: Path):
    """`--threshold 0.05` is forwarded to run_held_out_eval.py."""
    with patch("scripts.run_held_out_pipeline.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        rc = main(
            ["--mode", "eval", "--threshold", "0.05", "--halo-home", str(tmp_path)]
        )
    assert rc == 0
    cmd = mock_run.call_args[0][0]
    # Threshold + value must appear consecutively.
    t_idx = cmd.index("--threshold")
    assert cmd[t_idx + 1] == "0.05"


# ---------------------------------------------------------------------------
# Missing script handling
# ---------------------------------------------------------------------------


def test_missing_script_returns_rc_2(tmp_path: Path, monkeypatch):
    """If a referenced script doesn't exist, the orchestrator returns
    rc=2 (no crash)."""
    # Point at a non-existent scripts dir.
    import scripts.run_held_out_pipeline as orch

    monkeypatch.setattr(orch, "SCRIPTS_DIR", tmp_path / "no-such-dir")
    rc = main(["--mode", "eval", "--halo-home", str(tmp_path)])
    assert rc == 2


# ---------------------------------------------------------------------------
# Sprint 45 — --base-model-path flag + default fix
# ---------------------------------------------------------------------------


def test_base_model_path_default_is_whisper_yue_base_not_recordings_models(
    tmp_path: Path,
):
    """Regression: Sprint 40 default was `recordings/models/whisper-base`
    (parent-walk bug). Sprint 45 must default to
    `~/.gundam-halo/models/whisper-yue-base`."""
    with patch("scripts.run_held_out_pipeline.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        rc = main(["--mode", "finetune", "--halo-home", str(tmp_path)])
    assert rc == 0
    cmd = mock_run.call_args[0][0]
    # Find --base_model_path flag in the spawned command.
    assert "--base_model_path" in cmd, f"--base_model_path flag missing in {cmd}"
    flag_idx = cmd.index("--base_model_path")
    base_path = Path(cmd[flag_idx + 1])
    # Must NOT contain /recordings/ in the path.
    assert "/recordings/" not in str(base_path), (
        f"base_model_path leaked recordings/ parent: {base_path}"
    )
    # Must end with /models/whisper-yue-base.
    assert base_path.name == "whisper-yue-base", (
        f"expected whisper-yue-base, got {base_path.name}"
    )
    # Must be under the resolved halo_home, not under recordings/.
    assert base_path.parent.name == "models"


def test_base_model_path_flag_overrides_default(tmp_path: Path):
    """Explicit `--base-model-path=...` is forwarded to finetune script."""
    custom_base = tmp_path / "models" / "whisper-experimental"
    custom_base.mkdir(parents=True, exist_ok=True)
    with patch("scripts.run_held_out_pipeline.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        rc = main(
            [
                "--mode", "finetune",
                "--halo-home", str(tmp_path),
                "--base-model-path", str(custom_base),
            ]
        )
    assert rc == 0
    cmd = mock_run.call_args[0][0]
    assert "--base_model_path" in cmd
    flag_idx = cmd.index("--base_model_path")
    assert Path(cmd[flag_idx + 1]) == custom_base


def test_empty_base_model_path_skips_flag(tmp_path: Path):
    """`--base-model-path=""` omits the flag — finetune_whisper_yue.py
    falls back to HF Hub openai/whisper-base (English-only)."""
    with patch("scripts.run_held_out_pipeline.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        rc = main(
            [
                "--mode", "finetune",
                "--halo-home", str(tmp_path),
                "--base-model-path", "",
            ]
        )
    assert rc == 0
    cmd = mock_run.call_args[0][0]
    assert "--base_model_path" not in cmd, (
        f"--base_model_path should be omitted when flag is empty, got {cmd}"
    )


def test_resolve_train_corpus_dir_helper_picks_latest_yue_self(tmp_path: Path, monkeypatch):
    """Unit test on the helper that powers the new endpoint's
    auto-detection. Latest `yue-self-*/` dir wins."""
    from app.api import voice_config_api

    recordings = tmp_path / "recordings"
    recordings.mkdir()
    older = recordings / "yue-self-2026-06-26"
    older.mkdir()
    (older / "manifest.jsonl").write_text(
        '{"audio_path": "/a.wav", "text": "old", "duration_s": 30, "sample_rate": 16000}\n'
    )
    newer = recordings / "yue-self-2026-06-27"
    newer.mkdir()
    # Force mtime ordering.
    import os
    import time
    os.utime(older, (time.time() - 3600, time.time() - 3600))
    os.utime(newer, (time.time(), time.time()))

    # Override _resolve_halo_home to return tmp_path.
    monkeypatch.setattr(voice_config_api, "_resolve_halo_home", lambda: tmp_path)
    result = voice_config_api._latest_self_record_corpus(tmp_path)
    assert result == newer
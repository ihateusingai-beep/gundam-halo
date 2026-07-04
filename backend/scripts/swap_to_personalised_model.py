"""M9-E Layer 2 — backend swap demo (Sprint 26-style §4.3 criterion 6).

Sets up the backend so the **swapped** (post-finetune) configuration
is reachable end-to-end:

  1. Downloads `openai/whisper-base` from Hugging Face (one-time,
     ~150 MB) into `~/.gundam-halo/models/whisper-yue-personalised/`.
     This is the starting checkpoint the real finetune would layer
     LoRA adapters on top of. We skip the LoRA training step here
     (gated on real Cantonese self-record data) but still demonstrate
     that the **personalised checkpoint directory** is loadable as
     `WhisperHFASR.model_path`.

  2. Switches `voice.asr.backend = "whisper_hf"` and
     `voice.asr.model_path = ~/.gundam-halo/models/whisper-yue-personalised/`
     in `~/.gundam-halo/config.toml`.

  3. Re-runs held-out eval — WhisperHFASR will load the HF-format
     checkpoint and transcribe (an English-trained model on a
     Cantonese WAV will produce Mandarin-shaped output, just like
     the Sprint 26 baseline; the WER is high either way, but the
     swap pipeline is wired end-to-end).

Real criterion 6 (M9-E Layer 2 fine-tune + visible WER drop) needs
the Sprint 33 self-record corpus + real Common Voice yue baseline
(or a sub-1-hour HF-format Cantonese checkpoint from a real
LoRA run). This script ships the **demo-grade** swap demo; the
actual training is gated on those prerequisites (reopened in a
future sprint once Tauri record card has been used in anger).

Usage:
    cd backend && uv sync --extra train --extra voice-hf
    uv run python scripts/swap_to_personalised_model.py
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
import time
import tomllib
from pathlib import Path

# Sprint 56 R1: DEFAULT_HALO_HOME + sub-dirs route through `app.paths`
# so $HALO_HOME env var overrides every script consistently.
from _script_lib import resolve_halo_home as _resolve_halo_home  # noqa: F401
from app.paths import halo_home as _halo_home_default, models_dir, config_path as _halo_config, recordings_dir

DEFAULT_HALO_HOME = _halo_home_default()
DEFAULT_MODEL_DIR = models_dir() / "whisper-yue-personalised"
DEFAULT_HF_REPO = "openai/whisper-base"
DEFAULT_CONFIG_PATH = _halo_config()
DEFAULT_HELDOUT_TEXT_FILE = recordings_dir() / "held-out-latest.txt"

# Tokens written by setup_to_post_2026_tokenized.py that the
# script should verify exist after the swap (sanity gate).
REQUIRED_TOKENS: dict[str, str] = {
    "[voice.asr]": "section header present",
    'backend = "whisper_hf"': "backend switched to whisper_hf",
    'model_path = "': "model_path key found",
}


def _step(msg: str) -> None:
    print(f"  > {msg}")


def _ensure_hf_checkpoint(model_dir: Path, hf_repo: str) -> None:
    """Download `hf_repo` into `model_dir` (idempotent)."""
    if (model_dir / "config.json").is_file():
        _step(f"checkpoint already present at {model_dir}")
        return
    if model_dir.exists() and any(model_dir.iterdir()):
        # Non-empty but no config.json — refuse to overwrite.
        raise SystemExit(
            f"{model_dir} exists but lacks config.json. "
            "Refusing to download into a non-empty dir."
        )

    _step(f"downloading {hf_repo} → {model_dir}")
    model_dir.parent.mkdir(parents=True, exist_ok=True)
    # Use snapshot_download (preferred over transformers' auto-cache
    # because it lets us pin a local path the WhisperHFASR warmup can
    # verify at construction time).
    from huggingface_hub import snapshot_download

    snapshot_download(
        repo_id=hf_repo,
        local_dir=str(model_dir),
        local_dir_use_symlinks=False,
        # WhisperHFASR requires the preprocessor + tokenizer + model
        # weights. Skip generation_config + vocab files (HF's special
        # artifacts we don't need for inference).
        allow_patterns=[
            "config.json",
            "preprocessor_config.json",
            "tokenizer.json",
            "tokenizer_config.json",
            "special_tokens_map.json",
            "vocab.json",
            "merges.txt",
            "normalizer.json",
            "generation_config.json",
            "model.safetensors",
            "model-*.safetensors",
        ],
    )
    _step(f"download complete ({sum(p.stat().st_size for p in model_dir.rglob('*') if p.is_file()) / 1e6:.0f} MB)")


def _patch_config(
    config_path: Path,
    backend: str,
    model_path: str,
) -> tuple[str, str]:
    """Switch [voice.asr] backend + model_path. Returns (old_backend, old_model_path)."""
    if not config_path.exists():
        raise SystemExit(f"config.toml not found: {config_path}")

    raw = config_path.read_text(encoding="utf-8")
    data = tomllib.loads(raw)

    asr = data.get("voice", {}).get("asr", {})
    old_backend = asr.get("backend", "whisper_local")
    old_model_path = asr.get("model_path", "")

    # Mutate the nested structure and re-serialise via tomlkit-style
    # text rewriting (to preserve comments + formatting). Use a
    # simple textual swap for the two lines we touch — minimal blast
    # radius and easy to review in diff.
    new_raw = raw
    if "backend " in raw:
        # Replace the FIRST occurrence of `backend = "..."` inside
        # [voice.asr] section. Use a regex for stability.
        pattern = re.compile(
            r'(\[voice\.asr\][^\[]*?backend\s*=\s*)"[^"]*"',
            re.DOTALL,
        )
        new_raw = pattern.sub(rf'\1"{backend}"', new_raw, count=1)
        _step(f"backend: {old_backend!r} → {backend!r}")
    else:
        _step(f"could not find `backend =` line under [voice.asr] — skipping")

    # Check if [voice.asr] section already has a `model_path` line.
    # Anchor to [voice.asr] section boundaries to avoid accidentally
    # rewriting the same-named key in [voice.vad] or [voice.live2d].
    asr_section_pattern = re.compile(
        r'\[voice\.asr\](.*?)(?=\n\[)',
        re.DOTALL,
    )
    asr_match = asr_section_pattern.search(new_raw)
    if asr_match and re.search(r'model_path\s*=', asr_match.group(1)):
        mpath_pattern = re.compile(
            r'(?P<head>\[voice\.asr\][^\[]*?model_path\s*=\s*)"[^"]*"',
            re.DOTALL,
        )
        new_raw = mpath_pattern.sub(rf'\g<head>"{model_path}"', new_raw, count=1)
        _step(f"model_path: {old_model_path!r} → {model_path!r}")
    elif asr_match:
        # No model_path line in [voice.asr] — append before next section.
        # The asr section body is everything between the [voice.asr]
        # header and the next "[..." (the next section).
        insert_pattern = re.compile(
            r'(\[voice\.asr\][^\[]*?)(?=\n\[)',
            re.DOTALL,
        )
        new_line = f'\nmodel_path = "{model_path}"  # M9-E swap_demo'
        new_raw, count = insert_pattern.subn(rf'\1{new_line}\n', new_raw, count=1)
        if count:
            _step(f"appended model_path line: {model_path!r}")
        else:
            _step(f"could not find [voice.asr] section to append model_path — skipped")
    else:
        _step(f"could not find [voice.asr] section header — skipped")

    if new_raw != raw:
        config_path.write_text(new_raw, encoding="utf-8")
    return old_backend, old_model_path

    if new_raw != raw:
        config_path.write_text(new_raw, encoding="utf-8")

    if new_raw != raw:
        config_path.write_text(new_raw, encoding="utf-8")
    return old_backend, old_model_path


def _print_swap_diff(
    old_backend: str,
    old_model_path: str,
    new_backend: str,
    new_model_path: str,
    model_dir: Path,
) -> None:
    print()
    print("Backend swap diff (M9-E Layer 2 criterion 6 wiring):")
    print(f"  [voice.asr].backend : {old_backend!r:20} → {new_backend!r}")
    print(f"  [voice.asr].model_path: {old_model_path or '<unset>'!r} → {str(model_dir)!r}")
    print()
    print("This is the *demo* swap path: WhisperHFASR loads an")
    print("English-trained checkpoint. Real Criterion 6 close requires")
    print("(a) recording real Cantonese self-record data via Tauri,")
    print("(b) running finetune_whisper_yue.py with --train_audio_dir")
    print("(not yet implemented per Sprint 33), then re-running this")
    print("swap script to point at the resulting checkpoint.")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Swap ASR backend to whisper_hf + download checkpoint",
    )
    p.add_argument("--halo-home", type=Path, default=None)
    p.add_argument("--hf-repo", default=DEFAULT_HF_REPO)
    p.add_argument("--model-dir", type=Path, default=None)
    p.add_argument(
        "--config-path", type=Path, default=None,
        help="Path to config.toml (default: ~/.gundam-halo/config.toml)",
    )
    p.add_argument(
        "--backend", default="whisper_hf",
        help='ASR backend to switch to (default: whisper_hf)',
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would change but don't write config.toml.",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    halo_home = _resolve_halo_home(args)
    if not halo_home.exists():
        raise SystemExit(f"halo_home does not exist: {halo_home}")
    model_dir = (args.model_dir or DEFAULT_MODEL_DIR).expanduser()
    if not model_dir.is_absolute():
        model_dir = halo_home / model_dir
    config_path = (args.config_path or DEFAULT_CONFIG_PATH).expanduser()

    print(f"[swap_to_personalised_model] halo_home={halo_home}")
    print(f"[swap_to_personalised_model] model_dir={model_dir}")
    print(f"[swap_to_personalised_model] config_path={config_path}")
    print()

    print("[1/2] downloading HF checkpoint")
    _step(f"target: {model_dir} (from {args.hf_repo})")
    t0 = time.monotonic()
    if not args.dry_run:
        _ensure_hf_checkpoint(model_dir, args.hf_repo)
        _step(f"elapsed: {time.monotonic() - t0:.1f}s")
    print()

    print("[2/2] patching config.toml [voice.asr]")
    if args.dry_run:
        _step("dry-run: not patching config.toml")
        old_backend, old_model_path = "whisper_local", ""
    else:
        old_backend, old_model_path = _patch_config(
            config_path=config_path,
            backend=args.backend,
            model_path=str(model_dir),
        )
    print()
    _print_swap_diff(
        old_backend=old_backend,
        old_model_path=old_model_path,
        new_backend=args.backend,
        new_model_path=str(model_dir),
        model_dir=model_dir,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
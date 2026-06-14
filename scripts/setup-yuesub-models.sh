#!/usr/bin/env bash
# setup-yuesub-models.sh — idempotent symlink helper for Sprint 17b.
#
# Gundam Halo's yuesub ASR backend (see docs/FEATURE-SPEC-SPRINT17b.md)
# expects model files under $HOME/.gundam-halo/models/. The yuesub-api
# repo at $HOME/workspace/yuesub-api/models/ already contains the
# pre-downloaded SenseVoiceSmall + fsmn-vad + denoiser.onnx files (and
# optionally hon9kon9ize/bert-large-cantonese if you ran
# `download_models.py --with-bert`).
#
# This script symlinks the yuesub-api model artifacts into Gundam
# Halo's expected layout. Safe to re-run: it skips anything that
# already exists at the target path.
#
# Usage:
#   bash scripts/setup-yuesub-models.sh          # link all available
#   bash scripts/setup-yuesub-models.sh --check # just verify, don't link
#
# Exit codes:
#   0 = all available model dirs are linked (or already existed)
#   1 = some models are missing on the yuesub-api side (run download_models.py)

set -euo pipefail

CHECK_ONLY=0
if [ "${1:-}" = "--check" ]; then
    CHECK_ONLY=1
fi

# Allow overrides via env, but default to the documented layout.
HALO_HOME="${HALO_HOME:-$HOME/.gundam-halo}"
YUESUB_HOME="${YUESUB_HOME:-$HOME/workspace/yuesub-api}"
HALO_MODELS="$HALO_HOME/models"
YUESUB_MODELS="$YUESUB_HOME/models"

# ---------------------------------------------------------------------------
# Sanity checks
# ---------------------------------------------------------------------------

if [ ! -d "$YUESUB_MODELS" ]; then
    echo "ERROR: yuesub-api models dir not found at $YUESUB_MODELS" >&2
    echo "  Clone https://github.com/yourname/yuesub-api there, or set" >&2
    echo "  YUESUB_HOME=/path/to/yuesub-api before running this script." >&2
    exit 1
fi

if [ ! -d "$YUESUB_MODELS/iic" ]; then
    echo "ERROR: $YUESUB_MODELS/iic/ not found." >&2
    echo "  Run: cd $YUESUB_HOME && python download_models.py" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Helper: link if missing, never overwrite.
# ---------------------------------------------------------------------------

link_or_skip() {
    local target="$1"      # existing file/dir on the yuesub-api side
    local linkpath="$2"    # where we want the symlink under $HALO_MODELS
    if [ -e "$linkpath" ] || [ -L "$linkpath" ]; then
        if [ -L "$linkpath" ] && [ "$(readlink "$linkpath")" = "$target" ]; then
            echo "ok    $linkpath -> $target"
        else
            echo "skip  $linkpath (exists, not a yuesub symlink)"
        fi
    else
        if [ "$CHECK_ONLY" = "1" ]; then
            echo "miss  $linkpath"
        else
            ln -s "$target" "$linkpath"
            echo "link  $linkpath -> $target"
        fi
    fi
}

# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

mkdir -p "$HALO_MODELS"

echo "Gundam Halo models: $HALO_MODELS"
echo "yuesub-api models: $YUESUB_MODELS"
echo "---"

# SenseVoiceSmall + fsmn-vad (both live under $YUESUB_MODELS/iic/)
link_or_skip "$YUESUB_MODELS/iic" "$HALO_MODELS/iic"

# Denoiser (single file, not under iic/)
if [ -f "$YUESUB_MODELS/denoiser.onnx" ]; then
    link_or_skip "$YUESUB_MODELS/denoiser.onnx" "$HALO_MODELS/denoiser.onnx"
else
    echo "miss  $YUESUB_MODELS/denoiser.onnx (not downloaded)"
fi

# BERT corrector (optional — only if user ran --with-bert)
if [ -d "$YUESUB_MODELS/hon9kon9ize" ]; then
    link_or_skip "$YUESUB_MODELS/hon9kon9ize" "$HALO_MODELS/hon9kon9ize"
else
    echo "skip  $HALO_MODELS/hon9kon9ize (BERT corrector not downloaded)"
    echo "      Run: cd $YUESUB_HOME && python download_models.py --with-bert"
    echo "      then re-run this script to link."
fi

echo "---"
if [ "$CHECK_ONLY" = "1" ]; then
    echo "(check-only mode — no links created)"
fi
echo "Done. Verify with:  ls -la $HALO_MODELS"

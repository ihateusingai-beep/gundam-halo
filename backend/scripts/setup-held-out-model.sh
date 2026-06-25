#!/usr/bin/env bash
# Sprint 38 — verify openai-whisper base.pt is cached.
#
# Usage:  bash scripts/setup-held-out-model.sh
#
# The Sprint 38 baseline uses openai-whisper's `base.pt`
# (75 MB) — NOT the larger `whisper-yue-base` HF model.
# This script just verifies the file exists and prompts
# a download if not. The HF personalised-checkpoint path
# is reserved for after Sprint 30 Track B fine-tuning
# (set voice.asr.backend = "whisper_hf" + voice.asr.model_path
# to the checkpoint dir; see docs/FEATURE-SPEC-SPRINT38.md).
#
# Exits 0 if the model is ready, 1 otherwise.

set -euo pipefail

# ---------------------------------------------------------------------------
# Pretty logging
# ---------------------------------------------------------------------------

bold() { printf "\033[1m%s\033[0m\n" "$*"; }
ok()   { printf "  \033[32m✓\033[0m %s\n" "$*"; }
warn() { printf "  \033[33m!\033[0m %s\n" "$*"; }
fail() { printf "  \033[31m✗\033[0m %s\n" "$*"; exit 1; }
info() { printf "    %s\n" "$*"; }

bold "→ Sprint 38 held-out model setup"
info "Backend:  openai-whisper (whisper_local ASR)"
info "Model:    base (75 MB, ~150 MB on disk after extraction)"
info "Cache:    \${XDG_CACHE_HOME:-\$HOME/.cache}/whisper/base.pt"

# ---------------------------------------------------------------------------
# Step 1 — check venv
# ---------------------------------------------------------------------------

bold "→ Step 1 / 3 — Check openai-whisper is in the venv"

# Prefer the project's venv python (.venv/bin/python) so the
# import sees openai-whisper installed by `uv sync --extra voice`.
# Fall back to system python3 if no venv exists.
if [[ -x ".venv/bin/python" ]]; then
    PY=".venv/bin/python"
elif [[ -x "../.venv/bin/python" ]]; then
    PY="../.venv/bin/python"
else
    PY="python3"
fi
info "Python: $PY"

if "$PY" -c "import whisper" 2>/dev/null; then
    ok "openai-whisper importable"
else
    fail "openai-whisper not installed. Run: uv sync --extra voice"
fi

# ---------------------------------------------------------------------------
# Step 2 — check ~/.cache/whisper/base.pt
# ---------------------------------------------------------------------------

CACHE_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/whisper"
CACHE_FILE="$CACHE_DIR/base.pt"

bold "→ Step 2 / 3 — Check $CACHE_FILE"

if [[ -f "$CACHE_FILE" ]]; then
    SIZE_BYTES=$(stat -f%z "$CACHE_FILE" 2>/dev/null || stat -c%s "$CACHE_FILE")
    SIZE_MB=$(( SIZE_BYTES / 1024 / 1024 ))
    ok "base.pt cached (${SIZE_MB} MB)"
else
    warn "base.pt not found at $CACHE_FILE"
    info "Trigger download by loading the model in Python:"
    info ""
    info "    uv run python -c \"import whisper; whisper.load_model('base')\""
    info ""
    info "(openai-whisper auto-downloads to the cache dir on first load_model call."
    info " Re-run this script after the download finishes.)"
    fail "base.pt missing — run the command above and re-run."
fi

# ---------------------------------------------------------------------------
# Step 3 — sanity check loadable
# ---------------------------------------------------------------------------

bold "→ Step 3 / 3 — Verify base.pt loads"

# Lazy load: takes ~5 s on Apple Silicon, ~10 s on Intel.
# We don't pipe stderr — let the user see progress.
if ! "$PY" -c "import whisper; m = whisper.load_model('base'); print('OK loaded:', type(m).__name__)" 2>&1 | tail -3; then
    fail "base.pt exists but failed to load — corrupt download? Delete and re-run."
fi

ok "base.pt loadable"

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------

bold "✓ Held-out model ready"
info "voice.asr.backend = 'whisper_local' (the default)"
info "voice.asr.model_size = 'base' (the default)"
info ""
info "Next: bash scripts/record-held-out.sh  to record 30 s + transcript,"
info "      then bash scripts/run_held_out_eval.py  to grade WER."

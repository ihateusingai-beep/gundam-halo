#!/usr/bin/env bash
# M9-E Layer 2 — personalised refinement one-command wrapper.
#
# Sprint 67 prep. This script orchestrates the 3-step
# M9-E Layer 2 pipeline:
#
#   1. validate the yue-self-* corpus
#   2. run the LoRA finetune (Sprint 55's
#      `finetune_whisper_yue.py`)
#   3. swap the backend to the personalised checkpoint
#      (Sprint 54's `swap_to_personalised_model.py`)
#
# Usage (from the project root or anywhere):
#   ./backend/scripts/personalise_yue.sh
#   ./backend/scripts/personalise_yue.sh --force
#   ./backend/scripts/personalise_yue.sh --corpus <path>
#
# Exit codes match `validate_yue_self_record.py`:
#   0 — all 3 steps succeeded
#   1 — hard fail (validation, finetune, or swap)
#   2 — soft fail (under 5-min corpus; --force to override)
#
# This is a Sprint 67 PREP deliverable. The actual
# fine-tune + WER-improvement measurement happens
# in Sprint 68+ when the user has recorded enough
# audio (currently the existing demo corpus is
# only ~20s; needs ~5 min for a meaningful WER
# improvement per the M9-E criterion 6 spec).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

CORPUS=""
FORCE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --corpus) CORPUS="$2"; shift 2 ;;
    --force) FORCE="--force"; shift ;;
    *) echo "❌ Unknown arg: $1"; exit 1 ;;
  esac
done

# Step 1 — validate the corpus.
echo "─── Step 1/3: validate yue self-record corpus ───"
VALIDATE_ARGS=()
if [[ -n "$CORPUS" ]]; then
  VALIDATE_ARGS+=(--corpus "$CORPUS")
fi
if [[ -n "$FORCE" ]]; then
  VALIDATE_ARGS+=(--force)
fi
if ! uv run python "$SCRIPT_DIR/validate_yue_self_record.py" "${VALIDATE_ARGS[@]}"; then
  VALIDATE_EXIT=$?
  if [[ $VALIDATE_EXIT -eq 2 ]]; then
    echo "⚠ Soft fail (under 5-min corpus). Re-run with --force to override."
  fi
  exit $VALIDATE_EXIT
fi

# Step 2 — finetune.
echo ""
echo "─── Step 2/3: run LoRA finetune ───"
if ! uv run python "$BACKEND_DIR/scripts/finetune_whisper_yue.py"; then
  echo "❌ Finetune failed. See logs above."
  exit 1
fi

# Step 3 — swap the backend to the personalised checkpoint.
echo ""
echo "─── Step 3/3: swap backend to personalised checkpoint ───"
if ! uv run python "$BACKEND_DIR/scripts/swap_to_personalised_model.py"; then
  echo "❌ Swap failed. See logs above."
  exit 1
fi

echo ""
echo "✓ M9-E Layer 2 personalised refinement complete."
echo "  Run held-out eval to measure the WER improvement:"
echo "    uv run python $BACKEND_DIR/scripts/run_held_out_eval.py"

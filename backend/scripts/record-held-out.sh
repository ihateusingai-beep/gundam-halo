#!/usr/bin/env bash
# Sprint 38 — interactive held-out Cantonese recorder.
#
# Usage:  bash scripts/record-held-out.sh
#         bash scripts/record-held-out.sh --date 2026-06-25
#
# What it does (Sprint 26 §4.3 acceptance criterion 1):
#   1. Verifies ~/.gundam-halo/recordings/ exists.
#   2. Picks a recorder: `rec` (SoX) on macOS/Linux, falls back
#      to `afrecord` (macOS built-in) or `arecord` (Linux ALSA).
#   3. Records 30 seconds of mono 16 kHz s16le WAV.
#   4. Plays the recording back via `afplay` / `aplay` so the
#      user can verify their mic captured clean audio.
#   5. Opens the user's $EDITOR on a .txt sidecar — the user
#      types the correct Cantonese transcript. NO validation
#      (the transcript IS the ground truth; if the user
#      mistypes, the WER is wrong, that's the user's problem).
#   6. Verifies the transcript is non-empty.
#   7. Prints the file path + reminder to run pytest.
#
# The 30 s duration is per Sprint 26 §4.3 spec — long enough
# to surface ASR quality issues (5 s clips can pass by
# cherry-picking), short enough that the user doesn't bail.
#
# Failure modes (all exit 1 with a clear message):
#   - No recorder found in PATH (no rec / afrecord / arecord)
#   - Editor exits non-zero (user ^C'd the editor)
#   - Transcript is empty after edit
#   - Disk full / permission denied on ~/.gundam-halo/recordings/

set -euo pipefail

# ---------------------------------------------------------------------------
# Args + env
# ---------------------------------------------------------------------------

DATE_STR="${1:-$(date +%Y-%m-%d)}"
DURATION_S=30
HALO_HOME="${HALO_HOME:-$HOME/.gundam-halo}"
RECORDINGS_DIR="$HALO_HOME/recordings"
HALDOUT_WAV="$RECORDINGS_DIR/held-out-${DATE_STR}.wav"
HALDOUT_TXT="$RECORDINGS_DIR/held-out-${DATE_STR}.txt"

# ---------------------------------------------------------------------------
# Pretty logging
# ---------------------------------------------------------------------------

bold() { printf "\033[1m%s\033[0m\n" "$*"; }
ok()   { printf "  \033[32m✓\033[0m %s\n" "$*"; }
warn() { printf "  \033[33m!\033[0m %s\n" "$*"; }
fail() { printf "  \033[31m✗\033[0m %s\n" "$*"; exit 1; }
info() { printf "    %s\n" "$*"; }

bold "→ Sprint 38 held-out recorder"
info "Date:    $DATE_STR"
info "WAV:     $HALDOUT_WAV"
info "TXT:     $HALDOUT_TXT"
info "Length:  ${DURATION_S} s"

# ---------------------------------------------------------------------------
# Step 1 — prep
# ---------------------------------------------------------------------------

mkdir -p "$RECORDINGS_DIR" || fail "Cannot create $RECORDINGS_DIR"
if [[ -f "$HALDOUT_WAV" ]]; then
    warn "Existing $HALDOUT_WAV — overwriting (delete manually to keep)"
fi

# ---------------------------------------------------------------------------
# Step 2 — pick a recorder
# ---------------------------------------------------------------------------

REC_CMD=""
PLAY_CMD=""

if command -v rec >/dev/null 2>&1; then
    REC_CMD="rec"
    PLAY_CMD="afplay"  # macOS — falls back to aplay on Linux below
elif [[ "$(uname)" == "Darwin" ]] && command -v afrecord >/dev/null 2>&1; then
    # macOS built-in (no SoX needed)
    REC_CMD="afrecord"
    PLAY_CMD="afplay"
elif command -v arecord >/dev/null 2>&1; then
    REC_CMD="arecord"
    PLAY_CMD="aplay"
else
    fail "No recorder found. Install SoX (\`brew install sox\` on macOS, \`apt install sox\` on Debian/Ubuntu) and re-run."
fi

ok "Recorder: $REC_CMD"
ok "Player:   $PLAY_CMD"

# ---------------------------------------------------------------------------
# Step 3 — record
# ---------------------------------------------------------------------------

bold "→ Recording ${DURATION_S} s of mono 16 kHz s16le audio"
info "Speak Cantonese clearly into your default input device."
info "Recording starts in 2 s..."

sleep 2

REC_ARGS=()
case "$REC_CMD" in
    rec)
        # SoX `rec` defaults vary by platform; explicit format args
        # ensure the WAV header matches the Whisper contract
        # (mono, 16 kHz, s16le).
        REC_ARGS=(
            --channels 1
            --rate 16000
            --encoding signed-integer
            --bits 16
            --type wav
            "$HALDOUT_WAV"
            trim 0.0 "$DURATION_S"
        )
        ;;
    afrecord)
        # afrecord defaults to .aiff; force .wav + explicit format
        # (matches Whisper's transcribe contract).
        REC_ARGS=(
            -f WAVE -d LEI16
            -c 1 -r 16000
            "$HALDOUT_WAV"
        )
        ;;
    arecord)
        REC_ARGS=(
            -f S16_LE
            -c 1 -r 16000
            -d "$DURATION_S"
            "$HALDOUT_WAV"
        )
        ;;
esac

# Run recorder (don't surface its TTY noise — pipe to /dev/null for
# non-error output; let stderr through for real warnings).
"$REC_CMD" "${REC_ARGS[@]}" >/dev/null 2>&1 \
    || fail "Recorder failed (microphone permission? input device busy?). Try again or install SoX."
ok "Recorded $HALDOUT_WAV"

# ---------------------------------------------------------------------------
# Step 4 — verify recording is 16 kHz mono s16le
# ---------------------------------------------------------------------------

# Use `file` (BSD on macOS, GNU on Linux) to confirm WAV magic.
file "$HALDOUT_WAV" | grep -qi "wav" \
    || fail "$HALDOUT_WAV doesn't look like a WAV file — recorder bug?"

# Use `ffprobe` if available (best — reports exact sample rate / channels).
# Falls back to byte-size math: 16 kHz × 2 bytes × N seconds + 44-byte header.
if command -v ffprobe >/dev/null 2>&1; then
    SR=$(ffprobe -v error -select_streams a:0 -show_entries stream=sample_rate,channels -of default=noprint_wrappers=1 "$HALDOUT_WAV" 2>/dev/null)
    info "ffprobe: $SR"
else
    FILE_BYTES=$(stat -f%z "$HALDOUT_WAV" 2>/dev/null || stat -c%s "$HALDOUT_WAV")
    PCM_BYTES=$(( FILE_BYTES - 44 ))
    SAMP_COUNT=$(( PCM_BYTES / 2 ))
    SR_SAMP=$(( SAMP_COUNT / DURATION_S ))
    info "File size: ${FILE_BYTES} bytes; PCM: ${PCM_BYTES} bytes; ~${SR_SAMP} Hz (heuristic)"
fi
ok "Format check passed"

# ---------------------------------------------------------------------------
# Step 5 — playback
# ---------------------------------------------------------------------------

bold "→ Playback"
info "Listen once and verify your mic captured clean audio."
info "(Press Enter to play; Ctrl-C to abort and re-record.)"
read -r _unused

if [[ -n "$PLAY_CMD" ]] && command -v "$PLAY_CMD" >/dev/null 2>&1; then
    "$PLAY_CMD" "$HALDOUT_WAV" >/dev/null 2>&1 || warn "Playback failed (non-fatal; recording is on disk)"
    ok "Played back $HALDOUT_WAV"
else
    warn "No audio player found ($PLAY_CMD). Verify manually."
fi

# ---------------------------------------------------------------------------
# Step 6 — open editor on transcript sidecar
# ---------------------------------------------------------------------------

bold "→ Edit transcript"
info "Open your \$EDITOR on $HALDOUT_TXT"
info "Type the correct Cantonese transcript of what you just said."
info "Save and quit when done. Leave the file empty to abort."

# Pre-populate with a hint comment so the user knows what to type.
if [[ ! -f "$HALDOUT_TXT" ]]; then
    cat > "$HALDOUT_TXT" <<EOF
# Type the correct Cantonese transcript of the recording below.
# Lines starting with '#' are ignored by the WER scorer.
# Example: 你好今日天氣好好
EOF
fi

EDITOR_CMD="${EDITOR:-vi}"
if ! command -v "$EDITOR_CMD" >/dev/null 2>&1; then
    EDITOR_CMD="nano"  # most distros ship this
fi

"$EDITOR_CMD" "$HALDOUT_TXT" \
    || fail "Editor exited non-zero — transcript not saved. Re-run the script."

# ---------------------------------------------------------------------------
# Step 7 — validate transcript (non-empty, comment-stripped)
# ---------------------------------------------------------------------------

TRANSCRIPT=$(grep -v '^[[:space:]]*#' "$HALDOUT_TXT" | grep -v '^[[:space:]]*$' || true)
if [[ -z "${TRANSCRIPT// /}" ]]; then
    fail "Transcript is empty. Re-run and type the correct transcript."
fi

ok "Transcript saved ($(echo "$TRANSCRIPT" | wc -w | tr -d ' ') words)"

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------

bold "✓ Held-out set ready"
info "WAV:  $HALDOUT_WAV"
info "TXT:  $HALDOUT_TXT"
info ""
info "Next steps:"
info "  1. Run pytest tests/voice/test_held_out_eval.py -v"
info "     (the 3 tests will skip if base.pt is missing;"
info "      run scripts/setup-held-out-model.sh first)"
info "  2. (Optional) Run scripts/run_held_out_eval.py for a"
info "     full CLI eval with WER printed to stdout + JSON"
info "     saved under tests/voice/held_out_results/"
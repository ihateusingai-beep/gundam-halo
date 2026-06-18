#!/usr/bin/env bash
# record-held-out.sh — Sprint 32 (Track 31-A) interactive held-out recorder.
#
# Sprint 26 §4.3 ("Track 3 — held-out Cantonese eval"):
#   the user records 30 seconds of Cantonese (a different
#   prompt from the M9-C fixture, e.g. "what's the weather
#   today" or "read me the first three lines of the README"),
#   types the correct transcript, and the script writes
#   `~/.gundam-halo/recordings/held-out-<date>.wav` +
#   `~/.gundam-halo/recordings/held-out-<date>.txt`. The
#   test suite (`backend/tests/voice/test_held_out_eval.py`)
#   then loads the WAV + transcript and asserts WER < 15%
#   on the v0.1.4 WhisperHFASR backend.
#
# Usage:
#   bash scripts/record-held-out.sh             # record 30s (default)
#   bash scripts/record-held-out.sh --duration 60  # record 60s
#   bash scripts/record-held-out.sh --no-playback   # skip the playback step
#
# Exit codes:
#   0 = recording + transcript saved successfully
#   1 = user aborted (Ctrl-C) or recorder missing
#   2 = transcript was empty / aborted
#
# Recording backend (auto-detected, in priority order):
#   1. `rec` (from `sox` — brew install sox)
#   2. `ffmpeg` with avfoundation (Mac native input)
# The script writes a 16-bit signed little-endian mono
# WAV at 16kHz — the exact format `WhisperHFASR.transcribe`
# expects (see backend/app/voice/asr/whisper_hf.py:170).

set -euo pipefail

# ---------------------------------------------------------------------------
# Args
# ---------------------------------------------------------------------------

DURATION=30
PLAYBACK=1
while [ $# -gt 0 ]; do
    case "$1" in
        --duration)
            DURATION="$2"
            shift 2
            ;;
        --no-playback)
            PLAYBACK=0
            shift
            ;;
        -h|--help)
            sed -n '2,30p' "$0"
            exit 0
            ;;
        *)
            echo "Unknown arg: $1" >&2
            exit 1
            ;;
    esac
done

# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

# Honour HALO_HOME override (matches `app.core.config.DEFAULT_HOME`).
HALO_HOME="${HALO_HOME:-$HOME/.gundam-halo}"
RECORDINGS_DIR="$HALO_HOME/recordings"
DATE_STR="$(date +%Y-%m-%d)"
WAV_PATH="$RECORDINGS_DIR/held-out-$DATE_STR.wav"
TXT_PATH="$RECORDINGS_DIR/held-out-$DATE_STR.txt"

mkdir -p "$RECORDINGS_DIR"

# ---------------------------------------------------------------------------
# Pre-flight: pick a recorder
# ---------------------------------------------------------------------------

RECORDER=""
if command -v rec >/dev/null 2>&1; then
    RECORDER="sox"
elif command -v ffmpeg >/dev/null 2>&1; then
    RECORDER="ffmpeg"
else
    echo "ERROR: neither 'rec' (sox) nor 'ffmpeg' found on PATH." >&2
    echo "Install one of:" >&2
    echo "  brew install sox     # gives you 'rec'" >&2
    echo "  brew install ffmpeg" >&2
    exit 1
fi

echo "==> Gundam Halo held-out recorder"
echo "    HALO_HOME     = $HALO_HOME"
echo "    Recordings dir = $RECORDINGS_DIR"
echo "    Date stamp    = $DATE_STR"
echo "    WAV output    = $WAV_PATH"
echo "    TXT output    = $TXT_PATH"
echo "    Duration      = ${DURATION}s"
echo "    Recorder      = $RECORDER"
echo

# ---------------------------------------------------------------------------
# Step 1: pick a prompt
# ---------------------------------------------------------------------------

echo "==> Pick a prompt (so the held-out set differs from the M9-C fixture):"
echo "    1) What's the weather today? (粵語回答天氣)"
echo "    2) Read me the first three lines of the README"
echo "    3) What's on my calendar for tomorrow?"
echo "    4) Free-form (you'll type your own)"
echo
read -r -p "    Pick [1-4]: " PROMPT_CHOICE
case "$PROMPT_CHOICE" in
    1) PROMPT_TEXT="What's the weather today?" ;;
    2) PROMPT_TEXT="Read me the first three lines of the README" ;;
    3) PROMPT_TEXT="What's on my calendar for tomorrow?" ;;
    4)
        read -r -p "    Type your prompt: " PROMPT_TEXT
        ;;
    *)
        echo "Invalid choice: $PROMPT_CHOICE" >&2
        exit 1
        ;;
esac

echo
echo "==> Prompt locked: $PROMPT_TEXT"
echo

# ---------------------------------------------------------------------------
# Step 2: record (with a 3-second countdown)
# ---------------------------------------------------------------------------

echo "==> Recording will start in 3 seconds. Get ready to speak."
for i in 3 2 1; do
    printf "    %s...\n" "$i"
    sleep 1
done
echo "    Recording!"
echo

# Sox / rec: 16-bit signed little-endian, mono, 16kHz. The WhisperHFASR
# pipeline's `_pcm_bytes_to_float32` requires exactly this format
# (see backend/app/voice/asr/whisper_hf.py:170).
if [ "$RECORDER" = "sox" ]; then
    rec -q -r 16000 -c 1 -e signed -b 16 "$WAV_PATH" trim 0 "$DURATION"
else
    # ffmpeg via avfoundation on macOS — `:0` is the default input device.
    ffmpeg -y -loglevel error -f avfoundation -i ":0" \
        -ar 16000 -ac 1 -acodec pcm_s16le \
        -t "$DURATION" "$WAV_PATH"
fi

echo "==> Recording saved to $WAV_PATH"
echo

# ---------------------------------------------------------------------------
# Step 3: playback (optional)
# ---------------------------------------------------------------------------

if [ "$PLAYBACK" -eq 1 ]; then
    echo "==> Playing back for verification..."
    if [ "$RECORDER" = "sox" ]; then
        play -q "$WAV_PATH"
    else
        ffplay -loglevel error -nodisp -autoexit "$WAV_PATH"
    fi
    echo "    Playback done."
    echo
fi

# ---------------------------------------------------------------------------
# Step 4: hand-type the transcript
# ---------------------------------------------------------------------------

echo "==> Type the correct transcript of what you just said."
echo "    (This is the reference text for the WER assertion.)"
echo "    End with Ctrl-D on a new line, or just press Enter twice."
echo

# Read into TRANSCRIPT, allowing multi-line input.
TRANSCRIPT=""
while IFS= read -r line; do
    # Two consecutive empty lines = end of input.
    if [ -z "$line" ] && [ -z "$TRANSCRIPT" ]; then
        TRANSCRIPT=""
        break
    fi
    if [ -z "$line" ] && [ "${TRANSCRIPT: -1}" = $'\n' ]; then
        # Trim trailing newline.
        TRANSCRIPT="${TRANSCRIPT%$'\n'}"
        break
    fi
    if [ -z "$TRANSCRIPT" ]; then
        TRANSCRIPT="$line"
    else
        TRANSCRIPT="${TRANSCRIPT}"$'\n'"$line"
    fi
done

# Trim whitespace.
TRANSCRIPT="$(printf '%s' "$TRANSCRIPT" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"

if [ -z "$TRANSCRIPT" ]; then
    echo
    echo "ERROR: transcript is empty. Aborting (WAV kept at $WAV_PATH)." >&2
    exit 2
fi

# ---------------------------------------------------------------------------
# Step 5: write both files (atomic write for the transcript)
# ---------------------------------------------------------------------------

printf '%s\n' "$TRANSCRIPT" > "$TXT_PATH.tmp"
mv "$TXT_PATH.tmp" "$TXT_PATH"

# Sidecar metadata so the test (or future tooling) can see the prompt
# without re-reading the user's config. JSON-ish, but kept parseable
# by Python's `json.loads` (no trailing-comma hazards).
META_PATH="$RECORDINGS_DIR/held-out-$DATE_STR.meta.json"
cat > "$META_PATH" <<EOF
{
  "date": "$DATE_STR",
  "duration_s": $DURATION,
  "prompt": $(printf '%s' "$PROMPT_TEXT" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))'),
  "wav_path": "$WAV_PATH",
  "txt_path": "$TXT_PATH",
  "recorder": "$RECORDER",
  "recorded_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF

echo
echo "==> Saved:"
echo "    WAV : $WAV_PATH"
echo "    TXT : $TXT_PATH"
echo "    META: $META_PATH"
echo
echo "==> Run the held-out test:"
echo "    cd backend && .venv/bin/pytest tests/voice/test_held_out_eval.py -v"
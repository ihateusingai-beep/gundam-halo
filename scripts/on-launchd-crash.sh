#!/usr/bin/env bash
# scripts/on-launchd-crash.sh — Sprint 43 self-healing crash hook.
#
# launchd fires this script when its `WatchPaths` trigger detects
# that the crash marker file at $HALO_HOME/state/crash_marker has
# changed (which the backend writes via `app.core.watchdog.write_crash_marker`
# on uncaught exception + crash marker writes).
#
# Flow:
#   1. Backend dies unexpectedly (uncaught exception / OOM / SIGKILL).
#   2. Backend's `app/main.py` shutdown hook calls `write_crash_marker()`.
#   3. The marker file change triggers launchd's WatchPaths.
#   4. launchd runs THIS script via `<key>ProgramArguments</key>` in
#      `scripts/com.gundam.halo.plist`.
#   5. This script reads the marker → appends JSON to crash_log.jsonl →
#      removes the marker so the next crash starts clean.
#
# Idempotent: if the marker is missing or malformed, we exit 0 silently
# (nothing to log). We never want to crash launchd itself.
#
# Atomicity: the crash log write is a single `printf >> file` which
# POSIX guarantees atomic for writes < PIPE_BUF (4096 bytes). Each
# crash line is ~150 bytes, well under the limit.

set -uo pipefail

# Resolve HALO_HOME — defaults to ~/.gundam-halo per the project convention.
HALO_HOME="${HALO_HOME:-$HOME/.gundam-halo}"

CRASH_MARKER="$HALO_HOME/state/crash_marker"
CRASH_LOG="$HALO_HOME/state/crash_log.jsonl"

# Ensure the parent dir exists (should, but defensive — launchd may
# call us before the backend has ever written a marker).
mkdir -p "$(dirname "$CRASH_LOG")"

# If no marker, nothing to do. Exit clean so launchd doesn't log an error.
if [[ ! -f "$CRASH_MARKER" ]]; then
    exit 0
fi

# Parse the marker (newline-separated KEY=VALUE).
TIMESTAMP=""
EXIT_CODE=""
REASON=""
UPTIME_SECONDS=""
while IFS='=' read -r key value; do
    case "$key" in
        timestamp) TIMESTAMP="$value" ;;
        exit_code) EXIT_CODE="$value" ;;
        reason) REASON="$value" ;;
        uptime_seconds) UPTIME_SECONDS="$value" ;;
    esac
done < "$CRASH_MARKER"

# Defaults — never fail the script on missing fields.
TIMESTAMP="${TIMESTAMP:-$(date -u +'%Y-%m-%dT%H:%M:%S+00:00')}"
EXIT_CODE="${EXIT_CODE:-1}"
REASON="${REASON:-unknown}"
UPTIME_SECONDS="${UPTIME_SECONDS:-0}"

# Sanity check: refuse to write if any field contains a quote (would
# break the JSON line). Defensive against bugs in the marker writer.
if [[ "$TIMESTAMP" == *'"'* || "$REASON" == *'"'* ]]; then
    echo "on-launchd-crash: refusing to write malformed marker (contains quote)" >&2
    rm -f "$CRASH_MARKER"
    exit 0
fi

# Append the JSONL line. POSIX guarantees atomicity for writes < PIPE_BUF.
printf '{"timestamp":"%s","exit_code":%s,"reason":"%s","uptime_seconds":%s}\n' \
    "$TIMESTAMP" "$EXIT_CODE" "$REASON" "$UPTIME_SECONDS" >> "$CRASH_LOG"

# Remove the marker so the next crash starts clean. We do this AFTER
# the append (not before) so a partial write doesn't leave us without
# a log entry.
rm -f "$CRASH_MARKER"

exit 0

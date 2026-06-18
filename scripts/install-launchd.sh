#!/usr/bin/env bash
# install-launchd.sh — install the Gundam Halo launchd supervisor.
#
# Sprint 26 §4.2 / Sprint 34 Track 2: copies
# scripts/com.gundam.halo.plist to
# ~/Library/LaunchAgents/com.gundam.halo.plist (substituting
# the __HALO_REPO__ and __HALO_HOME__ placeholders with the
# actual user paths) and runs `launchctl load` on it.
#
# Idempotent: if the plist is already loaded, unload it
# first, overwrite the destination, then re-load. Safe to
# re-run after editing the source plist.
#
# Usage:
#   bash scripts/install-launchd.sh
#
# Exit codes:
#   0 = success (or already installed, no change)
#   1 = missing prerequisite (no plist source, no launchctl, etc.)
#   2 = launchctl load failed (plist invalid or already loaded by another user)

set -euo pipefail

# ---------------------------------------------------------------------------
# Pretty logging
# ---------------------------------------------------------------------------

bold() { printf "\033[1m%s\033[0m\n" "$*"; }
ok()   { printf "  \033[32m✓\033[0m %s\n" "$*"; }
warn() { printf "  \033[33m!\033[0m %s\n" "$*"; }
fail() { printf "  \033[31m✗\033[0m %s\n" "$*"; exit 1; }
info() { printf "    %s\n" "$*"; }

# ---------------------------------------------------------------------------
# Path discovery
# ---------------------------------------------------------------------------

# Resolve the absolute path to the repo root (the parent of
# this script's directory). Works even when the script is
# invoked via a relative path or a symlink.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

PLIST_SRC="$REPO_DIR/scripts/com.gundam.halo.plist"
PLIST_LABEL="com.gundam.halo"
PLIST_DEST="$HOME/Library/LaunchAgents/${PLIST_LABEL}.plist"
LOGS_DIR="${HALO_HOME:-$HOME/.gundam-halo}/logs"

# ---------------------------------------------------------------------------
# Pre-flight
# ---------------------------------------------------------------------------

bold "→ Gundam Halo launchd supervisor installer"

# macOS only — launchd is Apple's supervisor.
if [[ "$(uname -s)" != "Darwin" ]]; then
    fail "launchd is macOS-only. Detected: $(uname -s). Use systemd / a different supervisor on Linux."
fi

if ! command -v launchctl >/dev/null 2>&1; then
    fail "launchctl not found. This script requires macOS."
fi

if [[ ! -f "$PLIST_SRC" ]]; then
    fail "Plist source not found: $PLIST_SRC. Did you delete scripts/com.gundam.halo.plist?"
fi

ok "Repo:        $REPO_DIR"
ok "Plist src:   $PLIST_SRC"
ok "Plist dest:  $PLIST_DEST"
ok "Logs dir:    $LOGS_DIR"

# ---------------------------------------------------------------------------
# 1. Create ~/Library/LaunchAgents if missing
# ---------------------------------------------------------------------------

mkdir -p "$(dirname "$PLIST_DEST")"
mkdir -p "$LOGS_DIR"
ok "LaunchAgents + logs dirs ready"

# ---------------------------------------------------------------------------
# 2. If already loaded, unload first (idempotency)
# ---------------------------------------------------------------------------

# `launchctl list` returns "PID\tStatus\tLabel" rows. We grep
# for the Label. The exit code of `launchctl list` is always
# 0 (it's a query), so we check the output.
if launchctl list 2>/dev/null | awk '{print $3}' | grep -qx "$PLIST_LABEL"; then
    warn "Plist already loaded — unloading first for idempotency"
    launchctl unload "$PLIST_DEST" 2>/dev/null || true
fi

# ---------------------------------------------------------------------------
# 3. Substitute placeholders + write the plist
# ---------------------------------------------------------------------------

# We use awk for safe substitution (avoids sed -i portability
# issues between BSD sed and GNU sed).
HALO_REPO="$REPO_DIR"
HALO_HOME="${HALO_HOME:-$HOME/.gundam-halo}"

awk \
    -v repo="$HALO_REPO" \
    -v home="$HALO_HOME" \
    '{
        gsub(/__HALO_REPO__/, repo)
        gsub(/__HALO_HOME__/, home)
        print
    }' \
    "$PLIST_SRC" > "$PLIST_DEST"

# Lock down permissions — the plist is user-scoped, not
# system-scoped, but 0644 is fine (read-only for others).
chmod 0644 "$PLIST_DEST"
ok "Plist rendered to $PLIST_DEST"

# ---------------------------------------------------------------------------
# 4. Validate the plist with plutil
# ---------------------------------------------------------------------------

# plutil -lint returns 0 on valid plists, non-zero on invalid.
# We surface a clear error so the user knows to fix the plist
# before retrying.
if ! plutil -lint "$PLIST_DEST" >/dev/null 2>&1; then
    fail "Plist failed plutil -lint. Inspect with: plutil -lint $PLIST_DEST"
fi
ok "Plist XML is well-formed (plutil -lint)"

# ---------------------------------------------------------------------------
# 5. launchctl load
# ---------------------------------------------------------------------------

# We capture the stderr so we can surface a useful error if
# load fails (e.g. another user has the same Label).
if ! LOAD_ERR=$(launchctl load "$PLIST_DEST" 2>&1); then
    fail "launchctl load failed: $LOAD_ERR"
fi
ok "launchctl load succeeded"

# ---------------------------------------------------------------------------
# 6. Verify the backend started (best-effort)
# ---------------------------------------------------------------------------

# launchd starts the process asynchronously. We give it 3
# seconds to spin up, then check `launchctl list` for the
# label. If the PID is a non-zero number, the process is
# running; if it's "-" or "0", it hasn't started yet (will
# retry on its own throttle interval).
info "Waiting 3s for the backend to spin up..."
sleep 3

LISTING=$(launchctl list 2>/dev/null | awk -v label="$PLIST_LABEL" '$3 == label {print}')
if [[ -z "$LISTING" ]]; then
    warn "Label not found in launchctl list — check logs at $LOGS_DIR/launchd.err.log"
elif echo "$LISTING" | awk '{print $1}' | grep -qE '^[0-9]+$'; then
    PID=$(echo "$LISTING" | awk '{print $1}')
    ok "Backend running under launchd (PID $PID)"
else
    # "-" means "no PID assigned yet" (process spawning)
    warn "Backend still spinning up. Run: launchctl list | grep $PLIST_LABEL"
fi

# ---------------------------------------------------------------------------
# 7. Print next steps
# ---------------------------------------------------------------------------

bold "✓ launchd supervisor installed"

cat <<EOF

The Gundam Halo backend is now supervised by launchd.

Useful commands:
  launchctl list | grep $PLIST_LABEL          # check status
  tail -f $LOGS_DIR/launchd.out.log           # follow stdout
  tail -f $LOGS_DIR/launchd.err.log           # follow stderr
  launchctl stop $PLIST_LABEL                 # stop the backend
  launchctl start $PLIST_LABEL                # start the backend
  bash scripts/uninstall-launchd.sh            # remove the supervisor

If the backend fails to start, check:
  1. $LOGS_DIR/launchd.err.log  (stderr from uvicorn)
  2. cat $PLIST_DEST            (verify placeholders were substituted)
  3. ls $HALO_HOME              (HALO_HOME exists with config.toml)

EOF

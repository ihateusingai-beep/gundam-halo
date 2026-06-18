#!/usr/bin/env bash
# uninstall-launchd.sh — remove the Gundam Halo launchd supervisor.
#
# Sprint 26 §4.2 / Sprint 34 Track 2: stops the backend (if
# running) and removes the plist from
# ~/Library/LaunchAgents/. The user can re-install anytime
# via `bash scripts/install-launchd.sh`.
#
# Idempotent: if the plist isn't installed, this is a no-op
# (exits 0). Safe to re-run.
#
# Usage:
#   bash scripts/uninstall-launchd.sh
#
# Exit codes:
#   0 = success (or already uninstalled)
#   1 = launchctl unload failed (process still running?)

set -euo pipefail

# ---------------------------------------------------------------------------
# Pretty logging
# ---------------------------------------------------------------------------

bold() { printf "\033[1m%s\033[0m\n" "$*"; }
ok()   { printf "  \033[32m✓\033[0m %s\n" "$*"; }
warn() { printf "  \033[33m!\033[0m %s\n" "$*"; }
fail() { printf "  \033[31m✗\033[0m %s\n" "$*"; exit 1; }
info() { printf "    %s\n"; }

# ---------------------------------------------------------------------------
# Path discovery
# ---------------------------------------------------------------------------

PLIST_LABEL="com.gundam.halo"
PLIST_DEST="$HOME/Library/LaunchAgents/${PLIST_LABEL}.plist"

# ---------------------------------------------------------------------------
# Pre-flight
# ---------------------------------------------------------------------------

bold "→ Gundam Halo launchd supervisor uninstaller"

if [[ "$(uname -s)" != "Darwin" ]]; then
    fail "launchd is macOS-only. Detected: $(uname -s)."
fi

# ---------------------------------------------------------------------------
# 1. If loaded, unload (best-effort)
# ---------------------------------------------------------------------------

if [[ ! -f "$PLIST_DEST" ]]; then
    ok "Plist not installed at $PLIST_DEST — nothing to do"
    exit 0
fi

if launchctl list 2>/dev/null | awk '{print $3}' | grep -qx "$PLIST_LABEL"; then
    info "Unloading $PLIST_LABEL..."
    # launchctl unload returns non-zero if the process is
    # still running and won't die; we capture and warn but
    # continue (the file will be removed either way).
    if ! UNLOAD_ERR=$(launchctl unload "$PLIST_DEST" 2>&1); then
        warn "launchctl unload reported: $UNLOAD_ERR"
        info "Trying `launchctl bootout` as a fallback..."
        launchctl bootout "gui/$(id -u)/$PLIST_LABEL" 2>/dev/null || true
    fi
    ok "Plist unloaded"
else
    info "Plist not loaded — skipping unload"
fi

# ---------------------------------------------------------------------------
# 2. Remove the plist
# ---------------------------------------------------------------------------

rm -f "$PLIST_DEST"
ok "Plist removed: $PLIST_DEST"

# ---------------------------------------------------------------------------
# 3. Print next steps
# ---------------------------------------------------------------------------

bold "✓ launchd supervisor uninstalled"

cat <<EOF

The Gundam Halo backend is no longer supervised by launchd.

To remove the logs (optional, ~MB):
  rm -rf ~/.gundam-halo/logs/launchd.{out,err}.log

To re-install the supervisor:
  bash scripts/install-launchd.sh

To run the backend manually (dev mode):
  cd $(dirname "$PLIST_DEST")/../..  # back to the repo root
  cd backend && .venv/bin/uvicorn app.main:app --port 8765

EOF

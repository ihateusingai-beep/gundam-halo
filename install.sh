#!/usr/bin/env bash
# Gundam Halo — one-shot installer (macOS / Linux).
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/ihateusingai-beep/gundam-halo/main/install.sh | bash
#   # or locally:
#   ./install.sh [--no-frontend] [--no-tailscale]
#
# What it does:
#   1. Verifies Python 3.11+, uv, ffmpeg
#   2. Clones the repo (or uses existing $HALO_SRC)
#   3. uv sync in backend/
#   4. Copies config.toml.example to ~/.gundam-halo/config.toml (if missing)
#   5. Prints next steps
set -euo pipefail

# ---------------------------------------------------------------------------
# Flags
# ---------------------------------------------------------------------------

INSTALL_FRONTEND=1
SETUP_TAILSCALE=0  # off by default; user can re-run with --with-tailscale

for arg in "$@"; do
    case "$arg" in
        --no-frontend)
            INSTALL_FRONTEND=0
            ;;
        --with-tailscale)
            SETUP_TAILSCALE=1
            ;;
        -h|--help)
            echo "Usage: $0 [--no-frontend] [--with-tailscale]"
            echo "  --no-frontend   skip the npm install + vite build step"
            echo "  --with-tailscale print Tailscale ACL hints (no auto-install)"
            exit 0
            ;;
    esac
done

# ---------------------------------------------------------------------------
# Pretty logging
# ---------------------------------------------------------------------------

bold() { printf "\033[1m%s\033[0m\n" "$*"; }
ok()   { printf "  \033[32m✓\033[0m %s\n" "$*"; }
warn() { printf "  \033[33m!\033[0m %s\n" "$*"; }
fail() { printf "  \033[31m✗\033[0m %s\n" "$*"; exit 1; }
info() { printf "    %s\n" "$*"; }

# ---------------------------------------------------------------------------
# Step 1 — verify prerequisites
# ---------------------------------------------------------------------------

bold "→ Step 1 / 5 — Checking prerequisites"

# Python
if command -v python3 >/dev/null 2>&1; then
    PY_VERSION="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
    if [[ "$PY_VERSION" == "3.11" || "$PY_VERSION" == "3.12" || "$PY_VERSION" == "3.13" ]]; then
        ok "python3 $PY_VERSION"
    else
        fail "python3 $PY_VERSION (need 3.11–3.13)"
    fi
else
    fail "python3 not found — install Python 3.11+ first"
fi

# uv (fast Python package manager — https://docs.astral.sh/uv/)
if command -v uv >/dev/null 2>&1; then
    ok "uv $(uv --version | awk '{print $2}')"
else
    warn "uv not found — installing"
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # shellcheck disable=SC1091
    source "$HOME/.local/bin/env" 2>/dev/null || true
    command -v uv >/dev/null 2>&1 || fail "uv install failed"
    ok "uv installed"
fi

# ffmpeg (required for Whisper ASR + audio format conversion)
if command -v ffmpeg >/dev/null 2>&1; then
    ok "ffmpeg"
else
    warn "ffmpeg not found — needed for voice layer (Whisper)"
    if [[ "$(uname)" == "Darwin" ]]; then
        info "Install with: brew install ffmpeg"
    else
        info "Install with your distro's package manager (apt/ dnf/ pacman)"
    fi
fi

# Node (only if frontend)
if [[ "$INSTALL_FRONTEND" == "1" ]]; then
    if command -v node >/dev/null 2>&1 && command -v npm >/dev/null 2>&1; then
        ok "node $(node --version), npm $(npm --version)"
    else
        warn "node/npm not found — skipping frontend install (use --no-frontend to suppress)"
        INSTALL_FRONTEND=0
    fi
fi

# ---------------------------------------------------------------------------
# Step 2 — clone (or use existing source)
# ---------------------------------------------------------------------------

bold "→ Step 2 / 5 — Locating source"

REPO_DIR="${HALO_SRC:-$HOME/workspace/gundam-halo}"
if [[ -d "$REPO_DIR/.git" ]]; then
    ok "Using existing repo at $REPO_DIR"
elif [[ -d "$(dirname "$REPO_DIR")" && -d "$REPO_DIR/backend" ]]; then
    ok "Found source at $REPO_DIR"
else
    info "Cloning https://github.com/ihateusingai-beep/gundam-halo.git to $REPO_DIR"
    mkdir -p "$(dirname "$REPO_DIR")"
    git clone https://github.com/ihateusingai-beep/gundam-halo.git "$REPO_DIR"
    ok "Cloned"
fi

# ---------------------------------------------------------------------------
# Step 3 — backend dependencies
# ---------------------------------------------------------------------------

bold "→ Step 3 / 5 — Installing backend dependencies"

cd "$REPO_DIR/backend"
uv sync --extra voice 2>&1 | tail -5 || fail "uv sync failed"
ok "uv sync (backend + voice extras)"

# ---------------------------------------------------------------------------
# Step 4 — config.toml
# ---------------------------------------------------------------------------

bold "→ Step 4 / 5 — Writing ~/.gundam-halo/config.toml"

HALO_HOME="${HALO_HOME:-$HOME/.gundam-halo}"
mkdir -p "$HALO_HOME/projects" "$HALO_HOME/logs"
CONFIG="$HALO_HOME/config.toml"
if [[ -f "$CONFIG" ]]; then
    warn "$CONFIG already exists — leaving untouched"
    info "Edit it manually: $CONFIG"
else
    cp "$REPO_DIR/config.toml.example" "$CONFIG"
    ok "Wrote $CONFIG"
    info "Edit it to set your MiniMax API key and Telegram bot token."
fi

# .env
ENV_FILE="$HALO_HOME/.env"
if [[ ! -f "$ENV_FILE" ]]; then
    cat > "$ENV_FILE" <<EOF
# Gundam Halo — environment overrides
# Anything you put here is loaded by the backend at startup.
# Don't commit this file.

# LLM
MINIMAX_API_KEY=

# Telegram (optional; empty = dry-run mode)
GUNDAM_HALO_TG_TOKEN=
EOF
    ok "Wrote $ENV_FILE"
    info "Set MINIMAX_API_KEY before running the agent."
fi

# ---------------------------------------------------------------------------
# Step 5 — frontend build (optional)
# ---------------------------------------------------------------------------

bold "→ Step 5 / 5 — Building frontend (optional)"

if [[ "$INSTALL_FRONTEND" == "1" ]]; then
    cd "$REPO_DIR/frontend"
    if [[ ! -d node_modules ]]; then
        info "Running npm install (this can take a minute)..."
        npm install --silent 2>&1 | tail -5 || fail "npm install failed"
    fi
    info "Building production bundle..."
    npm run build 2>&1 | tail -5 || fail "npm run build failed"
    ok "Frontend built (dist/ ready)"
else
    info "Skipped (use --no-frontend to suppress)"
fi

# ---------------------------------------------------------------------------
# Tailscale hints
# ---------------------------------------------------------------------------

if [[ "$SETUP_TAILSCALE" == "1" ]]; then
    bold "→ Tailscale notes"
    if command -v tailscale >/dev/null 2>&1; then
        ok "tailscale $(tailscale version | head -1)"
        info "Make sure Tailscale is up: tailscale up"
        info "Get your hostname: tailscale status"
    else
        warn "tailscale not installed"
        info "Install from https://tailscale.com/download and run: tailscale up"
    fi
    info "Gundam Halo expects Tailscale ACLs to allow your devices to reach the gateway on port 8765."
fi

# ---------------------------------------------------------------------------
# Next steps
# ---------------------------------------------------------------------------

bold "✓ Install complete"

cat <<EOF

Next steps:

  1. Edit your config:
       \$$EDITOR $CONFIG
       \$$EDITOR $ENV_FILE        # set MINIMAX_API_KEY

  2. Start the backend (dev mode):
       cd $REPO_DIR/backend
       .venv/bin/uvicorn app.main:app --reload --port 8765

  3. (optional) Start the dashboard:
       cd $REPO_DIR/frontend
       npx vite --port 5173

  4. Verify with the smoke test:
       python3 $REPO_DIR/scripts/smoke_test.py

  5. (optional) Build the Tauri desktop app:
       cd $REPO_DIR/frontend
       npm run tauri dev

EOF

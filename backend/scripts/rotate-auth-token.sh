#!/usr/bin/env bash
# scripts/rotate-auth-token.sh — Sprint 48
# Replace the existing bearer token in $HALO_HOME/.env.
# The backend rejects the old token immediately on restart.

set -euo pipefail

HALO_HOME="${HALO_HOME:-$HOME/.gundam-halo}"
ENV_FILE="$HALO_HOME/.env"

if [[ ! -f "$ENV_FILE" ]]; then
    echo "ERROR: $ENV_FILE not found. Run scripts/generate-auth-token.sh first." >&2
    exit 1
fi

NEW_TOKEN=$(openssl rand -base64 32 | tr -d '=/+' | head -c 43)

if grep -q '^HALO_API_TOKEN=' "$ENV_FILE"; then
    if [[ "$OSTYPE" == "darwin"* ]]; then
        sed -i '' "s|^HALO_API_TOKEN=.*|HALO_API_TOKEN=$NEW_TOKEN|" "$ENV_FILE"
    else
        sed -i "s|^HALO_API_TOKEN=.*|HALO_API_TOKEN=$NEW_TOKEN|" "$ENV_FILE"
    fi
else
    echo "HALO_API_TOKEN=$NEW_TOKEN" >> "$ENV_FILE"
fi
chmod 600 "$ENV_FILE"

echo ""
echo "✓ Token rotated."
echo ""
echo "Restart the Gundam Halo backend + Tauri shell to pick up the new token:"
echo "  cd ~/workspace/working/gundam-halo/backend && .venv/bin/uvicorn app.main:halo_app --port 8765"
echo ""
echo "  New token (one-time display):"
echo "    $NEW_TOKEN"
#!/usr/bin/env bash
# scripts/generate-auth-token.sh — Sprint 48
# Bootstrap or refresh the bearer token used by `app.core.auth.require_auth`.
# Writes (or rotates) $HALO_HOME/.env with HALO_API_TOKEN=<random-32-byte>.
# Idempotent: re-running rotates the existing token.

set -euo pipefail

HALO_HOME="${HALO_HOME:-$HOME/.gundam-halo}"
ENV_FILE="$HALO_HOME/.env"

# 1. Create halo_home if needed.
if [[ ! -d "$HALO_HOME" ]]; then
    echo "Creating $HALO_HOME..."
    mkdir -p "$HALO_HOME"/{logs,recordings,models,projects,memory,state,skills}
fi

# 2. Ensure .env exists.
if [[ ! -f "$ENV_FILE" ]]; then
    echo "Creating $ENV_FILE (mode 600)..."
    touch "$ENV_FILE"
    chmod 600 "$ENV_FILE"
fi

# 3. Generate 32 random bytes, base64-encode, strip padding.
NEW_TOKEN=$(openssl rand -base64 32 | tr -d '=/+' | head -c 43)

# 4. Replace or append the HALO_API_TOKEN line.
if grep -q '^HALO_API_TOKEN=' "$ENV_FILE"; then
    # macOS sed -i '' vs Linux sed -i.
    if [[ "$OSTYPE" == "darwin"* ]]; then
        sed -i '' "s|^HALO_API_TOKEN=.*|HALO_API_TOKEN=$NEW_TOKEN|" "$ENV_FILE"
    else
        sed -i "s|^HALO_API_TOKEN=.*|HALO_API_TOKEN=$NEW_TOKEN|" "$ENV_FILE"
    fi
else
    echo "HALO_API_TOKEN=$NEW_TOKEN" >> "$ENV_FILE"
fi

# 5. Defensive chmod (in case the file was edited by something that
#    reset permissions, e.g. a backup tool).
chmod 600 "$ENV_FILE"

echo ""
echo "✓ HALO_API_TOKEN written to $ENV_FILE (mode 600)."
echo "  Restart the Gundam Halo backend + Tauri shell to pick it up:"
echo "    cd ~/workspace/working/gundam-halo/backend && .venv/bin/uvicorn app.main:halo_app --port 8765"
echo ""
echo "  New token (one-time display — copy now, won't be shown again):"
echo "    $NEW_TOKEN"
# Sprint 48 — Auth layer for /api/system/* + write-side /voice/* + /api/setup/*

**Date**: 2026-06-29
**Status**: Draft
**Author**: Mavis
**Priority**: High (closes the 3-remaining "no auth yet" notes from Sprint 13-43)
**Depends on**: Sprint 13 (Tailscale locality), Sprint 43 (system endpoints
+ crash log), Sprint 44 (setup wizard endpoints)

## Goal

Closes the **3 long-standing "no auth yet" notes** scattered across
the codebase:
- `app/api/system.py:170` — "Sprint 45 will add an auth layer"
  (Sprint 43 just shipped the surface).
- `app/api/setup.py:27` — "no auth yet (single-user assumption)".
- `app/api/secrets.py:14` — "no auth middleware yet (single-user)".

Today, the entire backend assumes the network is local (Tailscale
ACL or 127.0.0.1 binding). If `server.bind_address = 0.0.0.0` slips
through (the install.sh `--with-tailscale` path), **any device on
the Tailscale tailnet can `POST /api/system/clear-crash-log`**,
`**POST /api/system/cancel-restart**`, **`POST /voice/run-finetune`**
(spawn 30-60 min LoRA training), or **`PUT /api/setup/...`** (swap
LLM/ASR backend, write to config.toml). That's a real blast radius.

Sprint 48 adds a **bearer token** (chmod 600 in `~/.gundam-halo/.env`)
as a hard requirement, plus **Tailscale identity allowlist** as
defence-in-depth. Both checks must pass on protected endpoints.

## Why now

- Sprint 43 + 44 shipped the privileged endpoints; the "Sprint 45
  will add auth" note has been aging for 5 sprints.
- User has been gradually turning on more write-side features
  (held-out eval, fine-tune, crash log clear, setup wizard
  writes); the privileged surface is now 7+ endpoints.
- Single-user Mac doesn't mean "no auth" — it means "only this
  user + this Mac should be able to drive these actions".
  A shared-secret token is the simplest correct answer.

## Why both bearer + Tailscale

The user explicitly chose belt + braces. The two checks catch
different attack vectors:

| Threat | Bearer alone | Tailscale alone | Both |
|---|---|---|---|
| Random Tailscale peer on the tailnet calls /voice/run-finetune | ✅ rejected (no token) | ❌ passes (peer is in tailnet) | ✅ rejected |
| Token leaks (committed to dotfiles by accident) | ❌ passes (any caller with token) | ✅ rejected (no Tailscale identity header) | ✅ rejected |
| Localhost curl with the leaked token | ❌ passes (no Tailscale header) | ✅ rejected (no identity) | ✅ rejected |
| Both leaked | ❌ passes | ❌ passes | ❌ passes (out of scope; the only fix is key rotation) |

The "both leaked" case is the residual risk and is mitigated by
easy token rotation (one CLI: `gundam-halo rotate-token`).

## Design

### 1. Token storage

`$HALO_HOME/.env` (chmod 600) holds the bearer token. New env var:

```
# ~/.gundam-halo/.env  (mode 600)
HALO_API_TOKEN=openssl_random_base64_32bytes
```

Sprint 48 ships a bootstrap script (`scripts/generate-auth-token.sh`)
that:
1. Checks if `$HALO_HOME/.env` exists; if not, creates it (chmod 600).
2. Checks if `HALO_API_TOKEN` is set; if not, generates a
   32-byte URL-safe base64 token via `openssl rand -base64 32`.
3. Appends or updates the line.
4. **Re-chmods to 600** (defensive in case the file was edited by
   a tool that stripped permissions).

The Tauri shell reads this token on startup and stores it in
a `TauriState` (process memory, never written to disk a second
time). The frontend's `api.ts` auto-injects it into every fetch
via a wrapper around `request<T>()`.

The Python backend reads the same `.env` file via `python-dotenv`
at startup (already wired in Sprint 22 — see `app/core/config_loader.py`).
The token lands in `os.environ["HALO_API_TOKEN"]` before the FastAPI
app starts.

### 2. Auth dependency

```python
# backend/app/core/auth.py — Sprint 48 NEW

from fastapi import Header, HTTPException, Depends, status
from typing import Annotated


async def require_auth(
    authorization: Annotated[str | None, Header()] = None,
) -> AuthContext:
    """FastAPI dependency: 401 unless bearer + Tailscale identity
    both pass (Sprint 48).

    Returns an `AuthContext` with the resolved identity (caller_id,
    source IP) for audit logging.
    """
    # Stage 1: bearer token (HARD requirement).
    expected = os.environ.get("HALO_API_TOKEN")
    if not expected:
        # Bootstrap error: backend started without a token.
        # Refuse EVERY protected request (fail-closed).
        raise HTTPException(
            status_code=503,
            detail=(
                "Backend is not configured for auth. Run "
                "`scripts/generate-auth-token.sh` to create "
                "$HALO_HOME/.env with HALO_API_TOKEN."
            ),
        )

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    presented = authorization[len("Bearer "):].strip()
    if not hmac.compare_digest(presented, expected):
        raise HTTPException(status_code=401, detail="Invalid bearer token")

    # Stage 2: Tailscale identity (defence-in-depth, OPTIONAL enhance).
    # If the tailscaled socket is unreachable, log a WARNING and
    # let the request through (bearer is enough for single-Mac
    # localhost setups that don't use Tailscale).
    identity = _verify_tailscale_identity()
    if identity is None:
        if _tailscaled_available():
            # Socket reachable but request didn't carry the
            # identity header (e.g. not coming through Tailscale).
            # Reject: the protected endpoints should only be
            # callable from inside the Tailscale tailnet.
            raise HTTPException(
                status_code=401,
                detail=(
                    "Missing Tailscale identity header. The protected "
                    "endpoints require both a bearer token AND a "
                    "Tailscale-WhoIs-verified identity. Are you "
                    "calling from a Tailscale-routed device?"
                ),
            )
        else:
            # tailscaled not running (e.g. dev on localhost).
            # Log + accept; bearer is enough.
            logger.warning(
                "Sprint 48 auth: tailscaled socket unreachable, "
                "skipping identity check (bearer-only mode)."
            )

    return AuthContext(
        caller_id=identity.user_id if identity else "localhost-bearer",
        source_ip=identity.src_ip if identity else "127.0.0.1",
    )


@dataclass(frozen=True)
class AuthContext:
    """Resolved identity for audit logging."""
    caller_id: str
    source_ip: str
```

### 3. Tailscale identity verification

```python
# backend/app/core/auth.py — Sprint 48 (continued)

_TAILSCALED_SOCKET_CANDIDATES = [
    "/var/run/tailscale/tailscaled.sock",  # Linux
    "/Library/Tailscale/tailscaled.sock",  # macOS (rare; not in Tailscale 1.x)
    "localhost:41112",  # macOS Tailscale 1.x local API
]


def _tailscaled_available() -> bool:
    """Cheap probe: any of the known tailscaled local API
    endpoints responds. Returns True if reachable, False otherwise.

    Cached for 60s so we don't hammer the socket on every request.
    """
    # ... probe logic ...


def _verify_tailscale_identity() -> TailscaleIdentity | None:
    """Read the Tailscale-Identity header from the request, call
    local WhoIs, return the resolved identity.

    Returns None if either:
      - Tailscale-Identity header is absent (caller isn't routed
        through Tailscale), OR
      - WhoIs returns a peer not in the allowlist.
    """
    identity_json = request.headers.get("Tailscale-Identity")  # ...
    if not identity_json:
        return None
    # Parse + base64-decode the JWT (Tailscale identity is a
    # short-lived signed JWT). Verify the signature via tailscaled.
    payload = _decode_tailscale_jwt(identity_json)
    if not payload:
        return None
    # Optional: enforce allowlist (e.g. only tag:admin).
    if settings.auth.tailscale_allowed_tags:
        peer_tags = payload.get("Tags", [])
        if not any(t in settings.auth.tailscale_allowed_tags for t in peer_tags):
            return None
    return TailscaleIdentity(
        user_id=payload.get("UserProfile", {}).get("LoginName", "unknown"),
        src_ip=payload.get("Address", "unknown"),
        tags=payload.get("Tags", []),
    )
```

Allowlist config (in `config.toml`):
```toml
[security.auth]
# When set, only Tailscale peers with these tags may call the
# protected endpoints. Empty list = no tag filter (any authenticated
# Tailscale peer passes). Requires the bearer token either way.
tailscale_allowed_tags = ["tag:admin"]
```

### 4. Wire-up — protected endpoints

Two patterns:

**Pattern A** — `Depends(require_auth)` on a single route:

```python
# backend/app/api/system.py
from app.core.auth import require_auth, AuthContext

@router.post("/clear-crash-log", dependencies=[Depends(require_auth)])
async def post_clear_crash_log(...) -> dict[str, Any]:
    ...
```

**Pattern B** — `APIRouter(dependencies=[...])` for a whole router:

```python
# backend/app/api/voice_config_api.py
# All write-side /voice/* endpoints get auth in one shot.
# Read-side endpoints (GET /voice/config, GET /voice/status) stay
# unprotected — Tailscale-locality is enough for the dashboard's
# periodic status fetch.

# Approach: split voice_config_api into two routers.
# - `router` (existing) — read-only, no auth
# - `write_router` (new) — POST /voice/run-finetune, POST /voice/run-held-out-eval, with auth
```

Sprint 48 uses Pattern A for `/api/system/*` (each endpoint gets
`dependencies=[Depends(require_auth)]`) and Pattern B for the
write-side `/voice/*` (split router).

For `/api/setup/*`, all PUT/POST/DELETE endpoints get Pattern A;
the read-only GET `/api/setup/state` stays unprotected (the
wizard needs to fetch state before the user has a chance to
authenticate via the form).

### 5. Frontend auth injection

```typescript
// frontend/src/lib/api.ts — Sprint 48 change

async function authedRequest<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  // The Tauri shell passes the bearer token via the
  // `window.__haloApiToken` global on startup.
  // NEVER read it directly outside this module.
  const token = (window as any).__haloApiToken as string | undefined;
  const headers: Record<string, string> = {
    ...(init.headers as Record<string, string> | undefined),
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  // Tailscale identity is injected automatically by the Tailscale
  // daemon on requests routed through the tailnet (HTTP header
  // Tailscale-Identity). No app code change needed.
  return request<T>(path, { ...init, headers });
}
```

`window.__haloApiToken` is set by the Tauri Rust shell at startup:

```rust
// frontend/src-tauri/src/auth.rs — Sprint 48 NEW
use tauri::Manager;

#[tauri::command]
pub async fn get_api_token(state: State<'_, AuthState>) -> Result<String, String> {
    Ok(state.token.clone())
}

pub fn bootstrap_auth(app: &tauri::App) -> Result<(), String> {
    // Read ~/.gundam-halo/.env at startup; extract HALO_API_TOKEN.
    let token = read_env_token(&app.path().home_dir()?)?;
    // Expose to the webview via init_script.
    let token_json = serde_json::to_string(&token)
        .map_err(|e| format!("failed to serialise token: {e}"))?;
    let init_script = format!(
        "window.__haloApiToken = JSON.parse({token_json:?});"
    );
    app.get_webview_window("main").unwrap()
        .eval(init_script)
        .map_err(|e| e.to_string())?;
    app.manage(AuthState { token });
    Ok(())
}
```

The Rust shell reads the token **once** at startup. The token
never goes to disk from the Tauri side. If the file is changed
on disk, the user must restart the app for the new token to take
effect (documented in `docs/SECURITY-HARDENING.md`).

### 6. Token rotation

```bash
# scripts/rotate-auth-token.sh — Sprint 48 NEW
#!/usr/bin/env bash
set -euo pipefail

HALO_HOME="${HALO_HOME:-$HOME/.gundam-halo}"
ENV_FILE="$HALO_HOME/.env"

if [[ ! -f "$ENV_FILE" ]]; then
    echo "ERROR: $ENV_FILE not found. Run scripts/generate-auth-token.sh first." >&2
    exit 1
fi

# Generate new token.
NEW_TOKEN=$(openssl rand -base64 32 | tr -d '=/+' | head -c 43)

# Replace or append in .env.
if grep -q "^HALO_API_TOKEN=" "$ENV_FILE"; then
    # macOS sed -i '' vs Linux sed -i
    if [[ "$OSTYPE" == "darwin"* ]]; then
        sed -i '' "s|^HALO_API_TOKEN=.*|HALO_API_TOKEN=$NEW_TOKEN|" "$ENV_FILE"
    else
        sed -i "s|^HALO_API_TOKEN=.*|HALO_API_TOKEN=$NEW_TOKEN|" "$ENV_FILE"
    fi
else
    echo "HALO_API_TOKEN=$NEW_TOKEN" >> "$ENV_FILE"
fi
chmod 600 "$ENV_FILE"

echo "✓ Token rotated. Restart the backend + Tauri shell to pick it up."
echo "  New token: $NEW_TOKEN"
```

The user runs this once if they suspect the token has leaked
(and again annually as a hygiene measure). The old token is
forgotten by the backend on restart; the new one is the only
valid token until the next rotation.

### 7. Audit log

Every successful protected request appends one line to
`$HALO_HOME/logs/audit.log`:

```json
{"ts": "2026-06-29T20:00:00+00:00", "caller_id": "tag:admin",
 "src_ip": "100.100.100.42", "method": "POST", "path":
 "/api/system/clear-crash-log", "status": 200, "duration_ms": 12}
```

Failures are logged at WARNING with the reason (missing header,
bad token, WhoIs mismatch). The audit log is rotated at
1 MB by the existing `app/core/security.py::rotate_audit_log`
helper (TODO from Sprint 13 — Sprint 48 implements it as a
side-effect of needing it).

### 8. Graceful localhost dev mode

The `scripts/run-dev.sh` script (already exists) sets
`HALO_API_TOKEN=dev-token-insecure` in the venv before starting
the backend. The Tauri shell in dev mode reads the same env var.
The `.env.dev` file is gitignored. This lets the user iterate
without running `generate-auth-token.sh` every time.

In dev mode, the Tailscale check still runs but the allowlist
is empty → any peer passes. The audit log records "dev-mode"
in `caller_id`.

### 9. Setup wizard integration

Sprint 44's setup wizard has 11 endpoints. Sprint 48 protects
all of them with `dependencies=[Depends(require_auth)]`. The
wizard's flow is:
1. User opens `/setup` route.
2. Frontend calls `GET /api/setup/state` (unprotected).
3. If state shows "needs_setup", frontend prompts for token
   (or auto-injects from `window.__haloApiToken`).
4. Subsequent POST/PUT calls carry the token.

A **first-run flow** is also added: if `HALO_HOME/.env` doesn't
exist on backend startup, the backend logs a clear warning and
auto-runs `generate-auth-token.sh`, writing the generated token
to `state/auth_first_run.json` (chmod 600). The setup wizard's
welcome step shows the user the generated token (one-time
display) so they can save it.

## Files to create / modify

### Backend (~600 LoC)

- `backend/app/core/auth.py` NEW (~250 LoC — `require_auth`
  dependency + `AuthContext` + Tailscale WhoIs + JWT decode).
- `backend/app/core/security.py` NEW (~100 LoC — `rotate_audit_log`
  helper finally implemented; JSONL format per `audit-log`
  pattern from Sprint 13).
- `backend/app/api/system.py` (modify — 3 endpoints
  `+ dependencies=[Depends(require_auth)]`:
  `clear-crash-log` + `cancel-restart` + `health-detailed`).
- `backend/app/api/voice_config_api.py` (modify — split router:
  `router` stays read-only; new `write_router` with auth dep
  for `run-held-out-eval` + `run-finetune` + the new
  `clear-eval-job` if it exists).
- `backend/app/api/setup.py` (modify — protect all write-side
  endpoints; leave `GET /state` open for first-run flow).
- `backend/app/main.py` (modify — `app.include_router(...,
  dependencies=[Depends(require_auth)])` for `write_router`).
- `backend/app/core/config.py` (modify — add
  `SecurityAuthConfig` with `tailscale_allowed_tags: list[str] = []`).
- `backend/scripts/generate-auth-token.sh` NEW (~40 LoC bash).
- `backend/scripts/rotate-auth-token.sh` NEW (~30 LoC bash).
- `backend/scripts/run-dev.sh` (modify — set
  `HALO_API_TOKEN=dev-token-insecure` if not already set).

### Frontend (~200 LoC)

- `frontend/src-tauri/src/auth.rs` NEW (~80 LoC — `bootstrap_auth`
  + `get_api_token` Tauri command).
- `frontend/src-tauri/src/lib.rs` (modify — register
  `bootstrap_auth` in `setup`; add `get_api_token` to
  `invoke_handler`).
- `frontend/src-tauri/Cargo.toml` (modify — add `base64` +
  `json` + `dotenvy` deps; `dotenvy` already in tree).
- `frontend/src/lib/api.ts` (modify — `authedRequest()` wrapper
  that auto-injects `Authorization: Bearer <token>` from
  `window.__haloApiToken`).
- `frontend/src/lib/auth-bootstrap.ts` NEW (~40 LoC — fetches
  token from Tauri on app start, sets `window.__haloApiToken`).
- `frontend/src/main.tsx` (modify — call `auth-bootstrap.ts`
  on mount before any other api call).

### Docs (~400 LoC)

- `docs/SECURITY-HARDENING.md` (modify — add the "Auth layer"
  section; document the token format, rotation, Tailscale
  allowlist; remove the "Sprint 45 will add" note; expand
  the "Endpoints currently unprotected" section to
  "Endpoints protected by Sprint 48").
- `docs/FEATURE-SPEC-SPRINT48-AUTH-LAYER.md` (this file).
- `docs/CHANGELOG.md` (entry under [Unreleased]).
- `config.toml.example` (modify — add `[security.auth]`
  section with the `tailscale_allowed_tags` example).

### Tests (~25 new tests)

- `backend/tests/core/test_auth.py` NEW (~150 LoC, 7 tests):
  - `test_require_auth_passes_with_valid_bearer` — happy path.
  - `test_require_auth_401s_with_missing_header`.
  - `test_require_auth_401s_with_wrong_token` — uses
    `hmac.compare_digest`-safe comparison.
  - `test_require_auth_503s_when_token_not_configured` —
    no HALO_API_TOKEN env var → fail-closed.
  - `test_require_auth_skips_tailscale_check_when_socket_unavailable`
    — mocked `_tailscaled_available()` returns False.
  - `test_require_auth_401s_when_tailscale_available_but_no_identity_header`.
  - `test_require_auth_401s_when_tailscale_identity_tag_not_in_allowlist`.

- `backend/tests/core/test_security.py` NEW (~80 LoC, 4 tests):
  - `test_audit_log_rotation_at_size_cap` — writes 1.5 MB,
    verifies rotation produces a new file.
  - `test_audit_log_appends_jsonl_line` — single entry round-trip.
  - `test_audit_log_resilient_to_malformed_lines` — corrupted
    line doesn't crash the appender.
  - `test_audit_log_mtime_preserved_on_rotation` — defensive.

- `backend/tests/api/test_system_auth.py` NEW (~80 LoC, 3 tests):
  - `test_clear_crash_log_requires_auth`.
  - `test_cancel_restart_requires_auth`.
  - `test_health_detailed_requires_auth`.

- `backend/tests/api/test_voice_write_auth.py` NEW (~80 LoC,
  3 tests):
  - `test_run_finetune_requires_auth`.
  - `test_run_held_out_eval_requires_auth`.
  - `test_voice_get_endpoints_stay_unprotected` — regression
    (read-side should not 401).

- `backend/tests/api/test_setup_auth.py` NEW (~60 LoC, 2 tests):
  - `test_setup_state_get_stays_unprotected`.
  - `test_setup_step_put_requires_auth`.

- `backend/tests/scripts/test_generate_auth_token.py` NEW
  (~50 LoC, 2 tests):
  - `test_creates_env_file_with_token_if_missing`.
  - `test_appends_to_existing_env_file_preserving_other_vars`.

- `backend/tests/scripts/test_rotate_auth_token.py` NEW
  (~40 LoC, 2 tests):
  - `test_rotates_existing_token` — old token rejected after
    rotation, new token accepted.
  - `test_fails_cleanly_if_env_file_missing`.

- `frontend/src/lib/api.test.ts` (extend existing — +2 tests):
  - `test_authedRequest_injects_bearer_from_window_global`.
  - `test_authedRequest_skips_injection_when_no_token`.

Total new tests: **~25** (split across 8 test files).

## Acceptance criteria

- [ ] `scripts/generate-auth-token.sh` creates `$HALO_HOME/.env`
  with `HALO_API_TOKEN` (mode 600) when missing.
- [ ] `scripts/rotate-auth-token.sh` replaces the existing
  token; old token rejected by the backend, new token accepted.
- [ ] `POST /api/system/clear-crash-log` returns 401 with no
  Authorization header.
- [ ] `POST /api/system/clear-crash-log` returns 401 with wrong
  bearer.
- [ ] `POST /api/system/clear-crash-log` returns 200 with
  correct bearer.
- [ ] `POST /api/system/cancel-restart` + `GET /api/system/health-detailed`
  follow the same 401/200 pattern.
- [ ] `POST /voice/run-finetune` + `POST /voice/run-held-out-eval`
  follow the same pattern.
- [ ] `GET /voice/config` + `GET /voice/status` + `GET /api/system/gauges`
  stay unprotected (read-side, Tailscale-locality is enough).
- [ ] `GET /api/setup/state` stays unprotected (first-run flow).
- [ ] `POST /api/setup/llm/validate` etc. require auth.
- [ ] Tailscale identity check enforced when `tailscaled`
  socket is reachable.
- [ ] Tailscale check skipped (warning logged) when
  `tailscaled` is unreachable.
- [ ] Audit log appended to `$HALO_HOME/logs/audit.log` for
  every protected call (success + failure).
- [ ] Tauri shell sets `window.__haloApiToken` on startup.
- [ ] Frontend `api.ts` auto-injects bearer in every fetch.
- [ ] Full backend pytest (excl slow tts) stays green: **+25 new tests**
  vs Sprint 46 baseline of 1343.
- [ ] Frontend tsc 0 errors + vitest +2 new tests.
- [ ] `cargo check --tests` clean.

## Version bump

`__version__` 0.1.19 → **0.1.20** (MINOR bump per Mavis memory rule —
adds a new security contract; the first auth-protected endpoints
land here, so it's a meaningful new capability boundary, not just
a bug fix). 4 surfaces synced.

## Out of scope (deferred to future sprints)

- **Token expiry** — current token is a long-lived shared secret.
  Future: short-lived JWTs (15-min TTL) issued by a token endpoint,
  refreshed via a separate long-lived refresh token. Adds significant
  complexity for marginal security gain in a single-user context.
- **Per-user RBAC** — current design treats all authed callers
  as equivalent. Future: roles (admin / read-only / etc.).
- **Rate limiting** — fastapi-limiter or similar to throttle
  brute-force attempts. Not needed at single-user scale.
- **mTLS** — could replace bearer for defence in depth but adds
  cert-management overhead. Not needed in single-user context.
- **Per-endpoint scopes** — currently it's all-or-nothing
  protected; future: scope the protection (e.g. "fine-tune"
  scope separate from "system-clear-crash-log" scope).
- **Audit log remote sink** — currently local JSONL. Future:
  forward to a SIEM / central log aggregator.

## Why this is the right minimal surface

The 7 protected endpoints cover ALL the privileged actions in
Gundam Halo:
- `clear-crash-log` — admin: wipe watchdog history
- `cancel-restart` — admin: abort self-restart
- `health-detailed` — admin: read crash log
- `run-finetune` — admin: spawn 30-60 min LoRA training
- `run-held-out-eval` — admin: spawn eval job
- `/api/setup/*` (10 endpoints) — admin: change LLM/ASR/theme/Tailscale config
- (the rotate-audit-log endpoint is internal, called by the
  audit logger itself, no auth)

The read-side (`/voice/config`, `/voice/status`, `/api/system/gauges`,
`/api/system/info`, `/api/setup/state`) stays open. These are
called by the dashboard on a 10-30s polling cadence; requiring
auth would mean injecting the token into every poll (a small
overhead but pointless — the only thing they reveal is "is the
backend up" + "what config is loaded", both of which are
public-knowledge on the local machine anyway). The Tailscale
locality check + `server.bind_address = 127.0.0.1` default
provides the practical security for the read side.

## After Sprint 48

The "no auth yet" notes in `system.py`, `setup.py`, and
`secrets.py` all get updated to "Sprint 48 auth layer in place".
The next time someone considers an unprotected write endpoint,
the convention is clear: use `Depends(require_auth)`.

M12 hardening backlog (from `docs/SECURITY-HARDENING.md`) loses
its "auth layer" item. Remaining items: macOS Seatbelt profile,
Linux AppArmor, audit log remote sink.
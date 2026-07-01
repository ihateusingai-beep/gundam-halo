"""Sprint 48 — auth layer.

Closes the long-standing "no auth yet" notes scattered across
`app/api/system.py`, `app/api/setup.py`, and `app/api/secrets.py`.

Two checks must pass on protected endpoints:

1. **Bearer token (HARD requirement)** — `Authorization: Bearer
   <token>` header must match `os.environ["HALO_API_TOKEN"]`
   (loaded by `app/core/config_loader.py` from `$HALO_HOME/.env`).
   Constant-time comparison via `hmac.compare_digest` to avoid
   timing attacks. If the env var isn't set, the dependency
   FAILS CLOSED (503) — never defaults to "no auth required".

2. **Tailscale identity (defence-in-depth, OPTIONAL enhance)** —
   when the local `tailscaled` socket is reachable, the request
   must carry a valid `Tailscale-Identity` JWT header AND the
   peer's tags must satisfy `config.security.auth.tailscale_allowed_tags`
   (default: empty list = no tag filter, any peer passes). If
   `tailscaled` is unreachable (e.g. dev on localhost without
   Tailscale login), the identity check is skipped and a WARNING
   is logged — bearer alone is enough.

The combination gives belt + braces:
  - Random Tailscale peer without a token → 401 (bearer fails).
  - Leaked token used from a non-Tailscale device → 401 (identity fails).
  - Leaked token + leaked identity from a different device → 401 (identity fails).
  - Both leak to a fully-trusted Tailscale peer → succeeds
    (residual risk; mitigated by easy token rotation via
    `scripts/rotate-auth-token.sh`).

Failures are appended to `$HALO_HOME/logs/audit.log` via
`app.core.security.append_audit_log()`.
"""
from __future__ import annotations

import hmac
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Annotated, Any

import requests

from fastapi import Header, HTTPException, Request

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tailscale socket discovery — local API endpoints
# ---------------------------------------------------------------------------

# macOS Tailscale 1.x local API is at localhost:41112 (HTTP) or
# via the unix socket at /var/run/tailscale/tailscaled.sock on Linux.
# On macOS, the user-space tailscaled socket isn't always exposed;
# we fall back to the local-API HTTP endpoint.
_TAILSCALED_PROBES: tuple[tuple[str, str], ...] = (
    # (label, probe URL)
    ("tailscaled-unix", "http://local-tailscaled.sock/localapi/v0/status"),
    ("tailscaled-localapi", "http://localhost:41112/localapi/v0/status"),
)


_PROBE_TTL_S = 60.0
_tailscaled_reachable: bool | None = None
_tailscaled_last_probe_at: float = 0.0


def _tailscaled_available() -> bool:
    """Cheap probe (cached 60s) for the local tailscaled API.

    Returns True if ANY of the probe endpoints responds with 200.
    Returns False if all probes fail (connection refused / timeout).

    The cache prevents hammering the socket on every request.
    """
    global _tailscaled_reachable, _tailscaled_last_probe_at
    now = time.time()
    if _tailscaled_reachable is not None and (now - _tailscaled_last_probe_at) < _PROBE_TTL_S:
        return _tailscaled_reachable
    for _label, url in _TAILSCALED_PROBES:
        try:
            r = requests.get(url, timeout=1.0)
            if r.status_code == 200:
                _tailscaled_reachable = True
                _tailscaled_last_probe_at = now
                return True
        except (requests.RequestException, OSError):
            continue
    _tailscaled_reachable = False
    _tailscaled_last_probe_at = now
    return False


def reset_tailscale_cache() -> None:
    """Test hook: clear the probe cache + last-probe timestamp."""
    global _tailscaled_reachable, _tailscaled_last_probe_at
    _tailscaled_reachable = None
    _tailscaled_last_probe_at = 0.0


# ---------------------------------------------------------------------------
# Tailscale-Identity JWT decode
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TailscaleIdentity:
    """Resolved Tailscale peer identity (from the WhoIs local API).

    `tags` is a list like ['tag:admin', 'tag:gundam-halo'].
    `user_id` is the Tailscale account login (e.g. 'kencheng@gmail.com').
    `src_ip` is the peer's tailnet IP (e.g. '100.100.100.42').
    """

    user_id: str
    src_ip: str
    tags: tuple[str, ...] = field(default_factory=tuple)


def _decode_tailscale_jwt(jwt_token: str) -> dict[str, Any] | None:
    """Decode a Tailscale-Identity JWT (no signature verify — the
    JWT is signed by tailscaled and we trust the local API).

    Returns the decoded payload dict or None on malformed input.
    """
    try:
        # JWT format: header.payload.signature
        parts = jwt_token.split(".")
        if len(parts) != 3:
            return None
        # base64url decode the payload (2nd part).
        import base64

        payload_b64 = parts[1]
        # Add padding for base64 decoding.
        payload_b64 += "=" * (-len(payload_b64) % 4)
        # Translate URL-safe alphabet.
        payload_b64 = payload_b64.replace("-", "+").replace("_", "/")
        payload_bytes = base64.b64decode(payload_b64)
        return json.loads(payload_bytes)
    except (ValueError, json.JSONDecodeError, ImportError):
        return None


def _verify_tailscale_identity(
    identity_header: str | None,
    allowed_tags: tuple[str, ...],
) -> TailscaleIdentity | None:
    """Verify the Tailscale-Identity header + enforce tag allowlist.

    Returns the resolved identity on success, None on failure
    (missing header, malformed JWT, tags not in allowlist).

    If `allowed_tags` is empty, any authenticated Tailscale peer
    passes (no tag filter — useful for single-user tails).
    """
    if not identity_header:
        return None
    payload = _decode_tailscale_jwt(identity_header)
    if payload is None:
        return None

    peer_tags = tuple(payload.get("Tags", []) or [])
    if allowed_tags and not any(t in allowed_tags for t in peer_tags):
        return None

    # Extract user_id (Tailscale payload uses 'UserProfile' nested dict).
    user_profile = payload.get("UserProfile", {}) or {}
    user_id = user_profile.get("LoginName", "unknown")
    src_ip = str(payload.get("Address", "unknown"))

    return TailscaleIdentity(
        user_id=user_id,
        src_ip=src_ip,
        tags=peer_tags,
    )


# ---------------------------------------------------------------------------
# AuthContext — resolved identity for audit logging
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AuthContext:
    """Resolved identity for an authenticated request.

    Used by the audit logger and any endpoint that wants to know
    who's calling (e.g. for rate-limiting or audit trails).
    """

    caller_id: str
    src_ip: str
    auth_method: str  # "bearer+tailscale" | "bearer-only" | "dev"
    is_tailscale: bool


# ---------------------------------------------------------------------------
# Configurable behaviour: read tags from config
# ---------------------------------------------------------------------------


def _get_allowed_tags() -> tuple[str, ...]:
    """Read tailscale_allowed_tags from the active config.

    Returns an empty tuple (= no filter) if the config isn't loaded
    yet (early startup) or the value is missing. We try the
    app config first; fall back to the env var directly so this
    module is importable in tests that don't init the full app.
    """
    try:
        from app.core.config import get_config

        cfg = get_config()
        tags = getattr(getattr(cfg, "security", None), "auth", None)
        if tags is not None:
            return tuple(tags.tailscale_allowed_tags or ())
    except Exception:
        pass
    env_tags = os.environ.get("HALO_TAILSCALE_ALLOWED_TAGS", "")
    return tuple(t.strip() for t in env_tags.split(",") if t.strip())


# ---------------------------------------------------------------------------
# The dependency — `Depends(require_auth)`
# ---------------------------------------------------------------------------


async def require_auth(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> AuthContext:
    """FastAPI dependency: 401 unless bearer + Tailscale identity
    both pass (Sprint 48).

    Returns an `AuthContext` with the resolved identity. Endpoints
    using this dependency MUST also append to the audit log via
    `app.core.security.append_audit_log()` for full visibility
    (the dependency itself logs failures only).

    Stage 1 — bearer token (HARD requirement, fail-closed):
      - Read `os.environ["HALO_API_TOKEN"]`. If unset → 503.
      - Parse `Authorization: Bearer <token>` header. If missing
        or malformed → 401.
      - Compare with `hmac.compare_digest` (timing-safe). If
        mismatch → 401.

    Stage 2 — Tailscale identity (defence-in-depth, OPTIONAL enhance):
      - Probe `tailscaled` local API. If reachable:
        * Require `Tailscale-Identity` header. If missing → 401.
        * Decode + verify JWT + check tag allowlist. If invalid
          → 401.
      - If `tailscaled` unreachable (e.g. dev on localhost):
        * Skip the identity check + log WARNING.
        * AuthContext.is_tailscale = False, auth_method = "bearer-only".

    Test bypass: when `HALO_TEST_AUTH_BYPASS=true` is set in the
    environment, the dependency returns a synthetic "test-user"
    AuthContext WITHOUT validating anything. The bypass is ONLY
    consulted when the env var is set — production code never
    sets it. The root `tests/conftest.py` enables this for tests
    that exercise the protected endpoints without caring about
    auth (e.g. Sprint 40 + 44 endpoint tests). Tests that DO care
    (Sprint 48 `test_endpoint_auth.py`) unset the bypass.
    """
    # Sprint 48: explicit test bypass — never enabled in production.
    # The env var name is intentionally all-caps + TEST-prefixed so
    # production tooling never sets it accidentally.
    if os.environ.get("HALO_TEST_AUTH_BYPASS") == "true":
        return AuthContext(
            caller_id="test-bypass",
            src_ip="127.0.0.1",
            auth_method="test-bypass",
            is_tailscale=False,
        )

    # Stage 1: bearer token.
    expected = os.environ.get("HALO_API_TOKEN")
    if not expected:
        logger.error(
            "Sprint 48 auth: HALO_API_TOKEN not set; refusing protected "
            "request (fail-closed). Run scripts/generate-auth-token.sh."
        )
        raise HTTPException(
            status_code=503,
            detail=(
                "Backend is not configured for auth. Run "
                "`scripts/generate-auth-token.sh` to create "
                "$HALO_HOME/.env with HALO_API_TOKEN, then restart "
                "the backend."
            ),
        )

    if not authorization or not authorization.startswith("Bearer "):
        _log_failure(request, reason="missing-bearer")
        raise HTTPException(
            status_code=401,
            detail="Missing or malformed Authorization header (expected: Bearer <token>)",
        )
    presented = authorization[len("Bearer "):].strip()
    if not presented or not hmac.compare_digest(presented, expected):
        _log_failure(request, reason="bad-bearer")
        raise HTTPException(
            status_code=401, detail="Invalid bearer token"
        )

    # Stage 2: Tailscale identity (defence-in-depth).
    src_ip = request.client.host if request.client else "unknown"
    if _tailscaled_available():
        identity_header = request.headers.get("Tailscale-Identity") or request.headers.get(
            "Tailscale-Identity-256"
        )
        identity = _verify_tailscale_identity(
            identity_header, _get_allowed_tags()
        )
        if identity is None:
            _log_failure(request, reason="tailscale-identity-missing-or-invalid")
            raise HTTPException(
                status_code=401,
                detail=(
                    "Missing or invalid Tailscale identity. The protected "
                    "endpoints require both a bearer token AND a "
                    "Tailscale-WhoIs-verified identity. Are you calling "
                    "from a Tailscale-routed device?"
                ),
            )
        return AuthContext(
            caller_id=identity.user_id,
            src_ip=identity.src_ip,
            auth_method="bearer+tailscale",
            is_tailscale=True,
        )

    # tailscaled unavailable — bearer-only mode.
    logger.warning(
        "Sprint 48 auth: tailscaled socket unreachable; "
        "accepting bearer-only auth for %s %s (src_ip=%s). "
        "Set up Tailscale on this Mac for the identity check.",
        request.method,
        request.url.path,
        src_ip,
    )
    return AuthContext(
        caller_id="localhost-bearer",
        src_ip=src_ip,
        auth_method="bearer-only",
        is_tailscale=False,
    )


# ---------------------------------------------------------------------------
# Failure logger (audit log on auth failure)
# ---------------------------------------------------------------------------


def _log_failure(request: Request, reason: str) -> None:
    """Append a one-line auth-failure record to the audit log.

    Best-effort: never raises (audit log errors mustn't mask the
    auth failure itself). Caller should also raise HTTPException
    after this.
    """
    try:
        from app.core.security import append_audit_log

        append_audit_log({
            "ts": time.time(),
            "event": "auth_failure",
            "reason": reason,
            "method": request.method,
            "path": request.url.path,
            "src_ip": request.client.host if request.client else "unknown",
            "user_agent": request.headers.get("user-agent", ""),
        })
    except Exception as e:
        logger.warning("Sprint 48 auth: failed to append audit log: %s", e)


__all__ = [
    "AuthContext",
    "TailscaleIdentity",
    "require_auth",
    "_tailscaled_available",
    "reset_tailscale_cache",
    "_verify_tailscale_identity",
    "_decode_tailscale_jwt",
    "_get_allowed_tags",
]
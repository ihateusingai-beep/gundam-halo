"""Sprint 48 — auth layer tests.

Coverage (7 tests):
1. require_auth 503s when HALO_API_TOKEN not set (fail-closed).
2. require_auth 401s on missing Authorization header.
3. require_auth 401s on wrong bearer token.
4. require_auth passes on valid bearer (no Tailscale — bearer-only).
5. _verify_tailscale_identity returns None for missing header.
6. _verify_tailscale_identity returns None for malformed JWT.
7. _verify_tailscale_identity enforces tag allowlist.

The Tailscale-socket probe is mocked — we don't actually need
`tailscaled` running for unit tests of the identity-check logic.
"""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from fastapi import HTTPException

# Set the env var BEFORE importing auth (require_auth reads it on
# each call, but several tests want to assert behaviour when it's
# absent — so we manage env via monkeypatch in each test).
TOKEN = "test-bearer-token-32-bytes-of-fun"


@pytest.fixture(autouse=True)
def _reset_env(monkeypatch):
    """Ensure each test starts with a clean auth env.

    Also unsets `HALO_TEST_AUTH_BYPASS` so the auth dependency
    runs the real logic — these tests are specifically verifying
    the dependency's behaviour (bypassing would defeat the point).
    """
    monkeypatch.delenv("HALO_TEST_AUTH_BYPASS", raising=False)
    monkeypatch.delenv("HALO_API_TOKEN", raising=False)
    monkeypatch.delenv("HALO_TAILSCALE_ALLOWED_TAGS", raising=False)


def _run_require_auth(authorization: str | None):
    """Helper: invoke require_auth with a fake Request + optional header."""
    import asyncio
    from app.core.auth import require_auth

    # Build a minimal fake Request.
    class _FakeClient:
        host = "127.0.0.1"

    class _FakeRequest:
        headers: dict = {}
        client = _FakeClient()
        method = "POST"
        url_path = "/api/system/clear-crash-log"

        @property
        def url(self):
            class _URL:
                path = "/api/system/clear-crash-log"

            return _URL()

    request = _FakeRequest()
    headers = {"authorization": authorization} if authorization is not None else {}
    return asyncio.run(require_auth(request, authorization=headers.get("authorization")))


def test_require_auth_503s_when_token_not_configured():
    """Fail-closed: no HALO_API_TOKEN env var → 503."""
    with pytest.raises(HTTPException) as exc_info:
        _run_require_auth(authorization=f"Bearer {TOKEN}")
    assert exc_info.value.status_code == 503
    assert "not configured" in str(exc_info.value.detail).lower()


def test_require_auth_401s_with_missing_header(monkeypatch):
    """No Authorization header → 401."""
    monkeypatch.setenv("HALO_API_TOKEN", TOKEN)
    with pytest.raises(HTTPException) as exc_info:
        _run_require_auth(authorization=None)
    assert exc_info.value.status_code == 401


def test_require_auth_401s_with_wrong_token(monkeypatch):
    """Wrong bearer token → 401 (timing-safe compare)."""
    monkeypatch.setenv("HALO_API_TOKEN", TOKEN)
    with patch("app.core.auth._tailscaled_available", return_value=False):
        with pytest.raises(HTTPException) as exc_info:
            _run_require_auth(authorization="Bearer wrong-token-here")
        assert exc_info.value.status_code == 401


def test_require_auth_passes_with_valid_bearer(monkeypatch):
    """Correct bearer + tailscaled unavailable → bearer-only mode."""
    monkeypatch.setenv("HALO_API_TOKEN", TOKEN)
    with patch("app.core.auth._tailscaled_available", return_value=False):
        ctx = _run_require_auth(authorization=f"Bearer {TOKEN}")
    assert ctx.caller_id == "localhost-bearer"
    assert ctx.is_tailscale is False
    assert ctx.auth_method == "bearer-only"


def test_verify_tailscale_identity_returns_none_for_missing_header():
    """No Tailscale-Identity header → None."""
    from app.core.auth import _verify_tailscale_identity

    assert _verify_tailscale_identity(None, ()) is None
    assert _verify_tailscale_identity("", ()) is None


def test_verify_tailscale_identity_returns_none_for_malformed_jwt():
    """Garbage JWT (not 3 parts, or un-parseable base64) → None."""
    from app.core.auth import _verify_tailscale_identity

    assert _verify_tailscale_identity("not-a-jwt", ()) is None
    assert _verify_tailscale_identity("a.b.c", ()) is None


def test_verify_tailscale_identity_enforces_tag_allowlist():
    """Tags not in allowlist → None (even with valid JWT)."""
    from app.core.auth import _verify_tailscale_identity

    # Build a minimal valid JWT: header.payload.sig.
    # Payload: {"Tags": ["tag:other"], "UserProfile": {"LoginName":
    # "alice"}, "Address": "100.100.100.42"}.
    import base64
    import json

    def b64url(d: bytes) -> str:
        return base64.urlsafe_b64encode(d).rstrip(b"=").decode()

    header = b64url(json.dumps({"alg": "none"}).encode())
    payload = b64url(json.dumps({
        "Tags": ["tag:other"],
        "UserProfile": {"LoginName": "alice"},
        "Address": "100.100.100.42",
    }).encode())
    sig = "fake-sig"
    jwt_token = f"{header}.{payload}.{sig}"

    # Empty allowlist → any tags pass.
    identity = _verify_tailscale_identity(jwt_token, ())
    assert identity is not None
    assert identity.user_id == "alice"
    assert identity.tags == ("tag:other",)

    # Allowlist with non-matching tag → None.
    identity = _verify_tailscale_identity(jwt_token, ("tag:admin",))
    assert identity is None

    # Allowlist with matching tag → identity returned.
    identity = _verify_tailscale_identity(jwt_token, ("tag:other", "tag:admin"))
    assert identity is not None
    assert "tag:other" in identity.tags
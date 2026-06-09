"""Tests for the SecretStore and /api/secrets endpoints.

Covers:
- Atomic write of .env file with 0600 permissions
- Refusal of unknown / unsafe env var names
- Set / get / clear cycle (in-memory + os.environ + on-disk)
- is_configured() truthiness
- status_payload() shape (no values, only booleans)
- Re-load from existing .env (simulate process restart)
- API endpoint: GET returns no values, POST returns no values
- API endpoint: POST with unknown key is rejected (400)
- API endpoint: POST triggers config-cache invalidation
- API endpoint: DELETE clears
- Audit log is emitted without the value
"""

from __future__ import annotations

import os
import stat
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core import config as config_mod
from app.core.secrets_store import SECRET_KEYS, SecretStore, reset_secret_store
from app.main import create_app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_halo_home(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def fresh_store(tmp_halo_home: Path):
    reset_secret_store()
    config_mod._config = None
    s = SecretStore(halo_home=tmp_halo_home)
    yield s
    reset_secret_store()
    config_mod._config = None


@pytest.fixture(autouse=True)
def _isolate_secrets():
    """Ensure every test starts with no MANAGED secrets in os.environ.

    Other env vars are not touched. Without this, tests can leak
    state into each other when run in sequence.
    """
    leaked = []
    for k in SECRET_KEYS:
        if k in os.environ:
            leaked.append(k)
            del os.environ[k]
    yield
    # Cleanup after test
    for k in SECRET_KEYS:
        os.environ.pop(k, None)


@pytest.fixture
def client(tmp_halo_home: Path):
    """A TestClient whose HALO_HOME is a temp dir."""
    reset_secret_store()
    config_mod._config = None
    os.environ["HALO_HOME"] = str(tmp_halo_home)
    # Wipe the env vars we're testing so the tests start clean
    for k in SECRET_KEYS:
        os.environ.pop(k, None)
    app = create_app()
    with TestClient(app) as c:
        yield c
    # Cleanup
    for k in SECRET_KEYS:
        os.environ.pop(k, None)
    reset_secret_store()
    config_mod._config = None


# ---------------------------------------------------------------------------
# SecretStore unit tests
# ---------------------------------------------------------------------------


class TestSecretStore:
    def test_empty_store_returns_empty(self, fresh_store):
        assert fresh_store.get("MINIMAX_API_KEY") == ""
        assert fresh_store.is_configured("MINIMAX_API_KEY") is False

    def test_set_persists_to_disk_with_0600(self, fresh_store, tmp_halo_home):
        fresh_store.set("MINIMAX_API_KEY", "sk-test-12345")
        env_path = tmp_halo_home / ".env"
        assert env_path.exists()
        mode = stat.S_IMODE(os.stat(env_path).st_mode)
        assert mode == 0o600, f"expected 0600, got {oct(mode)}"

    def test_set_writes_value_to_file(self, fresh_store, tmp_halo_home):
        fresh_store.set("MINIMAX_API_KEY", "sk-test-12345")
        content = (tmp_halo_home / ".env").read_text()
        assert "MINIMAX_API_KEY=sk-test-12345" in content

    def test_clear_removes_from_all_sources(self, fresh_store, tmp_halo_home):
        fresh_store.set("MINIMAX_API_KEY", "sk-test")
        assert fresh_store.is_configured("MINIMAX_API_KEY")
        fresh_store.clear("MINIMAX_API_KEY")
        assert not fresh_store.is_configured("MINIMAX_API_KEY")
        assert "MINIMAX_API_KEY" not in os.environ
        # .env should still exist but the value line removed (no `KEY=`)
        content = (tmp_halo_home / ".env").read_text()
        # We don't have an active "MINIMAX_API_KEY=..." line, just a
        # commented placeholder.
        for line in content.splitlines():
            assert not line.startswith("MINIMAX_API_KEY="), (
                f"unexpected active value line: {line!r}"
            )
        with pytest.raises(ValueError, match="unknown secret key"):
            fresh_store.set("BOGUS_API_KEY", "value")

    def test_set_refuses_unsafe_name(self, fresh_store):
        # Trailing space / special char
        with pytest.raises(ValueError):
            fresh_store.set("BAD-KEY", "value")

    def test_set_refuses_empty_value(self, fresh_store):
        with pytest.raises(ValueError, match="empty"):
            fresh_store.set("MINIMAX_API_KEY", "  ")

    def test_set_mirrors_to_environ(self, fresh_store):
        fresh_store.set("MINIMAX_API_KEY", "sk-test-12345")
        assert os.environ.get("MINIMAX_API_KEY") == "sk-test-12345"

    def test_set_marks_cache_dirty(self, fresh_store):
        assert fresh_store.is_config_cache_dirty() is False
        fresh_store.set("MINIMAX_API_KEY", "sk-test")
        assert fresh_store.is_config_cache_dirty() is True

    def test_invalidate_config_cache_resets_flag(self, fresh_store):
        fresh_store.set("MINIMAX_API_KEY", "sk-test")
        fresh_store.invalidate_config_cache()
        assert fresh_store.is_config_cache_dirty() is False
        # And the config module's cache is gone
        assert config_mod._config is None

    def test_clear_removes_from_all_sources(self, fresh_store, tmp_halo_home):
        fresh_store.set("MINIMAX_API_KEY", "sk-test")
        assert fresh_store.is_configured("MINIMAX_API_KEY")
        fresh_store.clear("MINIMAX_API_KEY")
        assert not fresh_store.is_configured("MINIMAX_API_KEY")
        assert "MINIMAX_API_KEY" not in os.environ
        # .env should still exist but the value line removed
        content = (tmp_halo_home / ".env").read_text()
        assert "MINIMAX_API_KEY=" not in content or "MINIMAX_API_KEY=#" in content

    def test_get_prefers_override_over_environ(self, fresh_store):
        os.environ["MINIMAX_API_KEY"] = "from-env"
        fresh_store.set("MINIMAX_API_KEY", "from-override")
        assert fresh_store.get("MINIMAX_API_KEY") == "from-override"

    def test_reload_picks_up_existing_env_file(self, tmp_halo_home):
        # Pre-seed an .env file
        (tmp_halo_home / ".env").write_text(
            "MINIMAX_API_KEY=from-disk\n"
            "GUNDAM_HALO_TG_TOKEN=1234:abcd\n"
        )
        # Wipe os.environ to prove the reload actually re-hydrates
        os.environ.pop("MINIMAX_API_KEY", None)
        os.environ.pop("GUNDAM_HALO_TG_TOKEN", None)
        # New store instance simulates process restart
        s = SecretStore(halo_home=tmp_halo_home)
        assert s.get("MINIMAX_API_KEY") == "from-disk"
        assert s.get("GUNDAM_HALO_TG_TOKEN") == "1234:abcd"

    def test_status_payload_no_values(self, fresh_store):
        fresh_store.set("MINIMAX_API_KEY", "sk-very-secret")
        payload = fresh_store.status_payload()
        # The payload must NEVER contain the value
        import json

        as_text = json.dumps(payload)
        assert "sk-very-secret" not in as_text
        # The shape is correct
        assert payload["MINIMAX_API_KEY"]["configured"] is True
        assert payload["MINIMAX_API_KEY"]["source"] == "override"
        assert payload["MINIMAX_API_KEY"]["label"] == "MiniMax API Key"

    def test_status_payload_unconfigured(self, fresh_store):
        payload = fresh_store.status_payload()
        assert payload["MINIMAX_API_KEY"]["configured"] is False
        assert payload["MINIMAX_API_KEY"]["source"] == "none"

    def test_status_payload_env_source(self, fresh_store):
        # No override; os.environ has the value
        os.environ["MINIMAX_API_KEY"] = "env-only"
        payload = fresh_store.status_payload()
        assert payload["MINIMAX_API_KEY"]["configured"] is True
        assert payload["MINIMAX_API_KEY"]["source"] == "env"

    def test_atomic_write_no_partial_file(self, fresh_store, tmp_halo_home):
        # Set + clear rapidly — no .env.tmp should remain
        fresh_store.set("MINIMAX_API_KEY", "sk-a")
        fresh_store.clear("MINIMAX_API_KEY")
        # .env should exist but no leftover tmp file
        env_path = tmp_halo_home / ".env"
        assert env_path.exists()
        leftovers = list(tmp_halo_home.glob(".env.*"))
        # mkstemp creates the tmp file but os.replace should remove it
        assert not leftovers, f"leftover tmp files: {leftovers}"


# ---------------------------------------------------------------------------
# /api/secrets endpoint tests
# ---------------------------------------------------------------------------


class TestSecretsEndpoint:
    def test_get_returns_no_values(self, client, tmp_halo_home):
        r = client.get("/api/secrets")
        assert r.status_code == 200
        body = r.json()
        for name in SECRET_KEYS:
            assert name in body
            assert "value" not in body[name]  # never
            assert body[name]["configured"] is False

    def test_post_sets_value(self, client, tmp_halo_home):
        r = client.post(
            "/api/secrets",
            json={"secrets": [{"name": "MINIMAX_API_KEY", "value": "sk-test-abc"}]},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["MINIMAX_API_KEY"]["configured"] is True
        # The value is NOT echoed back
        import json

        assert "sk-test-abc" not in json.dumps(body)
        # But it IS in the .env file
        env_text = (tmp_halo_home / ".env").read_text()
        assert "MINIMAX_API_KEY=sk-test-abc" in env_text
        # And in os.environ
        assert os.environ.get("MINIMAX_API_KEY") == "sk-test-abc"

    def test_post_rejects_unknown_key(self, client):
        r = client.post(
            "/api/secrets",
            json={"secrets": [{"name": "TOTALLY_BOGUS", "value": "x"}]},
        )
        assert r.status_code == 400
        assert "unknown" in r.json()["detail"].lower()

    def test_post_rejects_empty_value(self, client):
        r = client.post(
            "/api/secrets",
            json={"secrets": [{"name": "MINIMAX_API_KEY", "value": ""}]},
        )
        assert r.status_code == 422  # pydantic validation
        # pydantic catches it before our code

    def test_post_rejects_oversized_value(self, client):
        r = client.post(
            "/api/secrets",
            json={
                "secrets": [
                    {"name": "MINIMAX_API_KEY", "value": "x" * 5000}
                ]
            },
        )
        assert r.status_code == 422

    def test_post_multiple_at_once(self, client):
        r = client.post(
            "/api/secrets",
            json={
                "secrets": [
                    {"name": "MINIMAX_API_KEY", "value": "sk-1"},
                    {"name": "GUNDAM_HALO_TG_TOKEN", "value": "tg-1"},
                ]
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["MINIMAX_API_KEY"]["configured"] is True
        assert body["GUNDAM_HALO_TG_TOKEN"]["configured"] is True

    def test_post_invalidates_config_cache(self, client):
        # Warm the config cache
        from app.core.config import get_config

        cfg1 = get_config()
        cfg1_id = id(cfg1)
        # Post a secret
        client.post(
            "/api/secrets",
            json={"secrets": [{"name": "MINIMAX_API_KEY", "value": "sk-x"}]},
        )
        # Cache should be invalidated; next get_config returns a fresh
        # instance with the new value
        from app.core import config as config_mod

        assert config_mod._config is None
        cfg2 = get_config()
        # The new config should see the env var
        assert cfg2.llm.api_key == "sk-x"

    def test_delete_clears_specific(self, client, tmp_halo_home):
        # Set then delete
        client.post(
            "/api/secrets",
            json={"secrets": [{"name": "MINIMAX_API_KEY", "value": "sk-1"}]},
        )
        r = client.delete("/api/secrets/MINIMAX_API_KEY")
        assert r.status_code == 200
        body = r.json()
        assert body["MINIMAX_API_KEY"]["configured"] is False
        assert "MINIMAX_API_KEY" not in os.environ

    def test_delete_unknown_key_400(self, client):
        r = client.delete("/api/secrets/TOTALLY_BOGUS")
        assert r.status_code == 400

    def test_clear_batch(self, client):
        client.post(
            "/api/secrets",
            json={
                "secrets": [
                    {"name": "MINIMAX_API_KEY", "value": "sk-1"},
                    {"name": "GUNDAM_HALO_TG_TOKEN", "value": "tg-1"},
                ]
            },
        )
        r = client.post(
            "/api/secrets/clear",
            json={"names": ["MINIMAX_API_KEY", "GUNDAM_HALO_TG_TOKEN"]},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["MINIMAX_API_KEY"]["configured"] is False
        assert body["GUNDAM_HALO_TG_TOKEN"]["configured"] is False

    def test_response_never_includes_value(self, client, caplog):
        secret_value = "sk-supersecret-12345-very-private"
        with caplog.at_level("INFO"):
            r = client.post(
                "/api/secrets",
                json={"secrets": [{"name": "MINIMAX_API_KEY", "value": secret_value}]},
            )
        assert r.status_code == 200
        # Response body doesn't contain the value
        assert secret_value not in r.text
        # Audit log doesn't contain the value (only the key name)
        for record in caplog.records:
            assert secret_value not in record.message, (
                f"secret value leaked into log: {record.message!r}"
            )

"""SecretStore — runtime secret management for the dashboard.

Secrets (API keys, bot tokens) are normally read from environment
variables at backend startup. The dashboard needs to set them
at runtime without restarting the process. This module:

1. Defines the canonical "secret keys" (the env var names we care about)
2. Maintains an in-memory override map populated by POST /api/secrets
3. Atomically writes values to `~/.gundam-halo/.env` so they survive restart
4. Sets `os.environ[name] = value` so the running process picks them up
5. Invalidates the config cache so next `get_config()` reloads

The .env file is created with 0600 permissions and uses atomic write
(tmp + rename) to avoid corruption on crash.

Note: secrets are NEVER returned in API responses — only their
"configured" boolean. The dashboard's GET endpoint masks values
as "••••••" if set, or "" if not.
"""

from __future__ import annotations

import logging
import os
import re
import tempfile
import threading
from pathlib import Path
from typing import Dict, Iterable, Optional

logger = logging.getLogger(__name__)

# The canonical list of secret keys we manage. Each maps to:
#   - the env var name (what `os.environ` should hold)
#   - a human-readable label for the dashboard
SECRET_KEYS: Dict[str, str] = {
    "MINIMAX_API_KEY": "MiniMax API Key",
    "GUNDAM_HALO_TG_TOKEN": "Telegram Bot Token",
}

# A safe pattern for env var names — only A-Z, 0-9, underscore, leading alpha.
_SAFE_NAME = re.compile(r"^[A-Z][A-Z0-9_]*$")


class SecretStore:
    """Process-wide secret manager. Singleton via get_secret_store()."""

    def __init__(self, halo_home: Path) -> None:
        self._halo_home = halo_home
        self._env_path = halo_home / ".env"
        self._lock = threading.RLock()
        # In-memory override: env_var_name -> value. Set by the dashboard;
        # consulted before os.environ when checking what's configured.
        self._overrides: Dict[str, str] = {}
        self._loaded = False
        # Pending config-cache invalidations. The API layer calls
        # `invalidate_config_cache()` after a POST, and the next
        # `get_config()` reloads from disk + env.
        self._config_cache_dirty = False

    # ------------------------------------------------------------------
    # Read API
    # ------------------------------------------------------------------

    def get(self, name: str) -> str:
        """Return the current value of *name* (override or env)."""
        if not _SAFE_NAME.match(name):
            return ""
        with self._lock:
            self._ensure_loaded()
            if name in self._overrides:
                return self._overrides[name]
        return os.environ.get(name, "")

    def is_configured(self, name: str) -> bool:
        return bool(self.get(name))

    def configured_keys(self) -> Iterable[str]:
        """Return names that currently have a value set (from anywhere)."""
        for name in SECRET_KEYS:
            if self.is_configured(name):
                yield name

    def status_payload(self) -> Dict[str, Dict[str, object]]:
        """Return a JSON-safe status map for the dashboard.

        Schema:
          {
            "MINIMAX_API_KEY": {
              "label": "MiniMax API Key",
              "configured": true,
              "source": "override" | "env" | "none"
            },
            ...
          }

        Values are NEVER included — only booleans.
        """
        out: Dict[str, Dict[str, object]] = {}
        for name, label in SECRET_KEYS.items():
            with self._lock:
                self._ensure_loaded()
                if name in self._overrides and self._overrides[name]:
                    source = "override"
                    configured = True
                else:
                    configured = bool(os.environ.get(name, ""))
                    source = "env" if configured else "none"
            out[name] = {
                "label": label,
                "configured": configured,
                "source": source,
            }
        return out

    # ------------------------------------------------------------------
    # Write API
    # ------------------------------------------------------------------

    def set(self, name: str, value: str) -> None:
        """Set *name* to *value* in-memory and on disk. Marks config dirty."""
        if name not in SECRET_KEYS:
            raise ValueError(
                f"refusing to set unknown secret key: {name!r}. "
                f"Allowed: {list(SECRET_KEYS)}"
            )
        if not _SAFE_NAME.match(name):
            raise ValueError(f"unsafe env var name: {name!r}")
        value = value.strip()
        if not value:
            raise ValueError(f"refusing to set empty value for {name!r}")
        with self._lock:
            self._ensure_loaded()
            self._overrides[name] = value
            # Mirror into os.environ so the running process sees it
            os.environ[name] = value
            self._config_cache_dirty = True
            self._save()

    def clear(self, name: str) -> None:
        """Remove *name* from overrides + os.environ + .env file."""
        if name not in SECRET_KEYS:
            raise ValueError(f"unknown secret key: {name!r}")
        with self._lock:
            self._ensure_loaded()
            self._overrides.pop(name, None)
            os.environ.pop(name, None)
            self._config_cache_dirty = True
            self._save()

    def clear_all(self) -> None:
        """Wipe every managed secret (overrides + env + file)."""
        with self._lock:
            for name in list(SECRET_KEYS):
                self._overrides.pop(name, None)
                os.environ.pop(name, None)
            self._save()
            self._config_cache_dirty = True

    def is_config_cache_dirty(self) -> bool:
        with self._lock:
            return self._config_cache_dirty

    def invalidate_config_cache(self) -> None:
        """Mark the config cache for invalidation. The next get_config()
        call will reload from disk + env."""
        from app.core import config as config_mod

        with self._lock:
            self._config_cache_dirty = False  # we just acted on it
            config_mod._config = None

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        # Pre-populate overrides from any existing .env file (without
        # overwriting anything already in os.environ). This lets a
        # server restart re-hydrate from the file the dashboard wrote.
        if self._env_path.exists():
            try:
                text = self._env_path.read_text(encoding="utf-8")
                for line in text.splitlines():
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    name, _, value = line.partition("=")
                    name = name.strip()
                    value = value.strip()
                    if name in SECRET_KEYS and value:
                        self._overrides[name] = value
            except Exception as e:
                logger.warning(f"Failed to load .env overrides: {e}")
        self._loaded = True

    def _save(self) -> None:
        """Atomically persist the override map to .env (0600)."""
        try:
            self._halo_home.mkdir(parents=True, exist_ok=True)
            with self._lock:
                body = self._render_env(self._overrides)
            # Atomic write: tmp + rename, 0600 permissions
            fd, tmp_path = tempfile.mkstemp(
                prefix=".env.", dir=self._halo_home, text=True
            )
            try:
                os.write(fd, body.encode("utf-8"))
                os.fchmod(fd, 0o600)
            finally:
                os.close(fd)
            os.replace(tmp_path, self._env_path)
            # Belt + braces: also chmod the final file
            try:
                os.chmod(self._env_path, 0o600)
            except OSError:
                pass
            logger.debug(f"Persisted {len(self._overrides)} secret(s) to {self._env_path}")
        except Exception as e:
            logger.warning(f"Failed to persist secrets to .env: {e}")

    @staticmethod
    def _render_env(overrides: Dict[str, str]) -> str:
        """Render the .env file body.

        Only emits a value line for secrets that have an override.
        Unset secrets get a commented-out placeholder so the file
        structure is stable (no spurious "NAME=" empty assignments that
        would shadow real env vars in shells that source the file).
        """
        lines = [
            "# Gundam Halo — runtime secrets",
            "# Written by the dashboard; do not edit by hand unless you know",
            "# what you're doing. Values are managed via the Settings tab.",
            "",
        ]
        for name, label in SECRET_KEYS.items():
            lines.append(f"# {label}")
            if name in overrides and overrides[name]:
                lines.append(f"{name}={overrides[name]}")
            else:
                # Commented placeholder — no leading `=` (which some
                # shells parse as setting the var to empty).
                lines.append(f"# {name} (unset)")
            lines.append("")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_store: Optional[SecretStore] = None
_store_lock = threading.Lock()


def get_secret_store() -> SecretStore:
    """Return the process-wide secret store.

    Lazy-initialised from `cfg.home` on first call.
    """
    global _store
    with _store_lock:
        if _store is None:
            from app.core.config import get_config

            _store = SecretStore(halo_home=get_config().home)
        return _store


def reset_secret_store() -> None:
    """Replace the singleton with None (for tests)."""
    global _store
    with _store_lock:
        _store = None


__all__ = [
    "SecretStore",
    "SECRET_KEYS",
    "get_secret_store",
    "reset_secret_store",
]

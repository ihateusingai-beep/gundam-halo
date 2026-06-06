"""Settings endpoint — exposes sanitized config for the dashboard.

Secrets (api_key, bot_token) are never returned in plaintext — only
whether they are configured.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Query

from app.core.config import get_config
from app.security.audit import get_audit_logger

logger = logging.getLogger(__name__)
router = APIRouter()


def _sanitize_config() -> Dict[str, Any]:
    """Return config with secrets masked."""
    cfg = get_config()

    return {
        "app": {
            "version": "0.1.0",
            "home": str(cfg.home),
            "config_path": str(cfg.home / "config.toml"),
        },
        "user": {
            "name": cfg.user.name,
            "default_theme": cfg.user.default_theme,
        },
        "llm": {
            "provider": "MiniMax",
            "base_url": cfg.llm.base_url,
            "default_model": cfg.llm.default_model,
            "fallback_model": cfg.llm.fallback_model,
            "api_key_configured": bool(cfg.llm.api_key),
        },
        "server": {
            "host": cfg.server.host,
            "port": cfg.server.port,
            "log_level": cfg.server.log_level,
            "require_tailscale": cfg.server.require_tailscale,
            "tailscale_hostname": cfg.server.tailscale_hostname,
        },
        "mac": {
            "default_path_policy": cfg.mac.default_path_policy,
            "file_read_paths": cfg.mac.file_read_paths,
            "file_write_paths": cfg.mac.file_write_paths,
            "shell_allowlist": cfg.mac.shell_allowlist,
            "a11y_enabled": cfg.mac.a11y_enabled,
            "apple_script_enabled": cfg.mac.apple_script_enabled,
            "notifications_enabled": cfg.mac.notifications_enabled,
        },
        "telegram": {
            "enabled": cfg.telegram.enabled,
            "allowed_chat_ids": cfg.telegram.allowed_chat_ids,
            "command_prefix": cfg.telegram.command_prefix,
            "bot_token_configured": bool(cfg.telegram.bot_token),
        },
        "security": {
            "audit_log": cfg.security.audit_log,
            "audit_max_size_mb": cfg.security.audit_max_size_mb,
            "injection_scan": cfg.security.injection_scan,
            "require_confirm_for": cfg.security.require_confirm_for,
        },
    }


@router.get("/settings")
async def get_settings() -> Dict[str, Any]:
    """Return sanitized app config (secrets masked)."""
    return _sanitize_config()


@router.get("/settings/audit")
async def get_audit(
    limit: int = Query(100, ge=1, le=1000, description="Max entries to return"),
) -> List[Dict[str, Any]]:
    """Return recent audit log entries (most recent first)."""
    audit = get_audit_logger()
    return audit.tail(limit)

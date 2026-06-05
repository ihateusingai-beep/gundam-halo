"""Configuration loader.

Reads from:
1. `~/.gundam-halo/config.toml` (user config)
2. Environment variables (override anything)
3. Defaults (lowest priority)

Designed to be loaded once at startup and reloaded only when config changes.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]


# ---------------------------------------------------------------------------
# Default paths
# ---------------------------------------------------------------------------

DEFAULT_HOME = Path.home() / ".gundam-halo"


def expand_home(path: str | Path) -> Path:
    """Expand ~ and resolve to absolute Path."""
    return Path(os.path.expanduser(str(path))).resolve()


# ---------------------------------------------------------------------------
# Config dataclasses
# ---------------------------------------------------------------------------


@dataclass
class LLMConfig:
    provider: str = "minimax"
    api_key: str = ""
    base_url: str = "https://api.MiniMax.chat/v1"
    default_model: str = "MiniMax-M3"
    fallback_model: str = "MiniMax-M2"


@dataclass
class ServerConfig:
    host: str = "0.0.0.0"
    port: int = 8765
    log_level: str = "INFO"
    require_tailscale: bool = True
    tailscale_hostname: str = "gundam-halo"


@dataclass
class MacControlConfig:
    default_path_policy: str = "project_only"  # project_only | user_home | allowlist
    shell_allowlist: List[str] = field(
        default_factory=lambda: [
            "git", "ls", "cat", "head", "tail",
            "grep", "rg", "find", "fd",
            "pwd", "cd", "echo", "date",
            "open",
        ]
    )
    file_read_paths: List[str] = field(
        default_factory=lambda: ["~/Documents", "~/Downloads", "~/workspace", "/tmp"]
    )
    file_write_paths: List[str] = field(
        default_factory=lambda: ["~/workspace", "~/.gundam-halo/projects"]
    )
    a11y_enabled: bool = False
    apple_script_enabled: bool = True
    notifications_enabled: bool = True


@dataclass
class TelegramConfig:
    enabled: bool = False
    bot_token: str = ""
    allowed_chat_ids: List[int] = field(default_factory=list)
    command_prefix: str = "/"


@dataclass
class SecurityConfig:
    audit_log: str = "~/.gundam-halo/logs/audit.log"
    audit_max_size_mb: int = 100
    injection_scan: bool = True
    require_confirm_for: List[str] = field(
        default_factory=lambda: [
            "mac.file.write",
            "mac.shell",
            "mac.apple_script",
            "mac.a11y",
        ]
    )


@dataclass
class UserConfig:
    name: str = "User"
    default_theme: str = "gundam-ntd"


@dataclass
class Config:
    """Root config object."""

    home: Path = field(default_factory=lambda: expand_home(DEFAULT_HOME))
    user: UserConfig = field(default_factory=UserConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    mac: MacControlConfig = field(default_factory=MacControlConfig)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)

    @property
    def log_level(self) -> str:
        return self.server.log_level


# ---------------------------------------------------------------------------
# Loading logic
# ---------------------------------------------------------------------------


def _load_toml(path: Path) -> dict:
    """Load a TOML file. Returns empty dict if not found."""
    if not path.exists():
        return {}
    with open(path, "rb") as f:
        return tomllib.load(f)


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    v = _env(name, "").lower()
    if v in ("1", "true", "yes", "y", "on"):
        return True
    if v in ("0", "false", "no", "n", "off"):
        return False
    return default


def _load_user_config(toml_data: dict) -> UserConfig:
    d = toml_data.get("user", {})
    return UserConfig(
        name=d.get("name", UserConfig.name),
        default_theme=d.get("default_theme", UserConfig.default_theme),
    )


def _load_llm_config(toml_data: dict) -> LLMConfig:
    d = toml_data.get("llm", {})
    api_key_env = d.get("api_key_env", "MINIMAX_API_KEY")
    return LLMConfig(
        provider=d.get("provider", LLMConfig.provider),
        api_key=_env(api_key_env, ""),  # NEVER store in TOML, always env
        base_url=_env("MINIMAX_BASE_URL", d.get("base_url", LLMConfig.base_url)),
        default_model=_env("MINIMAX_MODEL", d.get("default_model", LLMConfig.default_model)),
        fallback_model=d.get("fallback_model", LLMConfig.fallback_model),
    )


def _load_server_config(toml_data: dict) -> ServerConfig:
    d = toml_data.get("server", {})
    return ServerConfig(
        host=_env("HALO_HOST", d.get("host", ServerConfig.host)),
        port=_env_int("HALO_PORT", d.get("port", ServerConfig.port)),
        log_level=_env("HALO_LOG_LEVEL", d.get("log_level", ServerConfig.log_level)),
        require_tailscale=_env_bool(
            "HALO_REQUIRE_TAILSCALE", d.get("require_tailscale", ServerConfig.require_tailscale)
        ),
        tailscale_hostname=_env(
            "HALO_TAILSCALE_HOSTNAME", d.get("tailscale_hostname", ServerConfig.tailscale_hostname)
        ),
    )


def _load_mac_config(toml_data: dict) -> MacControlConfig:
    d = toml_data.get("mac_control", {})
    return MacControlConfig(
        default_path_policy=d.get("default_path_policy", MacControlConfig.default_path_policy),
        shell_allowlist=d.get("shell_allowlist", MacControlConfig.shell_allowlist),
        file_read_paths=d.get("file_read_paths", MacControlConfig.file_read_paths),
        file_write_paths=d.get("file_write_paths", MacControlConfig.file_write_paths),
        a11y_enabled=d.get("a11y_enabled", MacControlConfig.a11y_enabled),
        apple_script_enabled=d.get("apple_script_enabled", MacControlConfig.apple_script_enabled),
        notifications_enabled=d.get(
            "notifications_enabled", MacControlConfig.notifications_enabled
        ),
    )


def _load_telegram_config(toml_data: dict) -> TelegramConfig:
    d = toml_data.get("channels", {}).get("telegram", {})
    chat_ids_env = _env("GUNDAM_HALO_TG_ALLOWED_CHAT_IDS", "")
    chat_ids = [int(x) for x in chat_ids_env.split(",") if x.strip().isdigit()]
    return TelegramConfig(
        enabled=d.get("enabled", False),
        bot_token=_env("GUNDAM_HALO_TG_TOKEN", ""),
        allowed_chat_ids=chat_ids or d.get("allowed_chat_ids", []),
        command_prefix=d.get("command_prefix", "/"),
    )


def _load_security_config(toml_data: dict) -> SecurityConfig:
    d = toml_data.get("security", {})
    return SecurityConfig(
        audit_log=d.get("audit_log", SecurityConfig.audit_log),
        audit_max_size_mb=d.get("audit_max_size_mb", SecurityConfig.audit_max_size_mb),
        injection_scan=d.get("injection_scan", SecurityConfig.injection_scan),
        require_confirm_for=d.get(
            "require_confirm_for", SecurityConfig.require_confirm_for
        ),
    )


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_config: Optional[Config] = None


def get_config(home: Optional[Path] = None) -> Config:
    """Get the global config (load from disk on first call)."""
    global _config
    if _config is None:
        _config = load_config(home)
    return _config


def load_config(home: Optional[Path] = None) -> Config:
    """Load config from TOML + env vars."""
    home = expand_home(home or _env("HALO_HOME", str(DEFAULT_HOME)))
    config_path = home / "config.toml"
    toml_data = _load_toml(config_path)

    return Config(
        home=home,
        user=_load_user_config(toml_data),
        llm=_load_llm_config(toml_data),
        server=_load_server_config(toml_data),
        mac=_load_mac_config(toml_data),
        telegram=_load_telegram_config(toml_data),
        security=_load_security_config(toml_data),
    )


def reset_config() -> None:
    """Reset the global config (for tests)."""
    global _config
    _config = None


__all__ = [
    "Config",
    "LLMConfig",
    "MacControlConfig",
    "SecurityConfig",
    "ServerConfig",
    "TelegramConfig",
    "UserConfig",
    "DEFAULT_HOME",
    "expand_home",
    "get_config",
    "load_config",
    "reset_config",
]

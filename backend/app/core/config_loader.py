"""Configuration loader — TOML read + env-var override + singleton.

Per `docs/ARCHITECTURE.md` §4.1, this module is **separate** from
`app/core/config.py` (which only defines the dataclasses). The
separation matters because:

- The dataclass definitions in `config.py` are loaded at module
  import time. Every `from app.core.config import X` triggers
  parsing + evaluating ~470 lines of default values + nested
  dataclass instantiations. By moving the **loading logic** here,
  callers that import a single config dataclass (e.g. just
  `VoiceLive2DConfig`) trigger fewer side effects.
- The singleton pattern (`get_config` / `reset_config`) belongs
  with the loader, not the type definitions.
- The TOML helpers (`_load_toml` / `_load_sub_config` /
  `_load_tools_config`) are pure functions over `dict`s, so they
  naturally group with the loader rather than the dataclasses.

**Sprint 32 P1.3 refactor**: extract loader from
`app/core/config.py` (828 lines, 18 dataclasses + 16 helper
functions) into this dedicated module. The 16 dataclasses
stay in `config.py` (they're the public contract); the loader
moves here. `__all__` in `config.py` re-exports the loader
symbols so existing `from app.core.config import get_config`
imports continue to work unchanged.
"""
from __future__ import annotations

import dataclasses
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any, Optional

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]

logger = logging.getLogger(__name__)

# NOTE on circular imports: the dataclasses (Config, LLMConfig, ...)
# AND the path helpers (DEFAULT_HOME, expand_home) all live in
# `app.core.config`. This loader module is imported by
# `app.core.config` (to re-export `get_config` / `load_config` /
# `reset_config` for back-compat). So we CANNOT do ANY top-level
# `from app.core.config import ...` here — that would form a
# cycle that fails at module load time.
#
# Instead, every symbol we need from `app.core.config` is
# imported lazily inside the function that uses it. The local
# import is cheap after the first call (cached in `sys.modules`),
# and it runs **after** `app.core.config` has finished its
# top-level evaluation, so the cycle is broken.
#
# The singleton cache (`_config`) lives on `app.core.config`
# itself — see its definition for the rationale (tests +
# `secrets_store.invalidate_config_cache()` both reach into
# `app.core.config._config` directly). The loader reads/writes
# that attribute via `getattr` / `setattr` on the lazily-imported
# module, never on a local.


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
#
# NOTE: there is intentionally NO module-level `_config` variable
# here. The singleton cache lives on `app.core.config._config`
# (see that module for the rationale — tests + secrets_store
# both reach into it). `get_config` and `reset_config` below
# read/write that attribute via the lazy `from app.core import
# config as _config_mod` pattern, never via a local.


def get_config(home: Optional[Path] = None) -> "Config":
    """Get the global config (load from disk on first call).

    The singleton cache lives on `app.core.config._config` (see
    that module for rationale). This function reads/writes that
    attribute lazily to keep the dataclass module as the
    canonical owner without creating a top-level import cycle.
    """
    from app.core import config as _config_mod

    cached = getattr(_config_mod, "_config", None)
    if cached is None:
        cached = load_config(home)
        setattr(_config_mod, "_config", cached)
    return cached


def reset_config() -> None:
    """Reset the global config (for tests).

    Clears `app.core.config._config` so the next `get_config()`
    call rebuilds from disk + env.
    """
    from app.core import config as _config_mod

    setattr(_config_mod, "_config", None)


# ---------------------------------------------------------------------------
# TOML + env-var primitives
# ---------------------------------------------------------------------------


class ConfigParseError(RuntimeError):
    """Raised when ~/.gundam-halo/config.toml is malformed (Sprint 42).

    Carries the offending file path + line + column so
    `app/main.py:lifespan` can surface a 1-line friendly
    error message instead of a raw `tomllib.TOMLDecodeError`
    stack trace on cold start.

    The lifespan re-raises after logging — the process
    exits non-zero, the user's process supervisor (launchd,
    supervisord, etc.) notices + keeps the old binary
    running until the user fixes the TOML.
    """

    def __init__(
        self, config_path: Path, line: int, column: int, message: str
    ):
        self.config_path = config_path
        self.line = line
        self.column = column
        super().__init__(
            f"Failed to parse {config_path}:{line}:{column} — {message}. "
            f"Fix the TOML syntax or validate manually with: "
            f"uv run python -c \"import tomllib; "
            f"tomllib.load(open('{config_path}', 'rb'))\""
        )


# Regex to extract "(at line N, column M)" from tomllib's
# error message (Python 3.11's TOMLDecodeError doesn't carry
# structured lineno/colno attributes — only the string).
_TOML_LINENO_RE = re.compile(r"at line (\d+), column (\d+)")


def _load_toml(path: Path) -> dict:
    """Load a TOML file. Returns empty dict if not found.

    Raises ConfigParseError with the offending file path +
    line + column on malformed input (per Sprint 42
    hardening). Without this catch, a malformed
    ~/.gundam-halo/config.toml raises the raw
    `tomllib.TOMLDecodeError` stack trace at startup —
    hard to read, easy to misdiagnose.
    """
    if not path.exists():
        return {}
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        # Python 3.11's TOMLDecodeError doesn't expose
        # structured lineno/colno; the string carries them.
        # Default to (1, 1) for "at end of document"-style
        # errors that don't include a position.
        match = _TOML_LINENO_RE.search(str(e))
        line = int(match.group(1)) if match else 1
        column = int(match.group(2)) if match else 1
        raise ConfigParseError(
            config_path=path,
            line=line,
            column=column,
            message=str(e),
        ) from e


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


# ---------------------------------------------------------------------------
# Per-section loaders
# ---------------------------------------------------------------------------


def _load_user_config(toml_data: dict) -> "UserConfig":
    from app.core.config import UserConfig
    d = toml_data.get("user", {})
    defaults = UserConfig()
    return UserConfig(
        name=d.get("name", defaults.name),
        default_theme=d.get("default_theme", defaults.default_theme),
    )


def _load_llm_config(toml_data: dict) -> "LLMConfig":
    from app.core.config import LLMConfig
    d = toml_data.get("llm", {})
    api_key_env = d.get("api_key_env", "MINIMAX_API_KEY")
    defaults = LLMConfig()
    return LLMConfig(
        provider=d.get("provider", defaults.provider),
        api_key=_env(api_key_env, ""),  # NEVER store in TOML, always env
        api_key_env=api_key_env,
        base_url=_env("MINIMAX_BASE_URL", d.get("base_url", defaults.base_url)),
        default_model=_env("MINIMAX_MODEL", d.get("default_model", defaults.default_model)),
        fallback_model=d.get("fallback_model", defaults.fallback_model),
    )


def _load_server_config(toml_data: dict) -> "ServerConfig":
    from app.core.config import ServerConfig
    d = toml_data.get("server", {})
    defaults = ServerConfig()
    return ServerConfig(
        host=_env("HALO_HOST", d.get("host", defaults.host)),
        port=_env_int("HALO_PORT", d.get("port", defaults.port)),
        log_level=_env("HALO_LOG_LEVEL", d.get("log_level", defaults.log_level)),
        require_tailscale=_env_bool(
            "HALO_REQUIRE_TAILSCALE", d.get("require_tailscale", defaults.require_tailscale)
        ),
        tailscale_hostname=_env(
            "HALO_TAILSCALE_HOSTNAME", d.get("tailscale_hostname", defaults.tailscale_hostname)
        ),
    )


def _load_mac_config(toml_data: dict) -> "MacControlConfig":
    from app.core.config import MacControlConfig
    d = toml_data.get("mac_control", {})
    # `default_factory` defaults aren't accessible as class attributes;
    # instantiate once to extract the defaults.
    defaults = MacControlConfig()
    return MacControlConfig(
        default_path_policy=d.get("default_path_policy", defaults.default_path_policy),
        shell_allowlist=d.get("shell_allowlist", defaults.shell_allowlist),
        file_read_paths=d.get("file_read_paths", defaults.file_read_paths),
        file_write_paths=d.get("file_write_paths", defaults.file_write_paths),
        a11y_enabled=d.get("a11y_enabled", defaults.a11y_enabled),
        apple_script_enabled=d.get("apple_script_enabled", defaults.apple_script_enabled),
        notifications_enabled=d.get(
            "notifications_enabled", defaults.notifications_enabled
        ),
    )


def _load_telegram_config(toml_data: dict) -> "TelegramConfig":
    from app.core.config import TelegramConfig
    d = toml_data.get("channels", {}).get("telegram", {})
    chat_ids_env = _env("GUNDAM_HALO_TG_ALLOWED_CHAT_IDS", "")
    chat_ids = [int(x) for x in chat_ids_env.split(",") if x.strip().isdigit()]
    defaults = TelegramConfig()
    return TelegramConfig(
        enabled=d.get("enabled", defaults.enabled),
        bot_token=_env("GUNDAM_HALO_TG_TOKEN", ""),
        allowed_chat_ids=chat_ids or d.get("allowed_chat_ids", defaults.allowed_chat_ids),
        command_prefix=d.get("command_prefix", defaults.command_prefix),
        display_names=d.get("display_names", defaults.display_names),
    )


def _load_security_config(toml_data: dict) -> "SecurityConfig":
    from app.core.config import SecurityAuthConfig, SecurityConfig
    d = toml_data.get("security", {})
    defaults = SecurityConfig()
    auth_d = d.get("auth", {}) or {}
    auth_defaults = SecurityAuthConfig()
    return SecurityConfig(
        audit_log=d.get("audit_log", defaults.audit_log),
        audit_max_size_mb=d.get("audit_max_size_mb", defaults.audit_max_size_mb),
        injection_scan=d.get("injection_scan", defaults.injection_scan),
        require_confirm_for=d.get(
            "require_confirm_for", defaults.require_confirm_for
        ),
        # Sprint 48: nested auth config. Empty list = no tag filter.
        auth=SecurityAuthConfig(
            tailscale_allowed_tags=auth_d.get(
                "tailscale_allowed_tags",
                auth_defaults.tailscale_allowed_tags,
            ),
            tailscale_check_disabled=auth_d.get(
                "tailscale_check_disabled",
                auth_defaults.tailscale_check_disabled,
            ),
        ),
    )


def _load_voice_config(toml_data: dict) -> "VoiceConfig":
    """Load the [voice] section and its sub-sections from TOML.

    Per ARCHITECTURE §15 — voice layer config is opt-in. Users enable it by
    setting `voice.enabled = true` in config.toml.
    """
    from app.core.config import (
        VoiceConfig,
        VoiceVADConfig,
        VoiceASRConfig,
        VoiceTTSConfig,
        VoiceLive2DConfig,
    )
    d = toml_data.get("voice", {})
    defaults = VoiceConfig()

    vad_d = d.get("vad", {})
    vad_defaults = VoiceVADConfig()
    vad = VoiceVADConfig(
        backend=vad_d.get("backend", vad_defaults.backend),
        model_path=vad_d.get("model_path", vad_defaults.model_path),
        speech_threshold_start=vad_d.get(
            "speech_threshold_start", vad_defaults.speech_threshold_start
        ),
        speech_threshold_end=vad_d.get(
            "speech_threshold_end", vad_defaults.speech_threshold_end
        ),
        min_speech_ms=vad_d.get("min_speech_ms", vad_defaults.min_speech_ms),
        min_silence_ms=vad_d.get("min_silence_ms", vad_defaults.min_silence_ms),
    )

    asr_d = d.get("asr", {})
    asr_defaults = VoiceASRConfig()
    asr = VoiceASRConfig(
        backend=asr_d.get("backend", asr_defaults.backend),
        model_size=asr_d.get("model_size", asr_defaults.model_size),
        model_path=asr_d.get("model_path", asr_defaults.model_path),
        language=asr_d.get("language", asr_defaults.language),
        device=asr_d.get("device", asr_defaults.device),
        compute_type=asr_d.get("compute_type", asr_defaults.compute_type),
        # Sprint 17b: corrector backend. Validated at
        # asr_factory time (not here) so users with whisper_local
        # don't see a "corrector" error if they accidentally
        # leave it set.
        corrector=asr_d.get("corrector", asr_defaults.corrector),
    )

    tts_d = d.get("tts", {})
    tts_defaults = VoiceTTSConfig()
    tts = VoiceTTSConfig(
        backend=tts_d.get("backend", tts_defaults.backend),
        voice=tts_d.get("voice", tts_defaults.voice),
        rate=tts_d.get("rate", tts_defaults.rate),
        pitch=tts_d.get("pitch", tts_defaults.pitch),
        volume=tts_d.get("volume", tts_defaults.volume),
    )

    live2d_d = d.get("live2d", {})
    live2d_defaults = VoiceLive2DConfig()
    live2d = VoiceLive2DConfig(
        enabled=live2d_d.get("enabled", live2d_defaults.enabled),
        theme=live2d_d.get("theme", live2d_defaults.theme),
        model_path=live2d_d.get("model_path", live2d_defaults.model_path),
        default_emotion=live2d_d.get(
            "default_emotion", live2d_defaults.default_emotion
        ),
    )

    return VoiceConfig(
        enabled=d.get("enabled", defaults.enabled),
        vad=vad,
        asr=asr,
        tts=tts,
        live2d=live2d,
        sample_rate=d.get("sample_rate", defaults.sample_rate),
        frame_duration_ms=d.get("frame_duration_ms", defaults.frame_duration_ms),
        wake_phrases=d.get("wake_phrases", defaults.wake_phrases),
        # Sprint 17a: read the new strict-mode flag. Note that
        # `_load_voice_config()` does NOT emit a "first-launch
        # upgrade" log here — see `load_config()` below, which
        # has access to whether the key was actually present in
        # the TOML (so we only log when the user has not yet
        # made an explicit choice). Reading the value here is
        # pure data; the user-experience nudge lives elsewhere.
        strict_wake_phrase=d.get(
            "strict_wake_phrase", defaults.strict_wake_phrase
        ),
        # Sprint 19c: always-on mic toggle. Runtime-tunable
        # (no restart needed) — the field lives under [voice]
        # alongside strict_wake_phrase so the user has a
        # single section to look at for voice preferences.
        always_on_mic=d.get(
            "always_on_mic", defaults.always_on_mic
        ),
    )


def _load_memory_config(toml_data: dict) -> "MemoryConfig":
    """Load the [memory] section from TOML.

    All fields are optional and fall back to MemoryConfig defaults.
    See ARCHITECTURE §M12 for design rationale.
    """
    from app.core.config import MemoryConfig
    d = toml_data.get("memory", {})
    defaults = MemoryConfig()
    return MemoryConfig(
        embedding_backend=d.get("embedding_backend", defaults.embedding_backend),
        embedding_dim=d.get("embedding_dim", defaults.embedding_dim),
        embed_queue_max=d.get("embed_queue_max", defaults.embed_queue_max),
        sqlite_wal=d.get("sqlite_wal", defaults.sqlite_wal),
        auto_rebuild=d.get("auto_rebuild", defaults.auto_rebuild),
        disable_vector_index=d.get(
            "disable_vector_index", defaults.disable_vector_index
        ),
    )


# ---------------------------------------------------------------------------
# Tools config loader (Sprint 28/29)
# ---------------------------------------------------------------------------


def _load_sub_config(
    section_dict: dict,
    sub_config_class: type,
) -> Any:
    """Generic sub-config loader.

    Iterates `dataclasses.fields(sub_config_class)` in
    declaration order and pulls each field from
    `section_dict.get(field.name, <default>)`. This
    generalises the field-by-field read pattern that
    `_load_memory_config` and `_load_voice_config`
    inline — Sprint 28 lifts it into a helper so any
    future sub-config (e.g. `LoggingConfig`,
    `SecurityAuditConfig`) can be added without
    touching the loader.

    Args:
        section_dict: The TOML section dict (e.g.
            `toml_data["tools"]["web_search"]`).
        sub_config_class: The dataclass to instantiate
            (e.g. `WebSearchConfig`).

    Returns:
        An instance of `sub_config_class` with all
        fields populated. Missing fields fall back to
        the dataclass's defaults.
    """
    defaults = sub_config_class()
    kwargs: dict = {}
    for f in dataclasses.fields(sub_config_class):
        kwargs[f.name] = section_dict.get(
            f.name, getattr(defaults, f.name)
        )
    return sub_config_class(**kwargs)


def _load_tools_config(toml_data: dict) -> "ToolsConfig":
    """Load the [tools.*] sections from TOML.

    All fields are optional and fall back to the
    ToolsConfig defaults. The 4 sub-configs
    (`WebSearchConfig`, `YouTubeSummarizeConfig`,
    `FlightFinderConfig`, `SendMessageConfig`) are
    loaded via the generic `_load_sub_config` helper.

    An unknown `[tools.bogus]` section in TOML is
    silently ignored — only the 4 known sub-configs
    are loaded. This is intentional: forward-
    compatibility for older configs that may have
    stale `tools.*` sections.

    See `docs/FEATURE-SPEC-SPRINT28.md` for the
    design rationale.
    """
    from app.core.config import (
        ToolsConfig,
        WebSearchConfig,
        YouTubeSummarizeConfig,
        FlightFinderConfig,
        SendMessageConfig,
    )
    d = toml_data.get("tools", {})
    return ToolsConfig(
        web_search=_load_sub_config(
            d.get("web_search", {}), WebSearchConfig
        ),
        youtube_summarize=_load_sub_config(
            d.get("youtube_summarize", {}),
            YouTubeSummarizeConfig
        ),
        flight_finder=_load_sub_config(
            d.get("flight_finder", {}), FlightFinderConfig
        ),
        send_message=_load_sub_config(
            d.get("send_message", {}), SendMessageConfig
        ),
    )


# ---------------------------------------------------------------------------
# Top-level loader
# ---------------------------------------------------------------------------


def load_config(home: Optional[Path] = None) -> "Config":
    """Load config from TOML + env vars."""
    from app.core.config import Config, DEFAULT_HOME, expand_home
    home = expand_home(home or _env("HALO_HOME", str(DEFAULT_HOME)))
    toml_data = _load_toml(home / "config.toml")

    return Config(
        home=home,
        user=_load_user_config(toml_data),
        llm=_load_llm_config(toml_data),
        server=_load_server_config(toml_data),
        mac=_load_mac_config(toml_data),
        telegram=_load_telegram_config(toml_data),
        security=_load_security_config(toml_data),
        voice=_load_voice_config(toml_data),
        memory=_load_memory_config(toml_data),
        # Sprint 28/29: tools config (4 sub-configs
        # for the Mark-XL tool imports).
        tools=_load_tools_config(toml_data),
    )


__all__ = [
    "get_config",
    "load_config",
    "reset_config",
]
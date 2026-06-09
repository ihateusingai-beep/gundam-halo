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
    # IMPORTANT: the MiniMax API has at least two distinct OpenAI-compatible
    # endpoints — `api.MiniMax.chat` and `api.minimax.io` — that DO NOT share
    # keys. The gundam-halo project ships with `.io` because that's the
    # cluster the project's MiniMax API key was issued against (same as
    # Open-LLM-VTuber's `conf.yaml`). If you see 401 `invalid api key (2049)`
    # on a key that works elsewhere, check the host here.
    base_url: str = "https://api.minimax.io/v1"
    default_model: str = "MiniMax-M2"
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
    # chat_id (str) → display name. Lets the agent know who's talking.
    # Example: display_names = { "123456789": "Ken" }
    display_names: Dict[str, str] = field(default_factory=dict)


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
class VoiceVADConfig:
    """VAD (voice activity detection) settings."""

    backend: str = "silero"  # only "silero" in v1
    model_path: str = "~/.gundam-halo/models/silero_vad.onnx"
    speech_threshold_start: float = 0.5
    speech_threshold_end: float = 0.3
    min_speech_ms: int = 250
    min_silence_ms: int = 700


@dataclass
class VoiceASRConfig:
    """ASR (automatic speech recognition) settings."""

    backend: str = "whisper_local"  # only "whisper_local" in v1
    model_size: str = "base"  # tiny|base|small|medium|large
    language: str = "auto"  # auto|en|zh|yue|ja|...
    device: str = "auto"  # auto|cpu|cuda|mps
    compute_type: str = "auto"  # auto|int8|float16|float32


@dataclass
class VoiceTTSConfig:
    """TTS (text-to-speech) settings — v1 reserved, not used in M1."""

    backend: str = "edge"  # only "edge" in v1
    voice: str = "zh-HK-HiuMaanNeural"
    rate: str = "+0%"
    pitch: str = "+0Hz"
    volume: str = "+0%"


@dataclass
class VoiceLive2DConfig:
    """Live2D trigger settings — v1 reserved, not used in M1."""

    enabled: bool = True
    theme: str = "ntd"  # v1: only "ntd"
    model_path: str = "~/.gundam-halo/models/live2d/unicorn/"
    default_emotion: str = "calm"


@dataclass
class VoiceConfig:
    """Voice + Live2D interaction layer config (see ARCHITECTURE §15)."""

    enabled: bool = False  # disabled by default; turn on with voice.enabled = true
    vad: VoiceVADConfig = field(default_factory=VoiceVADConfig)
    asr: VoiceASRConfig = field(default_factory=VoiceASRConfig)
    tts: VoiceTTSConfig = field(default_factory=VoiceTTSConfig)
    live2d: VoiceLive2DConfig = field(default_factory=VoiceLive2DConfig)
    sample_rate: int = 16000
    frame_duration_ms: int = 250  # chunk size for streaming audio frames


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
    voice: VoiceConfig = field(default_factory=VoiceConfig)

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
    defaults = UserConfig()
    return UserConfig(
        name=d.get("name", defaults.name),
        default_theme=d.get("default_theme", defaults.default_theme),
    )


def _load_llm_config(toml_data: dict) -> LLMConfig:
    d = toml_data.get("llm", {})
    api_key_env = d.get("api_key_env", "MINIMAX_API_KEY")
    defaults = LLMConfig()
    return LLMConfig(
        provider=d.get("provider", defaults.provider),
        api_key=_env(api_key_env, ""),  # NEVER store in TOML, always env
        base_url=_env("MINIMAX_BASE_URL", d.get("base_url", defaults.base_url)),
        default_model=_env("MINIMAX_MODEL", d.get("default_model", defaults.default_model)),
        fallback_model=d.get("fallback_model", defaults.fallback_model),
    )


def _load_server_config(toml_data: dict) -> ServerConfig:
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


def _load_mac_config(toml_data: dict) -> MacControlConfig:
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


def _load_telegram_config(toml_data: dict) -> TelegramConfig:
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


def _load_security_config(toml_data: dict) -> SecurityConfig:
    d = toml_data.get("security", {})
    defaults = SecurityConfig()
    return SecurityConfig(
        audit_log=d.get("audit_log", defaults.audit_log),
        audit_max_size_mb=d.get("audit_max_size_mb", defaults.audit_max_size_mb),
        injection_scan=d.get("injection_scan", defaults.injection_scan),
        require_confirm_for=d.get(
            "require_confirm_for", defaults.require_confirm_for
        ),
    )


def _load_voice_config(toml_data: dict) -> VoiceConfig:
    """Load the [voice] section and its sub-sections from TOML.

    Per ARCHITECTURE §15 — voice layer config is opt-in. Users enable it by
    setting `voice.enabled = true` in config.toml.
    """
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
        language=asr_d.get("language", asr_defaults.language),
        device=asr_d.get("device", asr_defaults.device),
        compute_type=asr_d.get("compute_type", asr_defaults.compute_type),
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
        voice=_load_voice_config(toml_data),
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
    "VoiceASRConfig",
    "VoiceConfig",
    "VoiceLive2DConfig",
    "VoiceTTSConfig",
    "VoiceVADConfig",
    "DEFAULT_HOME",
    "expand_home",
    "get_config",
    "load_config",
    "reset_config",
]

"""Configuration dataclasses.

This module owns the **shape** of the configuration: 18 dataclasses
that mirror the structure of `~/.gundam-halo/config.toml` (plus env
var overrides for secrets). Pure data, no side effects.

The actual loading logic — TOML parsing, env-var overrides,
sub-config dispatch, the singleton cache — lives in
`app.core.config_loader`. Splitting dataclasses from loaders
keeps the dataclass module cheap to import (no TOML parser,
no env lookups, no singleton state) and lets the loader evolve
independently. See `app/core/config_loader.py` for the loader
and the rationale.

The legacy public surface (`from app.core.config import
get_config` / `load_config` / `reset_config` / `DEFAULT_HOME` /
`expand_home`) is preserved via `__all__` re-exports from
`config_loader`. Existing call sites continue to work unchanged.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from app.core.config_loader import (
    _load_sub_config,
    get_config,
    load_config,
    reset_config,
)

# Module-level singleton cache for the loaded `Config`. Lives here
# (the dataclass module) rather than in `config_loader` because:
#
# 1. Tests reach into `app.core.config._config` to verify cache
#    invalidation (see `tests/core/test_secrets_store.py::
#    TestSecretsEndpoint::test_post_invalidates_config_cache`).
# 2. `secrets_store.invalidate_config_cache()` writes to
#    `app.core.config._config` to mark the cache stale.
#
# Putting the singleton here keeps that contract stable. The
# loader (`app/core/config_loader.py`) reads/writes this attribute
# lazily inside its functions, so there's no top-level cycle
# between the two modules.
_config: Optional["Config"] = None


# ---------------------------------------------------------------------------
# Default paths
# ---------------------------------------------------------------------------

DEFAULT_HOME = Path.home() / ".gundam-halo"


def expand_home(path: str | Path) -> Path:
    """Expand ~ and resolve to absolute Path."""
    return Path(os.path.expanduser(str(path))).resolve()


# `Config.home` uses `expand_home(DEFAULT_HOME)` for its default
# factory, so these two symbols must remain importable from this
# module path. `get_config` / `load_config` / `reset_config` are
# re-exported from `config_loader` above for back-compat with the
# pre-Sprint-32-P1.3 public surface.
__all__ = [
    # Dataclasses (the public contract)
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
    "MemoryConfig",
    "WebSearchConfig",
    "YouTubeSummarizeConfig",
    "FlightFinderConfig",
    "SendMessageConfig",
    "ToolsConfig",
    # Path helpers (kept for back-compat)
    "DEFAULT_HOME",
    "expand_home",
    # Loader entry points (re-exported from config_loader)
    "get_config",
    "load_config",
    "reset_config",
]


# ---------------------------------------------------------------------------
# Config dataclasses
# ---------------------------------------------------------------------------


@dataclass
class LLMConfig:
    provider: str = "minimax"
    api_key: str = ""
    # The name of the env var that holds the raw API key. Default
    # `MINIMAX_API_KEY` is the one we use everywhere; the wizard writes
    # this *name* (not the key itself) into config.toml as
    # `api_key_env = "MINIMAX_API_KEY"`.
    #
    # IMPORTANT: the MiniMax API has at least two distinct OpenAI-compatible
    # endpoints — `api.MiniMax.chat` and `api.minimax.io` — that DO NOT share
    # keys. The gundam-halo project ships with `.io` because that's the
    # cluster the project's MiniMax API key was issued against (same as
    # Open-LLM-VTuber's `conf.yaml`). If you see 401 `invalid api key (2049)`
    # on a key that works elsewhere, check the host here.
    api_key_env: str = "MINIMAX_API_KEY"
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
class SecurityAuthConfig:
    """Sprint 48 — auth layer configuration.

    The bearer token itself lives in `$HALO_HOME/.env` (read by
    `app.core.config_loader._load_dotenv()` into `os.environ`).
    This block configures the *defence-in-depth* Tailscale check
    that runs alongside the bearer check.

    `tailscale_allowed_tags`:
      - Empty list (default) = no tag filter; any authenticated
        Tailscale peer passes the identity check.
      - Non-empty = the peer's `Tailscale-Identity` JWT must
        carry at least one of these tags.

    `tailscale_check_disabled`:
      - True = skip the Tailscale identity check entirely.
        Useful for dev / CI where `tailscaled` isn't running.
      - False (default) = probe the local API and enforce if
        reachable; log a warning + skip if not.
    """
    tailscale_allowed_tags: List[str] = field(default_factory=list)
    tailscale_check_disabled: bool = False


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
    # Sprint 48: nested auth block. Empty list = no tag filter.
    auth: SecurityAuthConfig = field(default_factory=SecurityAuthConfig)


@dataclass
class UserConfig:
    name: str = "User"
    default_theme: str = "gundam-ntd"


@dataclass
class VoiceVADConfig:
    """VAD (voice activity detection) settings."""

    backend: str = "silero"  # only "silero" in v1
    # Sprint 37 — default to `.jit` (TorchScript). The upstream
    # Silero V5 ONNX file at the configured URL is corrupted as
    # of 2024-06 per the memory rule "Silero VAD ONNX 損壞需用
    # TorchScript bundle"; the only currently-valid V5 model is
    # the `silero-vad` PyPI bundle (a `.jit` file). If you have
    # the `.onnx` file, set this to that path explicitly — the
    # sibling-file probe in `silero_vad.warmup()` also handles
    # this transparently (probes `.jit` / `.pt` / `.onnx` in
    # the same directory in priority order).
    model_path: str = "~/.gundam-halo/models/silero_vad.jit"
    speech_threshold_start: float = 0.5
    speech_threshold_end: float = 0.3
    min_speech_ms: int = 250
    min_silence_ms: int = 700


@dataclass
class VoiceASRConfig:
    """ASR (automatic speech recognition) settings."""

    backend: str = "whisper_local"  # "whisper_local" (Sprint 16) | "yuesub" (Sprint 17b)
    model_size: str = "base"  # tiny|base|small|medium|large
    # M9-E Layer 2 (v0.1.3): when set, points at a local HF-format
    # fine-tuned checkpoint (e.g. ~/.gundam-halo/models/whisper-yue-base/).
    # Takes precedence over model_size if the directory exists.
    model_path: str = ""
    language: str = "auto"  # auto|en|zh|yue|ja|...
    device: str = "auto"  # auto|cpu|cuda|mps
    compute_type: str = "auto"  # auto|int8|float16|float32
    # Sprint 17b (yuesub backend only): which corrector to apply to
    # ASR output before wake detection. One of "bert" | "opencc" | "none".
    # "bert" requires hon9kon9ize/bert-large-cantonese to be downloaded
    # (`scripts/setup-yuesub-models.sh` after running
    # `python download_models.py --with-bert` inside the yuesub-api
    # repo). "opencc" is regex-only and runs in <5ms per segment.
    # "none" skips the corrector entirely (raw SenseVoice text).
    corrector: str = "bert"


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

    # Sprint 37 — flip default to True so cold-install users
    # get a working voice layer out of the box. The previous
    # default of False meant /voice/status, /voice/config,
    # and /ws/voice all returned 404 on first launch, which
    # broke the dashboard's voice tab. Set this to False
    # explicitly to disable voice.
    enabled: bool = True
    vad: VoiceVADConfig = field(default_factory=VoiceVADConfig)
    asr: VoiceASRConfig = field(default_factory=VoiceASRConfig)
    tts: VoiceTTSConfig = field(default_factory=VoiceTTSConfig)
    live2d: VoiceLive2DConfig = field(default_factory=VoiceLive2DConfig)
    sample_rate: int = 16000
    frame_duration_ms: int = 250  # chunk size for streaming audio frames
    # Sprint 16 (Unicorn voice control): text-level wake phrases. The
    # voice pipeline checks whether the ASR transcript starts with
    # one of these strings, and if so, strips the prefix and tags
    # the turn as `wake_triggered: True` in the agent.message frame.
    # User-approved default (2026-06-14):
    #   "Unicorn" — brand
    #   "NTD"     — Gundam NT-D theme, in-world codename
    #   "gundam"  — lowercase to match casual speech
    #   "獨角獸"  — "Unicorn" literal Chinese
    #   "高達"    — "Gundam" Cantonese pronunciation
    # Empty list disables the detection (the agent is still invoked
    # on every transcript, just without a `wake_triggered` flag).
    wake_phrases: List[str] = field(
        default_factory=lambda: [
            "Unicorn",
            "NTD",
            "gundam",
            "獨角獸",
            "高達",
        ]
    )
    # Sprint 17a (strict wake-phrase mode): when True, voice turns
    # whose ASR transcript does not start with a configured wake
    # phrase are discarded — no agent invocation, no TTS, a brief
    # cockpit hint. Default flipped from False → True in Sprint 17a
    # (breaking change for users who never opened Settings → Voice).
    # The 7-day upgrade banner (Sprint 17a §11) was removed in
    # Sprint 23 (v0.1.4) as the TTL has long expired for all users.
    # Users who want the old permissive behavior can set
    # strict_wake_phrase = false in ~/.gundam-halo/config.toml
    # under [voice] or via the Settings → Voice tab.
    strict_wake_phrase: bool = True
    # Sprint 19c: always-on mic mode. When True, the cockpit
    # auto-fires the agent on the backend's VAD speech_start
    # event instead of requiring a push-to-talk hold gesture.
    # Runtime-tunable (no restart required) because the
    # always-on flow is a frontend UX choice — the backend
    # always forwards VAD events either way.
    always_on_mic: bool = False


@dataclass
class MemoryConfig:
    """Structured memory layer config (M12 — SQLite + FAISS).

    The JSON / MD files remain the source of truth; SQLite is a
    queryable index and FAISS is the vector recall index. Both are
    rebuildable from disk (see ``app/memory/lifecycle.py``).
    """

    # Embedding backend:
    #   "hash"  — deterministic, offline, no model. Poor quality.
    #   "model" — sentence-transformers/all-MiniLM-L6-v2 (v0.2.1+).
    embedding_backend: str = "hash"
    embedding_dim: int = 384

    # Background embedder queue cap. Past this, oldest entries are
    # dropped (the SQLite index will still have them, just not vectors).
    embed_queue_max: int = 5000

    # SQLite WAL mode. ON = better read concurrency.
    sqlite_wal: bool = True

    # Rebuild on startup if index is missing or schema is older.
    auto_rebuild: bool = True

    # Disable the FAISS-backed vector index. When True, the lifecycle
    # layer uses NullVectorIndex (no FAISS native module loaded).
    # This is mainly useful for test environments where loading
    # faiss-cpu + torch together in the same process can crash on
    # Apple Silicon (see M12 ticket "Known follow-ups").
    disable_vector_index: bool = False


# ---------------------------------------------------------------------------
# Tools config (Sprint 28/29) — see docs/FEATURE-SPEC-SPRINT28.md
# ---------------------------------------------------------------------------
# 5 new dataclasses that control the 4 Mark-XL tools imported
# in Sprint 27 (commit 4a7a83e). The user can disable a tool per-tool
# by setting `enabled = false` in the corresponding [tools.*] section
# of ~/.gundam-halo/config.toml. Changes take effect on backend
# restart (Sprint 28 spec §4.5 restart caveat; runtime toggling is
# deferred to a future sprint).
#
# The 4 sub-configs follow the same pattern as the existing 8
# sub-configs (UserConfig, LLMConfig, etc.) — a flat dataclass
# with all fields required (or default). The _load_sub_config
# helper (see _load_tools_config in config_loader.py) iterates
# dataclasses.fields() to populate each sub-config from its TOML
# section, so a new field added to a sub-config requires only
# 1 line in the dataclass + 1 line in config.toml.example — no
# changes to the loader.


@dataclass
class WebSearchConfig:
    """Settings for the WebSearchTool (Sprint 27 Track 27.1).

    Per `docs/FEATURE-SPEC-SPRINT27.md` §4.2.
    The tool searches DuckDuckGo's HTML endpoint and returns
    TTS-friendly prose. No new deps; uses the existing httpx.
    """
    enabled: bool = True
    # Cap on results fetched from DDG (1-10). Default 5.
    max_results: int = 5
    # Cap on the formatted output length (chars) to keep
    # the TTS response under the 60s budget. Default 800.
    summary_max_chars: int = 800
    # HTTP timeout for the DDG endpoint. Default 10s.
    request_timeout_s: float = 10.0


@dataclass
class YouTubeSummarizeConfig:
    """Settings for the YouTubeSummarizeTool (Sprint 27 Track 27.2).

    The tool fetches a YouTube video's transcript via the optional
    `youtube-transcript-api` library. Without the dep, the tool
    falls back to YouTube's oEmbed API for title + author metadata.
    """
    enabled: bool = True
    # Cap on transcript length before LLM summarisation.
    # Default 12000 (matches Mark-XL).
    max_transcript_chars: int = 12_000
    # Cap on the formatted output length (chars).
    summary_max_chars: int = 800


@dataclass
class FlightFinderConfig:
    """Settings for the FlightFinderTool (Sprint 27 Track 27.3,
    Sprint 30 Track B).

    Sprint 30 Track B (per `docs/FEATURE-SPEC-SPRINT30.md` §4.3)
    added the real aviationstack-based flight-data extractor.
    The Sprint 27 URL builder stays as the fallback when the
    user hasn't set an `api_key` (free-tier testing, opt-out,
    or no paid account) or when the API errors
    (401/403/429/5xx).
    """
    enabled: bool = True
    # Sprint 30 Track B: aviationstack access key. Leave
    # empty to fall back to the Sprint 27 URL builder.
    # Get a free key (100 requests/month) at
    # https://aviationstack.com/signup. The paid tier
    # ($50/month for 10,000 requests) covers heavier use.
    api_key: str = ""
    # Sprint 30 Track B: which flight API provider to use.
    # Currently only "aviationstack" is wired in (per spec §4.2
    # — aviationstack is the primary API). "serpapi" is
    # reserved for a future sprint (see Appendix B in the
    # spec). Any value other than "aviationstack" falls
    # back to the URL builder.
    api_provider: str = "aviationstack"
    # Sprint 30 Track B: how many top flights to include in
    # the prose summary (1-10, default 5). aviationstack's
    # free tier returns ≤10 flights per request, so 5 is a
    # reasonable cap that keeps the TTS response under the
    # 60s budget.
    top_n: int = 5


@dataclass
class SendMessageConfig:
    """Settings for the SendMessageTool (Sprint 27 Track 27.4,
    Sprint 30 Track A).

    The `enabled` flag defaults to `False` because pyautogui
    is fragile. The other fields are optional with sensible
    defaults. Sprint 30 Track A replaced the hard-coded
    coordinate approach with a YOLO-based computer-vision
    detector. The YOLO model is bundled at
    `~/.gundam-halo/models/yolov8n-messaging.onnx`
    (~50MB, downloaded on first use via
    `scripts/download_yolo_model.py`).
    """
    enabled: bool = False  # OPT-IN: pyautogui is fragile
    # Default messaging platform when none is specified.
    default_platform: str = "whatsapp"
    # Sprint 30 Track A: YOLO detection confidence threshold
    # (0-1, default 0.7). Lower = more lenient (catches more
    # candidates, but more false positives). The user can
    # lower this if the YOLO model fails to detect UI in
    # low-contrast conditions.
    detection_confidence: float = 0.7
    # Sprint 30 Track A: path to the bundled YOLO model
    # (default = ~/.gundam-halo/models/yolov8n-messaging.onnx).
    # Set this to a custom path if the user wants to use
    # a different model (e.g. a re-trained version for
    # a specific app version).
    yolo_model_path: str = ""
    # Sprint 30 Track A: how long to wait for the app to
    # launch before taking the first screenshot (seconds).
    # Default 2.5s — most apps are ready in <2s but the
    # extra 0.5s gives buffer for slow Macs.
    app_launch_wait_s: float = 2.5
    # Sprint 30 Track A: delay between typed characters
    # (seconds). Default 0.05s — pyautogui's default is
    # 0.0 (instant). 0.05s gives the app time to process
    # each character reliably.
    typing_delay_s: float = 0.05
    # OS family (auto-detected from sys.platform by default;
    # uncomment to override). Reserved for Sprint 31+ when
    # the pyautogui flow is implemented.
    # os_system: str = "darwin"  # darwin | win32 | linux


@dataclass
class ToolsConfig:
    """Settings for the agent's tool registry (Sprint 28/29).

    Per `docs/FEATURE-SPEC-SPRINT28.md` and
    `docs/FEATURE-SPEC-SPRINT27.md` §4.4.

    The 4 sub-configs control the 4 Mark-XL tools imported
    in Sprint 27 (commit 4a7a83e). Each sub-config has an
    `enabled` flag that gates whether the tool is registered
    in the agent's tool list (`app/tools/builder.py::default_tools()`).
    A disabled tool is **invisible** to the LLM — the
    agent's tool spec list does not include it.

    Changes to `enabled` take effect on backend restart
    (not runtime-tunable in v0.1.5+). The restart caveat
    is documented in `config.toml.example` and the
    CHANGELOG entry.
    """
    web_search: WebSearchConfig = field(
        default_factory=WebSearchConfig
    )
    youtube_summarize: YouTubeSummarizeConfig = field(
        default_factory=YouTubeSummarizeConfig
    )
    flight_finder: FlightFinderConfig = field(
        default_factory=FlightFinderConfig
    )
    send_message: SendMessageConfig = field(
        default_factory=SendMessageConfig
    )


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
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    # Sprint 28/29: agent tool registry settings. The 4
    # Mark-XL tools imported in Sprint 27 (web_search,
    # youtube_summarize, flight_finder, send_message)
    # are conditionally registered based on
    # `tools.<name>.enabled`. See
    # `docs/FEATURE-SPEC-SPRINT28.md` for the
    # design rationale.
    tools: ToolsConfig = field(default_factory=ToolsConfig)

    @property
    def log_level(self) -> str:
        return self.server.log_level
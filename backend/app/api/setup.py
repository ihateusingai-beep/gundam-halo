"""Setup wizard API — 11 endpoints for the M13 first-run experience.

Endpoint map (mirrors M13 §"API design"):

    GET  /api/setup/state                 — current state
    POST /api/setup/start                 — begin wizard, set started_at
    POST /api/setup/llm                   — save LLM config + test connection
    POST /api/setup/voice-asr             — save ASR config, validate model
    POST /api/setup/voice-tts             — save TTS config
    POST /api/setup/theme                 — save theme pick
    POST /api/setup/tailscale             — save hostname, test reachability
    POST /api/setup/smoke                 — run end-to-end smoke
    POST /api/setup/finish                — mark finished, redirect target=/
    POST /api/setup/skip                  — mark skipped (advanced)
    POST /api/setup/reset                 — wipe state, restart at step 1

Every POST returns ``{ok, next_step, errors?}``. ``errors`` is a list of
``{field, code, message}`` so the UI can highlight fields.

Security model
--------------
- The LLM step receives a raw API key from the wizard UI. The handler
  writes it to the existing ``SecretStore`` (which atomically persists
  to ``$HALO_HOME/.env`` with 0600 perms) and returns ONLY the env var
  name. The TOML is updated to reference that env var — never the raw
  key.
- Every endpoint is local-only (the FastAPI server has no auth yet —
  single-user assumption per the project convention).
- Every state mutation is atomic (write to ``setup_state.json`` via
  ``tempfile + os.replace``).

Lifecycle
---------
The router is mounted by ``app.main`` under prefix ``/api/setup`` and
does NOT replace the main app — when the wizard is finished or skipped
the user lands on the regular dashboard.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import httpx
import tomlkit
from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator

from app.core.config import (
    get_config,
)
from app.core.secrets_store import SECRET_KEYS, get_secret_store
from app.core.setup_state import (
    ALLOWED_ASR_BACKENDS,
    ALLOWED_LLM_PROVIDERS,
    ALLOWED_THEMES,
    ALLOWED_TTS_BACKENDS,
    SetupState,
    compute_setup_state,
    is_tailscale_reachable,
    load_setup_state,
    now_iso,
    reset_setup_state,
    save_setup_state,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic request models
# ---------------------------------------------------------------------------


class StartRequest(BaseModel):
    """Body for POST /api/setup/start (no fields yet; placeholder for future)."""

    pass


class LLMSetupRequest(BaseModel):
    """Body for POST /api/setup/llm.

    The wizard sends a raw API key. We store it in SecretStore and
    write the env-var name to config.toml.
    """

    provider: str = Field(..., min_length=1, max_length=64)
    api_key: str = Field(..., min_length=1, max_length=2048)
    base_url: str = Field(..., min_length=1, max_length=512)
    default_model: str = Field(..., min_length=1, max_length=128)
    fallback_model: str = Field("", max_length=128)
    # Optional: allow the wizard to pin a custom env var name. Defaults
    # to MINIMAX_API_KEY (the only one SecretStore currently allows).
    api_key_env: str = Field("MINIMAX_API_KEY", max_length=128)

    @field_validator("provider")
    @classmethod
    def _validate_provider(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in ALLOWED_LLM_PROVIDERS:
            raise ValueError(
                f"provider must be one of {ALLOWED_LLM_PROVIDERS}"
            )
        return v


class VoiceASRRequest(BaseModel):
    """Body for POST /api/setup/voice-asr."""

    backend: str = Field("whisper_local", max_length=64)
    model_size: str = Field("base", max_length=32)
    model_path: str = Field("", max_length=1024)
    language: str = Field("auto", max_length=32)
    device: str = Field("auto", max_length=16)
    compute_type: str = Field("auto", max_length=16)

    @field_validator("backend")
    @classmethod
    def _validate_backend(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in ALLOWED_ASR_BACKENDS:
            raise ValueError(f"ASR backend must be one of {ALLOWED_ASR_BACKENDS}")
        return v

    @field_validator("model_size")
    @classmethod
    def _validate_model_size(cls, v: str) -> str:
        v = v.strip().lower()
        allowed = {"tiny", "base", "small", "medium", "large"}
        if v and v not in allowed:
            raise ValueError(f"model_size must be one of {sorted(allowed)}")
        return v


class VoiceTTSRequest(BaseModel):
    """Body for POST /api/setup/voice-tts."""

    backend: str = Field("edge", max_length=64)
    voice: str = Field("zh-HK-HiuMaanNeural", max_length=128)
    rate: str = Field("+0%", max_length=16)
    pitch: str = Field("+0Hz", max_length=16)
    volume: str = Field("+0%", max_length=16)

    @field_validator("backend")
    @classmethod
    def _validate_backend(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in ALLOWED_TTS_BACKENDS:
            raise ValueError(f"TTS backend must be one of {ALLOWED_TTS_BACKENDS}")
        return v


class ThemeRequest(BaseModel):
    """Body for POST /api/setup/theme."""

    theme: str = Field(..., min_length=1, max_length=64)

    @field_validator("theme")
    @classmethod
    def _validate_theme(cls, v: str) -> str:
        v = v.strip()
        if v not in ALLOWED_THEMES:
            raise ValueError(f"theme must be one of {ALLOWED_THEMES}")
        return v


class TailscaleRequest(BaseModel):
    """Body for POST /api/setup/tailscale."""

    hostname: str = Field("gundam-halo", min_length=1, max_length=128)
    require_tailscale: bool = Field(True)
    # If True, the server will ping the hostname before persisting.
    test_reachability: bool = Field(True)


class ResetRequest(BaseModel):
    """Body for POST /api/setup/reset (no fields; placeholder)."""

    pass


# ---------------------------------------------------------------------------
# TOML helpers — round-trip the user's config without losing comments
# ---------------------------------------------------------------------------


def _toml_path(home: Path) -> Path:
    return Path(home) / "config.toml"


def _load_toml_doc(path: Path) -> tuple[tomlkit.TOMLDocument, bool]:
    """Load a TOML document, returning ``(doc, existed)``.

    If the file doesn't exist, returns an empty document and existed=False.
    """
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return tomlkit.load(f), True
    return tomlkit.document(), False


def _write_toml_doc(path: Path, doc: tomlkit.TOMLDocument) -> None:
    """Atomically write a TOML document to *path*."""
    path.parent.mkdir(parents=True, exist_ok=True)
    body = tomlkit.dumps(doc)
    tmp_fd, tmp_path = _tmp_file_in(path.parent)
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            f.write(body)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _tmp_file_in(directory: Path) -> tuple[int, str]:
    """Create a uniquely-named tmp file in *directory*; return (fd, path)."""
    import tempfile

    return tempfile.mkstemp(prefix=".config.toml.", dir=str(directory), text=True)


def _update_llm(doc: tomlkit.TOMLDocument, payload: LLMSetupRequest) -> None:
    """Apply LLM-step fields to the TOML doc (writes env-var name only)."""
    if "llm" not in doc:
        doc["llm"] = tomlkit.table()
    llm = doc["llm"]
    llm["provider"] = payload.provider
    # CRITICAL: write the env var NAME, never the raw key. The raw
    # key lives only in SecretStore → .env.
    llm["api_key_env"] = payload.api_key_env
    llm["base_url"] = payload.base_url
    llm["default_model"] = payload.default_model
    if payload.fallback_model:
        llm["fallback_model"] = payload.fallback_model


def _update_voice_asr(doc: tomlkit.TOMLDocument, payload: VoiceASRRequest) -> None:
    """Apply ASR-step fields. Also flips voice.enabled = true (per Q3)."""
    if "voice" not in doc:
        doc["voice"] = tomlkit.table()
    voice = doc["voice"]
    voice["enabled"] = True
    if "asr" not in voice:
        voice["asr"] = tomlkit.table()
    asr = voice["asr"]
    asr["backend"] = payload.backend
    asr["model_size"] = payload.model_size
    if payload.model_path:
        asr["model_path"] = payload.model_path
    asr["language"] = payload.language
    asr["device"] = payload.device
    asr["compute_type"] = payload.compute_type


def _update_voice_tts(doc: tomlkit.TOMLDocument, payload: VoiceTTSRequest) -> None:
    """Apply TTS-step fields."""
    if "voice" not in doc:
        doc["voice"] = tomlkit.table()
    voice = doc["voice"]
    voice["enabled"] = True
    if "tts" not in voice:
        voice["tts"] = tomlkit.table()
    tts = voice["tts"]
    tts["backend"] = payload.backend
    tts["voice"] = payload.voice
    tts["rate"] = payload.rate
    tts["pitch"] = payload.pitch
    tts["volume"] = payload.volume


def _update_theme(doc: tomlkit.TOMLDocument, theme: str) -> None:
    """Apply Theme-step fields. Stores in [user].default_theme."""
    if "user" not in doc:
        doc["user"] = tomlkit.table()
    user = doc["user"]
    user["default_theme"] = theme


def _update_tailscale(
    doc: tomlkit.TOMLDocument, hostname: str, require_tailscale: bool
) -> None:
    """Apply Tailscale-step fields. Stores in [server]."""
    if "server" not in doc:
        doc["server"] = tomlkit.table()
    server = doc["server"]
    server["tailscale_hostname"] = hostname
    server["require_tailscale"] = require_tailscale


# ---------------------------------------------------------------------------
# LLM connection test
# ---------------------------------------------------------------------------


async def _test_llm_connection(
    base_url: str, api_key: str, model: str
) -> tuple[bool, str | None]:
    """Ping the LLM provider's /v1/models endpoint.

    Returns ``(ok, error_code)``. The OpenAI-compatible /v1/models
    endpoint requires a valid key and is much cheaper than a chat
    completion; it returns 200 with a JSON list on success, 401 on a
    bad key, 403 on a banned key, etc.

    Implementation note: we use raw httpx (not the OpenAI SDK) so the
    test path doesn't pay the SDK's setup cost and so we can intercept
    any 4xx/5xx with a uniform error code.
    """
    url = base_url.rstrip("/") + "/models"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
            resp = await client.get(url, headers=headers)
    except httpx.TimeoutException:
        return False, "timeout"
    except httpx.HTTPError as e:
        return False, f"network_error:{type(e).__name__}"

    if resp.status_code == 200:
        return True, None
    if resp.status_code in (401, 403):
        return False, "invalid_key"
    if resp.status_code == 404:
        # Some providers don't expose /v1/models. Fall back to a
        # minimal /v1/chat/completions with max_tokens=1.
        return await _test_llm_chat_minimal(base_url, api_key, model)
    if resp.status_code == 429:
        return False, "rate_limited"
    return False, f"http_{resp.status_code}"


async def _test_llm_chat_minimal(
    base_url: str, api_key: str, model: str
) -> tuple[bool, str | None]:
    """Fallback test: a 1-token chat completion. Used if /v1/models 404s."""
    url = base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": model,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 1,
        "temperature": 0,
    }
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
            resp = await client.post(url, headers=headers, json=body)
    except httpx.TimeoutException:
        return False, "timeout"
    except httpx.HTTPError as e:
        return False, f"network_error:{type(e).__name__}"
    if resp.status_code == 200:
        return True, None
    if resp.status_code in (401, 403):
        return False, "invalid_key"
    if resp.status_code == 429:
        return False, "rate_limited"
    return False, f"http_{resp.status_code}"


# ---------------------------------------------------------------------------
# Voice model validation
# ---------------------------------------------------------------------------


def _validate_asr_model_path(
    model_path: str, model_size: str
) -> tuple[bool, str | None]:
    """Validate that the ASR model is loadable.

    - If ``model_path`` is set, the directory must exist.
    - Otherwise we trust ``model_size`` (whisper will download on first
      run if the size isn't cached). We just confirm size is valid.
    """
    if model_path:
        p = Path(model_path).expanduser()
        if not p.exists():
            return False, f"model_path does not exist: {model_path}"
        if not p.is_dir():
            return False, f"model_path is not a directory: {model_path}"
    if not model_path and not model_size:
        return False, "either model_path or model_size must be set"
    return True, None


def _validate_tts_voice(voice: str) -> tuple[bool, str | None]:
    """TTS voice is just a string; we sanity-check the format (non-empty)."""
    if not voice or not voice.strip():
        return False, "voice must be non-empty"
    return True, None


# ---------------------------------------------------------------------------
# Smoke test (text + voice round-trip)
# ---------------------------------------------------------------------------


async def _run_smoke_text() -> tuple[bool, str | None]:
    """Send a single ping to the LLM and confirm a non-empty reply."""
    # Reload config fresh — the wizard may have just written toml and
    # we don't want to read the pre-wizard cached values.
    from app.core.config import load_config

    cfg = load_config(get_config().home)
    api_key = cfg.llm.api_key or os.environ.get(cfg.llm.api_key_env, "")
    if not api_key:
        return False, "no_api_key"
    url = cfg.llm.base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": cfg.llm.default_model,
        "messages": [{"role": "user", "content": "Reply with the single word: PONG"}],
        "max_tokens": 8,
        "temperature": 0,
    }
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            resp = await client.post(url, headers=headers, json=body)
    except httpx.TimeoutException:
        return False, "timeout"
    except httpx.HTTPError as e:
        return False, f"network_error:{type(e).__name__}"
    if resp.status_code != 200:
        return False, f"http_{resp.status_code}"
    try:
        data = resp.json()
        content = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )
    except (ValueError, KeyError, IndexError):
        return False, "bad_response"
    if not content:
        return False, "empty_response"
    return True, None


async def _run_smoke_voice() -> tuple[bool, str | None]:
    """Best-effort voice round-trip probe.

    The M13 ticket says "text chat round-trip + (optional) voice
    round-trip". For v0.1 we treat voice smoke as a config-validation
    check: confirm the ASR model is on disk (or marked auto-download)
    and TTS has a valid voice. We do NOT actually pipe audio through
    the full VAD+ASR+TTS pipeline — that would require a real mic and
    the live2d voice layer to be mounted.

    Returns ``(ok, error_code)``. ``ok=True`` means "voice is wired
    enough that the dashboard can mount the WS layer".
    """
    from app.core.config import load_config

    cfg = load_config(get_config().home)
    if not cfg.voice.enabled:
        return False, "voice_disabled"
    if not cfg.voice.asr.backend or not cfg.voice.asr.model_size:
        return False, "asr_not_configured"
    if not cfg.voice.tts.voice:
        return False, "tts_not_configured"
    # If a model_path is set, confirm the directory exists.
    if cfg.voice.asr.model_path:
        p = Path(cfg.voice.asr.model_path).expanduser()
        if not p.exists():
            return False, "asr_model_path_missing"
    return True, None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


def _get_halo_home() -> Path:
    """Return the configured HALO_HOME (post-config)."""
    return Path(get_config().home)


def _toml_write_err(e: Exception) -> dict[str, Any]:
    """Standard error response for TOML write failures."""
    return _err_payload(
        errors=[
            {
                "field": "config",
                "code": "toml_write_failed",
                "message": str(e),
            }
        ]
    )


def _step_payload(state: SetupState) -> dict[str, Any]:
    """Common response shape: ``{ok, next_step, status, current_step, ...}``."""
    return {
        "ok": True,
        "next_step": state.current_step,
        "status": state.status,
        "current_step": state.current_step,
        "completed_steps": state.completed_steps,
        "started_at": state.started_at,
        "finished_at": state.finished_at,
        "skipped": state.skipped,
        "reason": state.reason,
    }


def _err_payload(
    errors: list[dict[str, str]],
    current_step: int = 1,
    status: str = "needs_setup",
) -> dict[str, Any]:
    """Error response shape: ``{ok: false, next_step, errors: [...]}``."""
    return {
        "ok": False,
        "next_step": current_step,
        "status": status,
        "errors": errors,
    }


@router.get("/state", response_model=dict[str, Any])
async def get_setup_state() -> dict[str, Any]:
    """GET /api/setup/state — current state (auto-detected).

    The persisted state file is the source of truth for "what step
    was the user on". The live detection is the source of truth for
    "is the wizard even needed right now". We combine the two:

    - status: trust detection (it knows if the user deleted config.toml)
    - current_step: prefer the detected step when the user hasn't
      started yet (no started_at) OR when their persisted state
      doesn't match the detected status. Otherwise trust the
      persisted step (where they left off).
    - completed_steps, started_at, finished_at, skipped: from persisted
    - reason: prefer detection's reason (more diagnostic)
    """
    home = _get_halo_home()
    persisted = load_setup_state(home)
    detected = compute_setup_state(home)
    # If the user hasn't actually started yet (no started_at, no
    # completed steps), the detected state is the redirect target.
    user_has_started = bool(
        persisted.started_at or persisted.completed_steps or persisted.finished_at
    )
    use_detected_step = (
        detected.status != persisted.status
        or not user_has_started
    )
    combined = SetupState(
        version=persisted.version,
        status=detected.status,
        current_step=(
            detected.current_step if use_detected_step else persisted.current_step
        ),
        completed_steps=persisted.completed_steps,
        started_at=persisted.started_at,
        finished_at=persisted.finished_at,
        skipped=persisted.skipped,
        reason=detected.reason,
    )
    return {
        "status": combined.status,
        "current_step": combined.current_step,
        "completed_steps": combined.completed_steps,
        "started_at": combined.started_at,
        "finished_at": combined.finished_at,
        "skipped": combined.skipped,
        "reason": combined.reason,
    }


@router.post("/start", response_model=dict[str, Any])
async def post_setup_start() -> dict[str, Any]:
    """POST /api/setup/start — begin the wizard, set started_at."""
    home = _get_halo_home()
    state = load_setup_state(home)
    state.started_at = state.started_at or now_iso()
    state.skipped = False
    state.finished_at = None
    state.current_step = 1
    state.completed_steps = []
    state.reason = ""
    save_setup_state(home, state)
    return _step_payload(state)


@router.post("/llm", response_model=dict[str, Any])
async def post_setup_llm(payload: LLMSetupRequest) -> dict[str, Any]:
    """POST /api/setup/llm — save LLM config, test connection.

    Flow (per M13 §"secrets_store contract"):
    1. Test the key against the provider's /v1/models endpoint.
    2. On 200, write the raw key to SecretStore (which atomically
       persists to $HALO_HOME/.env with 0600 perms).
    3. Update config.toml with the provider/base_url/model/env_var_name.
    4. Mark step 2 complete + advance to step 3.

    NEVER echoes the raw key in the response. NEVER writes the raw
    key to config.toml.
    """
    # 1. Test connection FIRST. If the key is bad, we never touch
    # the secret store or TOML — the user can fix the key and retry.
    ok, err_code = await _test_llm_connection(
        payload.base_url, payload.api_key, payload.default_model
    )
    if not ok:
        logger.info(
            f"setup/llm: test_connection failed "
            f"(provider={payload.provider}, err={err_code})"
        )
        return _err_payload(
            errors=[
                {
                    "field": "api_key",
                    "code": err_code or "unknown",
                    "message": _llm_error_message(err_code),
                }
            ]
        )

    # 2. Write raw key to SecretStore. We use MINIMAX_API_KEY as the
    # canonical env-var name (the only one SecretStore currently
    # allows). For non-minimax providers we still store under
    # MINIMAX_API_KEY for v0.1 simplicity — the actual env-var that
    # gets read at config-load time is the one the user passes in
    # api_key_env. (We don't add a new SecretStore key per provider
    # in M13 v0.1 — that's an M13.x follow-up.)
    try:
        store = get_secret_store()
        env_name = payload.api_key_env
        if env_name not in SECRET_KEYS:
            # Coerce to MINIMAX_API_KEY for v0.1 — the user-supplied
            # env var name is still recorded in TOML via api_key_env,
            # but the runtime secret lives under MINIMAX_API_KEY.
            logger.info(
                f"setup/llm: env var {env_name!r} not in SECRET_KEYS; "
                f"storing under MINIMAX_API_KEY instead"
            )
            env_name = "MINIMAX_API_KEY"
        store.set(env_name, payload.api_key)
        if store.is_config_cache_dirty():
            store.invalidate_config_cache()
    except ValueError as e:
        # Invalid key name, empty value, etc.
        return _err_payload(
            errors=[
                {
                    "field": "api_key",
                    "code": "secrets_store_error",
                    "message": str(e),
                }
            ]
        )

    # 3. Update config.toml. We write the env var name (never the key).
    home = _get_halo_home()
    toml_path = _toml_path(home)
    try:
        doc, _ = _load_toml_doc(toml_path)
        _update_llm(doc, payload)
        _write_toml_doc(toml_path, doc)
    except Exception as e:
        logger.exception("setup/llm: failed to write config.toml")
        return _toml_write_err(e)

    # 4. Mark step 2 done; advance to step 3 (voice ASR).
    state = load_setup_state(home)
    if 2 not in state.completed_steps:
        state.completed_steps.append(2)
    state.current_step = 3
    state.reason = ""
    save_setup_state(home, state)

    payload_out = _step_payload(state)
    payload_out["stored_env"] = env_name
    return payload_out


def _llm_error_message(err_code: str | None) -> str:
    """Map an LLM-test error code to a user-friendly message."""
    if not err_code:
        return "Connection failed"
    if err_code == "invalid_key":
        return "API key is invalid (provider returned 401/403)"
    if err_code == "timeout":
        return "Connection timed out — check the base_url"
    if err_code == "rate_limited":
        return "Provider rate-limited the request (429)"
    if err_code.startswith("network_error"):
        return f"Network error: {err_code}"
    if err_code.startswith("http_"):
        return f"Provider returned {err_code}"
    return f"Test failed: {err_code}"


@router.post("/voice-asr", response_model=dict[str, Any])
async def post_setup_voice_asr(payload: VoiceASRRequest) -> dict[str, Any]:
    """POST /api/setup/voice-asr — save ASR config, validate model."""
    ok, err = _validate_asr_model_path(payload.model_path, payload.model_size)
    if not ok:
        return _err_payload(
            errors=[
                {
                    "field": "model_path" if payload.model_path else "model_size",
                    "code": "model_invalid",
                    "message": err or "ASR model invalid",
                }
            ]
        )

    home = _get_halo_home()
    toml_path = _toml_path(home)
    try:
        doc, _ = _load_toml_doc(toml_path)
        _update_voice_asr(doc, payload)
        _write_toml_doc(toml_path, doc)
    except Exception as e:
        logger.exception("setup/voice-asr: failed to write config.toml")
        return _toml_write_err(e)

    state = load_setup_state(home)
    if 3 not in state.completed_steps:
        state.completed_steps.append(3)
    state.current_step = 4
    state.reason = ""
    save_setup_state(home, state)
    return _step_payload(state)


@router.post("/voice-tts", response_model=dict[str, Any])
async def post_setup_voice_tts(payload: VoiceTTSRequest) -> dict[str, Any]:
    """POST /api/setup/voice-tts — save TTS config."""
    ok, err = _validate_tts_voice(payload.voice)
    if not ok:
        return _err_payload(
            errors=[
                {
                    "field": "voice",
                    "code": "voice_invalid",
                    "message": err or "TTS voice invalid",
                }
            ]
        )

    home = _get_halo_home()
    toml_path = _toml_path(home)
    try:
        doc, _ = _load_toml_doc(toml_path)
        _update_voice_tts(doc, payload)
        _write_toml_doc(toml_path, doc)
    except Exception as e:
        logger.exception("setup/voice-tts: failed to write config.toml")
        return _toml_write_err(e)

    state = load_setup_state(home)
    if 4 not in state.completed_steps:
        state.completed_steps.append(4)
    state.current_step = 5
    state.reason = ""
    save_setup_state(home, state)
    return _step_payload(state)


@router.post("/theme", response_model=dict[str, Any])
async def post_setup_theme(payload: ThemeRequest) -> dict[str, Any]:
    """POST /api/setup/theme — save theme pick.

    Default is NT-D (gundam-ntd). Wizard sends one of the 8 long-form
    IDs from ALLOWED_THEMES. We just store in [user].default_theme.
    """
    home = _get_halo_home()
    toml_path = _toml_path(home)
    try:
        doc, _ = _load_toml_doc(toml_path)
        _update_theme(doc, payload.theme)
        _write_toml_doc(toml_path, doc)
    except Exception as e:
        logger.exception("setup/theme: failed to write config.toml")
        return _toml_write_err(e)

    state = load_setup_state(home)
    if 5 not in state.completed_steps:
        state.completed_steps.append(5)
    state.current_step = 6
    state.reason = ""
    save_setup_state(home, state)
    return _step_payload(state)


@router.post("/tailscale", response_model=dict[str, Any])
async def post_setup_tailscale(payload: TailscaleRequest) -> dict[str, Any]:
    """POST /api/setup/tailscale — save hostname, test reachability.

    Per M13 Q1, the wizard does NOT auto-install Tailscale. It pings
    the hostname to confirm reachability, and if the ping fails the
    user is sent to the Tailscale install page.
    """
    reachable = is_tailscale_reachable() if payload.test_reachability else None

    home = _get_halo_home()
    toml_path = _toml_path(home)
    try:
        doc, _ = _load_toml_doc(toml_path)
        _update_tailscale(doc, payload.hostname, payload.require_tailscale)
        _write_toml_doc(toml_path, doc)
    except Exception as e:
        logger.exception("setup/tailscale: failed to write config.toml")
        return _toml_write_err(e)

    state = load_setup_state(home)
    if 6 not in state.completed_steps:
        state.completed_steps.append(6)
    # Tailscale is step 6. The next step is 7 (smoke) UNLESS smoke
    # is also the last step.
    state.current_step = 7
    state.reason = ""
    save_setup_state(home, state)
    out = _step_payload(state)
    out["reachable"] = reachable
    return out


@router.post("/smoke", response_model=dict[str, Any])
async def post_setup_smoke() -> dict[str, Any]:
    """POST /api/setup/smoke — run end-to-end smoke test.

    Two checks: text chat round-trip + voice round-trip. Each is
    reported independently. The wizard auto-advances to the success
    screen on success (no Next button on this step, per M13).
    """
    text_ok, text_err = await _run_smoke_text()
    voice_ok, voice_err = await _run_smoke_voice()

    home = _get_halo_home()
    state = load_setup_state(home)

    if text_ok and voice_ok:
        # Don't mark step 7 as completed here — finish() does that,
        # because the user might fail smoke and want to retry without
        # leaving the wizard. We just keep current_step=7.
        state.current_step = 7
        state.reason = ""
        save_setup_state(home, state)
        return {
            **_step_payload(state),
            "text_ok": True,
            "voice_ok": True,
            "text_error": None,
            "voice_error": None,
        }

    # One or both failed — surface the errors.
    errors: list[dict[str, str]] = []
    if not text_ok:
        errors.append(
            {
                "field": "llm",
                "code": text_err or "unknown",
                "message": f"Text chat round-trip failed: {text_err}",
            }
        )
    if not voice_ok:
        errors.append(
            {
                "field": "voice",
                "code": voice_err or "unknown",
                "message": f"Voice round-trip failed: {voice_err}",
            }
        )
    return {
        **_err_payload(errors, current_step=7),
        "text_ok": text_ok,
        "voice_ok": voice_ok,
        "text_error": text_err,
        "voice_error": voice_err,
    }


@router.post("/finish", response_model=dict[str, Any])
async def post_setup_finish() -> dict[str, Any]:
    """POST /api/setup/finish — mark the wizard finished.

    Per the "Required vs optional" table, finish is blocked until
    steps 2/3/4 have a value (LLM key, voice ASR, voice TTS) and
    step 7 passes. We enforce that with compute_setup_state() — if
    it's not "ready", we 409.
    """
    home = _get_halo_home()
    # Re-detect: if the config isn't actually valid, refuse to finish.
    detected = compute_setup_state(home)
    if detected.status != "ready":
        return _err_payload(
            errors=[
                {
                    "field": "wizard",
                    "code": "incomplete",
                    "message": f"wizard not complete: {detected.reason}",
                }
            ],
            current_step=detected.current_step,
        )

    state = load_setup_state(home)
    if 7 not in state.completed_steps:
        state.completed_steps.append(7)
    state.finished_at = now_iso()
    state.status = "ready"
    state.current_step = 7
    state.skipped = False
    state.reason = "wizard finished"
    save_setup_state(home, state)
    return {
        **_step_payload(state),
        "redirect": "/",
    }


@router.post("/skip", response_model=dict[str, Any])
async def post_setup_skip() -> dict[str, Any]:
    """POST /api/setup/skip — mark the wizard skipped (advanced).

    Per M13 Q1, skip does NOT reach "ready". It writes a minimal config
    (just enough to not crash) and marks the wizard as skipped. The
    dashboard will still show "missing fields" warnings for any step
    the user didn't complete.
    """
    home = _get_halo_home()
    toml_path = _toml_path(home)
    # Ensure a config.toml exists (write the absolute minimum).
    if not toml_path.exists():
        try:
            doc = tomlkit.document()
            # Defaults that are non-fatal: empty llm, voice off, etc.
            # The user can fill these in later via Settings.
            doc["user"] = tomlkit.table()
            doc["user"]["name"] = "User"
            doc["user"]["default_theme"] = "gundam-ntd"
            doc["llm"] = tomlkit.table()
            doc["llm"]["provider"] = "minimax"
            doc["llm"]["api_key_env"] = "MINIMAX_API_KEY"
            doc["llm"]["base_url"] = "https://api.minimax.io/v1"
            doc["llm"]["default_model"] = "MiniMax-M2"
            doc["server"] = tomlkit.table()
            doc["server"]["port"] = 8765
            doc["server"]["require_tailscale"] = False
            doc["server"]["tailscale_hostname"] = "gundam-halo"
            doc["voice"] = tomlkit.table()
            doc["voice"]["enabled"] = False
            _write_toml_doc(toml_path, doc)
        except Exception as e:
            logger.exception("setup/skip: failed to write minimal config.toml")
            return _err_payload(
                errors=[
                    {
                        "field": "config",
                        "code": "toml_write_failed",
                        "message": str(e),
                    }
                ]
            )

    state = load_setup_state(home)
    state.skipped = True
    state.finished_at = now_iso()
    state.status = "needs_setup"  # per Q1: skip does NOT reach "ready"
    state.reason = "skipped by user (advanced)"
    save_setup_state(home, state)
    return {
        **_step_payload(state),
        "redirect": "/",
    }


@router.post("/reset", response_model=dict[str, Any])
async def post_setup_reset() -> dict[str, Any]:
    """POST /api/setup/reset — wipe state, restart at step 1.

    Per M13 §"Reset wizard", this keeps config.toml intact. The
    user can edit it manually; the wizard just starts over.
    """
    home = _get_halo_home()
    new_state = reset_setup_state(home)
    return _step_payload(new_state)


__all__ = [
    "router",
    # Pydantic request models (re-exported for tests)
    "LLMSetupRequest",
    "VoiceASRRequest",
    "VoiceTTSRequest",
    "ThemeRequest",
    "TailscaleRequest",
    "StartRequest",
    "ResetRequest",
]

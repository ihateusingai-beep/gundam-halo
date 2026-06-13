"""Setup state — persistence + detection for the M13 first-run wizard.

This module owns:

1. ``SetupState`` — a dataclass for the JSON file at
   ``~/.gundam-halo/setup_state.json``.
2. ``compute_setup_state(home)`` — derive the wizard's current state
   from the live ``Config`` + filesystem.
3. ``is_tailscale_reachable()`` — a small helper that shells out to
   ``tailscale ping`` (returns False on missing tool, never raises).
4. ``load_setup_state(home)`` / ``save_setup_state(home, state)`` —
   atomic read + write of the state file.

The state file is intentionally separate from ``config.toml``:
``config.toml`` is the *user's* configuration; ``setup_state.json`` is
the *wizard's* view of "are we done onboarding?".

Design notes
------------
- The state file is the source of truth for "what step is the user on
  + did they skip / finish". The TOML config is the source of truth for
  "what values did they pick".
- "Needs setup" is detected by ``compute_setup_state()`` and may
  disagree with what's in the state file (e.g. user manually deleted
  ``config.toml`` after finishing). When they disagree, the detected
  state wins.
- Voice is REQUIRED to finish (per M13 Q3, locked 2026-06-13). The
  wizard defaults ``voice.enabled = true`` and won't let the user
  finish without ASR + TTS configured.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
import threading
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Filename of the wizard state file (sibling of config.toml in $HALO_HOME).
STATE_FILENAME = "setup_state.json"

#: Current schema version. Bump when the on-disk shape changes.
STATE_VERSION = 1

#: The 8 frontend theme IDs (long form). Kept here as the single source
#: of truth so the wizard's "pick a theme" step rejects anything else.
#: See ``frontend/src/lib/theme.ts`` and ``live2d_factory.available_themes()``.
ALLOWED_THEMES: list[str] = [
    "gundam-ntd",          # default (Unicorn psychoframe — most iconic)
    "gundam-god",
    "gundam-seed",
    "gundam-crossbone",
    "gundam-destiny",
    "gundam-halo",
    "gundam-ntd-green",
    "gundam-cartoon",
]

#: The 4 LLM providers the wizard knows how to onboard. Other providers
#: are out-of-scope for M13 v0.1 (advanced users can edit config.toml
#: by hand).
ALLOWED_LLM_PROVIDERS: list[str] = ["minimax", "openai", "ollama", "anthropic"]

#: The 2 ASR backends wired in v1.
ALLOWED_ASR_BACKENDS: list[str] = ["whisper_local", "sherpa"]

#: The 3 TTS backends the wizard exposes.
ALLOWED_TTS_BACKENDS: list[str] = ["edge", "openai", "cosyvoice"]


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------


@dataclass
class SetupState:
    """The on-disk wizard state.

    JSON file lives at ``$HALO_HOME/setup_state.json``.

    Fields
    ------
    version
        Schema version. Bump on incompatible changes.
    status
        ``"needs_setup"`` if the wizard should be shown, ``"ready"`` if
        the user has finished or skipped.
    current_step
        1-7 inclusive. Where the user is in the wizard.
    completed_steps
        Sorted list of steps the user has finished. Persisted so we
        can show "✓ LLM" checkmarks on the progress bar.
    started_at
        ISO-8601 string. Set on ``POST /api/setup/start``.
    finished_at
        ISO-8601 string. Set on ``POST /api/setup/finish``.
    skipped
        True if the user clicked Skip. Per M13 Q1, the dashboard
        still shows "missing fields" warnings but the wizard itself
        goes away.
    reason
        Diagnostic string for the dashboard's "why is the wizard
        showing?" tooltip. E.g. ``"no config.toml"`` or
        ``"missing: ['llm.api_key', 'voice.asr.model_path']"``.
    """

    version: int = STATE_VERSION
    status: str = "needs_setup"
    current_step: int = 1
    completed_steps: list[int] = field(default_factory=list)
    started_at: str | None = None
    finished_at: str | None = None
    skipped: bool = False
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe dict (matches the on-disk shape 1:1)."""
        d = asdict(self)
        # asdict gives us a regular list for completed_steps; ensure sorted.
        d["completed_steps"] = sorted(set(self.completed_steps))
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SetupState:
        """Build a SetupState from a parsed JSON dict (defensive)."""
        if not isinstance(data, dict):
            return cls()

        def _safe_int(v: Any, default: int) -> int:
            try:
                if v is None or v == "":
                    return default
                return int(v)
            except (TypeError, ValueError):
                return default

        def _safe_str_or_none(v: Any) -> str | None:
            if isinstance(v, (str, type(None))):
                return v
            return None

        completed = data.get("completed_steps", []) or []
        if not isinstance(completed, list):
            completed = []
        # Coerce every entry to int; drop anything unparseable.
        clean_completed: list[int] = []
        for x in completed:
            try:
                if x is None or x == "":
                    continue
                clean_completed.append(int(x))
            except (TypeError, ValueError):
                continue
        return cls(
            version=_safe_int(data.get("version"), STATE_VERSION),
            status=str(data.get("status", "needs_setup") or "needs_setup"),
            current_step=_safe_int(data.get("current_step"), 1),
            completed_steps=clean_completed,
            started_at=_safe_str_or_none(data.get("started_at")),
            finished_at=_safe_str_or_none(data.get("finished_at")),
            skipped=bool(data.get("skipped", False)),
            reason=str(data.get("reason", "") or ""),
        )


# ---------------------------------------------------------------------------
# Detection — "where should the wizard be?"
# ---------------------------------------------------------------------------


def _step_for_field(missing: str) -> int:
    """Map a missing-field name to the wizard step that fixes it.

    Mirrors the table in M13 §"Implementation impact (refined)".
    """
    if missing.startswith("llm."):
        return 2
    if missing.startswith("voice.asr") or missing == "voice.enabled":
        return 3
    if missing.startswith("voice.tts"):
        return 4
    if missing.startswith("server.tailscale") or missing == "server.require_tailscale":
        return 6
    return 1  # fallback


def is_tailscale_reachable() -> bool:
    """Return True if ``tailscale ping`` can reach the local node.

    Tries ``tailscale ping <hostname>`` and interprets exit code 0 as
    reachable. If the binary is missing or errors, return False — the
    wizard should not block the user from finishing on a non-Tailscale
    machine, but should also not lie about reachability.

    Implementation:
    - Looks for ``tailscale`` on $PATH
    - Runs ``tailscale ping gundam-halo`` with a 3-second timeout
    - Returns True on exit 0, False otherwise (including binary missing)

    This function NEVER raises — it always returns a bool.
    """
    tailscale_bin = shutil.which("tailscale")
    if not tailscale_bin:
        return False
    try:
        result = subprocess.run(
            [tailscale_bin, "ping", "--timeout=3s", "gundam-halo"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        logger.debug(f"tailscale ping failed: {e}")
        return False


def _has_voice_model(cfg) -> bool:
    """Return True if the voice ASR model is configured to load something.

    Per the M13 detection rules: voice is REQUIRED to finish. A voice
    model is considered "configured" if either ``voice.asr.model_path``
    is non-empty (HF fine-tune path) OR ``voice.asr.model_size`` is a
    non-empty string (the whisper_local default). The ``model_path``
    is checked first because it takes precedence in the actual loader.
    """
    if not cfg.voice.enabled:
        return False
    if cfg.voice.asr.model_path:
        return True
    if cfg.voice.asr.model_size:
        return True
    return False


def compute_setup_state(home: Path) -> SetupState:
    """Detect the current setup state by inspecting $HALO_HOME.

    Algorithm (mirrors M13 §"Detection logic"):
    1. If ``config.toml`` doesn't exist → needs_setup, step 1
    2. Load config; for each required field, append to ``missing``
    3. If ``missing`` non-empty → needs_setup, step_for(missing[0])
    4. Else → ready
    """
    home = Path(home)
    cfg_path = home / "config.toml"
    if not cfg_path.exists():
        return SetupState(
            status="needs_setup",
            current_step=1,
            reason="no config.toml",
        )

    # Late import: app.core.config pulls in the engine registry, which
    # we want to keep optional for the test suite (tests can construct
    # a Config directly without booting the whole app).
    from app.core.config import load_config

    try:
        cfg = load_config(home)
    except Exception as e:
        # Malformed TOML or any other parse failure → treat as needs_setup
        logger.warning(f"load_config failed in compute_setup_state: {e}")
        return SetupState(
            status="needs_setup",
            current_step=1,
            reason=f"config parse error: {e}",
        )

    missing: list[str] = []

    # --- LLM ---------------------------------------------------------------
    # LLM is REQUIRED. Either the secret_store has the key OR the
    # api_key_env env var is set in the current process.
    api_key_env_name = (
        getattr(cfg.llm, "api_key_env", "MINIMAX_API_KEY") or "MINIMAX_API_KEY"
    )
    has_api_key = bool(cfg.llm.api_key) or bool(os.environ.get(api_key_env_name, ""))
    if not has_api_key:
        missing.append("llm.api_key")

    # --- Voice -------------------------------------------------------------
    # Per M13 Q3, voice is REQUIRED to finish. The wizard defaults
    # voice.enabled = true and steps 3+4 are mandatory.
    if not cfg.voice.enabled:
        missing.append("voice.enabled")
    elif not _has_voice_model(cfg):
        missing.append("voice.asr.model_path")

    # TTS voice is also required (it's just a string field; we check
    # non-empty to make sure the wizard or config has picked a voice).
    if cfg.voice.enabled and not cfg.voice.tts.voice:
        missing.append("voice.tts.voice")

    # --- Tailscale ---------------------------------------------------------
    # Per the spec, Tailscale is OPTIONAL. We only flag it as missing
    # if the user has explicitly enabled require_tailscale in config
    # AND we can't actually reach the gateway.
    if cfg.server.require_tailscale and not is_tailscale_reachable():
        missing.append("server.tailscale")

    if missing:
        return SetupState(
            status="needs_setup",
            current_step=_step_for_field(missing[0]),
            reason=f"missing: {missing}",
        )
    return SetupState(status="ready", reason="all required fields present")


# ---------------------------------------------------------------------------
# Persistence — atomic load/save
# ---------------------------------------------------------------------------


_state_lock = threading.Lock()


def _state_path(home: Path) -> Path:
    return Path(home) / STATE_FILENAME


def load_setup_state(home: Path) -> SetupState:
    """Load setup_state.json from $HALO_HOME.

    Returns a default ``SetupState(needs_setup, step=1)`` if the file
    doesn't exist, can't be read, or contains malformed JSON. The
    wizard should never crash on a missing state file.
    """
    path = _state_path(home)
    if not path.exists():
        return SetupState(
            status="needs_setup", current_step=1, reason="no setup_state.json"
        )
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return SetupState.from_dict(data)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Failed to load setup_state.json: {e}")
        return SetupState(
            status="needs_setup",
            current_step=1,
            reason=f"state file unreadable: {e}",
        )


def save_setup_state(home: Path, state: SetupState) -> Path:
    """Atomically write *state* to $HALO_HOME/setup_state.json.

    Atomic write = temp file in the same directory + os.replace().
    Survives a crash mid-write (the previous good state stays).

    Returns the path that was written.
    """
    home = Path(home)
    home.mkdir(parents=True, exist_ok=True)
    target = _state_path(home)

    body = json.dumps(state.to_dict(), indent=2, sort_keys=False)
    # Mkstemp + os.replace gives us atomic replace. We use the same
    # directory so the rename is a single inode swap on the same FS.
    fd, tmp_path = tempfile.mkstemp(prefix=".setup_state.", dir=home, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(body)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                # fsync isn't supported on every FS (e.g. some FUSE
                # mounts); skip silently rather than fail the write.
                pass
        os.replace(tmp_path, target)
    except Exception:
        # Best-effort cleanup of the tmp file on failure.
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    with _state_lock:
        logger.debug(
            f"Saved setup_state to {target} "
            f"(status={state.status}, step={state.current_step})"
        )
    return target


def reset_setup_state(home: Path) -> SetupState:
    """Delete setup_state.json and return a fresh default state.

    The companion of "Reset wizard" — wipes progress but leaves
    config.toml intact. Per M13 §"Reset wizard", this is the spec.
    """
    path = _state_path(home)
    if path.exists():
        try:
            path.unlink()
        except OSError as e:
            logger.warning(f"Failed to delete {path}: {e}")
    fresh = SetupState(status="needs_setup", current_step=1, reason="reset by user")
    # Write the fresh state so the next GET /api/setup/state has a
    # concrete file to return (and any inotify watchers fire).
    save_setup_state(home, fresh)
    return fresh


# ---------------------------------------------------------------------------
# Convenience — ISO timestamps
# ---------------------------------------------------------------------------


def now_iso() -> str:
    """Current UTC time as ISO-8601 string with explicit timezone."""
    return datetime.now(tz=UTC).isoformat()


__all__ = [
    "ALLOWED_LLM_PROVIDERS",
    "ALLOWED_ASR_BACKENDS",
    "ALLOWED_TTS_BACKENDS",
    "ALLOWED_THEMES",
    "STATE_FILENAME",
    "STATE_VERSION",
    "SetupState",
    "compute_setup_state",
    "is_tailscale_reachable",
    "load_setup_state",
    "now_iso",
    "reset_setup_state",
    "save_setup_state",
]

"""Voice restart coordination — process-local "did the last PUT
change the ASR engine / corrector?" flag.

Sprint 32 P1.1: extracted from `api/voice_ws.py`. The flag
(`_voice_restart_required`) and its accessors live here so the
WS route and the REST PUT endpoint can both update / read it
without one importing the other.

This is intentionally process-local and resets on backend
restart — which is the right semantic, because after a restart
the new value has been picked up by the voice WS pipeline
(via `app/core/restart.py::schedule_restart`).
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Process-local flag. Mutated by `set_restart_required` from
# `api/voice_config_api.py::put_voice_config` (set when the user
# actually changes asr_backend or asr_corrector; cleared when a
# subsequent PUT doesn't touch either field).
_voice_restart_required: bool = False


def get_restart_required() -> bool:
    """Return whether the most recent PUT change requires a
    backend restart to take effect (e.g. the user swapped the
    ASR engine). Read by `get_voice_config` so the dashboard
    can show a "restart required" banner."""
    return _voice_restart_required


# Back-compat alias — the pre-P1.1 voice_ws.py exposed a getter
# named `_voice_restart_required_flag()`. Some tests still call
# this name (and the older `voice_ws._voice_restart_required`
# module-level flag, which maps to the same `_voice_restart_required`
# binding here). Keep both spellings working.
_voice_restart_required_flag = get_restart_required


def set_restart_required(value: bool) -> None:
    """Update the restart-required flag.

    Args:
        value: True when the latest PUT touched the asr_backend
            or asr_corrector fields with a different value;
            False when the PUT didn't touch either (which also
            clears any stale banner from a prior change).
    """
    global _voice_restart_required
    _voice_restart_required = value


def schedule_restart_if_needed(
    *, restart_required: bool, reason: str
) -> bool:
    """Schedule a backend restart when `restart_required` is True.

    Mirrors the Sprint 19b behaviour: when the user changed the
    ASR engine or corrector, we schedule a self-restart in 5
    seconds so the new pipeline (FsmnVAD + chosen ASR + corrector)
    loads on the new process. The PUT response returns immediately;
    the 5s grace gives in-flight voice turns time to finish.

    Args:
        restart_required: whether the caller determined a restart
            is needed (e.g. asr_backend / asr_corrector changed).
        reason: a short label for logs / dashboard debugging.

    Returns:
        True when a restart was actually scheduled, False otherwise.
        False can mean either "no restart needed" or "scheduler
        failed to import" — callers should treat both as the
        dashboard flag being authoritative.
    """
    if not restart_required:
        # PUT did not change the ASR fields — clear any pending
        # restart so a previous scheduled restart is the only signal.
        try:
            from app.core.restart import _set_restart_scheduled

            _set_restart_scheduled(False, reason="non_asr_put")
        except ImportError:
            pass
        return False

    try:
        from app.core.restart import (
            _set_restart_scheduled,
            schedule_restart,
        )

        schedule_restart(delay_s=5.0, reason=reason)
        _set_restart_scheduled(True, reason=reason)
        return True
    except Exception as e:
        # Defensive: if the restart scheduler fails to import or
        # schedule, we still persist the config but surface the
        # error to the dashboard so the user can restart manually.
        logger.error(f"[restart_handler] failed to schedule restart: {e}")
        return False
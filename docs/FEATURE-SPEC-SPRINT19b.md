# Feature Spec — Sprint 19b: auto-restart on ASR / corrector change

> **Status:** DRAFT — user signed off via the Sprint 19
> scope acceptance. Implementation follows in this session.
> **Scope:** 1 day. Backend-only. Closes the explicit
> deferred follow-up from Sprint 18: the
> `restart_required: true` flag that `put_voice_config`
> returns when the user changes `asr_backend` or
> `asr_corrector` becomes **actionable** — the backend
> auto-restarts itself with a 5-second grace period so
> the new ASR engine / corrector takes effect without
> the user manually running `pkill -f 'uvicorn ...' &&
> uvicorn ...`.
> **Out of scope (deferred to 19c/19d):** Tauri always-on
> mic, Cantonese Whisper fine-tune, systemd / launchd
> supervisor (we use a simple in-process self-restart
> pattern that requires the user to launch the backend
> themselves).

---

## 0. Why this sprint exists

Sprint 18's Track B added the `asr_backend` +
`asr_corrector` radio groups to the Settings → Voice
tab, and the `restart_required` flag in
`put_voice_config` flips to `true` when the user changes
either field. The dashboard's "Restart required" banner
already surfaces this — but the user has to manually
copy the restart command (`pkill -f 'uvicorn
app.main:app' && uv run --project . uvicorn
app.main:app`) and run it themselves. Sprint 19b makes
this automatic: the backend restarts itself with a short
grace period so the user's workflow doesn't break.

## 1. Goals

1. **Auto-restart on ASR change.** When
   `put_voice_config` flips `restart_required = true`,
   the backend schedules a self-restart in 5 seconds and
   returns the response with a
   `restart_scheduled: true` field. The dashboard
   surfaces this so the user knows the system is
   reloading (no "did it work?" uncertainty).
2. **Graceful shutdown.** During the 5-second grace
   period, in-flight voice turns finish, WebSocket
   connections close cleanly, and an audit log entry is
   written. The current HTTP request that triggered the
   PUT returns successfully before the restart.
3. **Same command line.** The restart uses
   `os.execvp(sys.executable, sys.argv)` so the new
   process inherits the same CLI args (uvicorn target,
   host, port, log level). No process supervisor
   required — the new process reuses the existing PID.
4. **No-op for non-ASR changes.** If the user only
   changes `wake_phrases` or `strict_wake_phrase`,
   `restart_required` stays false and no restart is
   scheduled. The current Sprint 18 path is unchanged.
5. **Tested end-to-end.** A new test verifies the
   scheduled restart flag is set, the response includes
   `restart_scheduled: true`, and a unit test for the
   restart scheduler confirms the timing.

## 2. Out of scope (deferred)

- **19c**: Tauri always-on mic
- **19d**: Cantonese Whisper fine-tune
- **systemd / launchd supervisor** — Sprint 19b uses
  self-restart, which requires the user to launch the
  backend themselves (no daemon). A follow-up sprint
  can add a launchd plist / systemd unit if needed.
- **Restart on every config PUT** — only ASR / corrector
  changes trigger a restart. wake_phrases /
  strict_wake_phrase are runtime-tunable.
- **Rollback on bad restart** — if the new process
  crashes after restart, we don't auto-rollback. The
  user can edit config.toml to revert.

## 3. User-facing behavior

1. User opens Settings → Voice.
2. User changes ASR engine from `whisper_local` to
   `yuesub` and clicks Save.
3. The PUT request succeeds with 200 and
   `restart_scheduled: true`. The dashboard toast says
   "Voice settings saved. The backend is restarting in
   5 seconds with the new ASR engine. Please wait…".
4. After ~5 seconds, the WebSocket disconnects
   (`voice.turn_ended` with `reason: 'restarting'`).
5. Within 1-2 more seconds, the WebSocket reconnects
   automatically (the new process is up) with the yuesub
   engine active. The dashboard's "Restart required"
   banner clears.
6. Total user-perceived downtime: ~6-7 seconds.

## 4. Architecture

### 4.1 Restart trigger

`put_voice_config` in `backend/app/api/voice_ws.py`
already sets the in-process `_voice_restart_required`
flag when the user changes `asr_backend` or
`asr_corrector`. Sprint 19b adds a one-line call to
`schedule_restart(delay_s=5.0)` in the same branch.

```python
# In put_voice_config, after the if restart_required:
# block that sets _voice_restart_required = True
if restart_required:
    _voice_restart_required = True
    schedule_restart(delay_s=5.0, reason="asr_config_change")
```

### 4.2 Restart scheduler

A new module `backend/app/core/restart.py` owns the
scheduling:

```python
import asyncio
import logging
import os
import sys
from typing import Optional

logger = logging.getLogger(__name__)


def schedule_restart(delay_s: float = 5.0, reason: str = "") -> None:
    """Schedule a self-restart in `delay_s` seconds.

    Uses `os.execvp(sys.executable, sys.argv)` so the new
    process inherits the same CLI args. The current PID
    is preserved (exec replaces the process image, not
    fork-and-exec).
    """
    async def _do_restart():
        logger.info(
            f"[halo.restart] scheduling self-restart in "
            f"{delay_s}s: reason={reason!r}"
        )
        try:
            await asyncio.sleep(delay_s)
        except asyncio.CancelledError:
            logger.info("[halo.restart] restart cancelled")
            return
        # Write audit log entry before exec (so it lands
        # on disk; the new process may not have time to
        # write it).
        try:
            from app.core.audit import write_audit
            write_audit(
                event="backend_restart",
                details={"reason": reason, "delay_s": delay_s},
            )
        except Exception as e:
            logger.warning(f"[halo.restart] audit write failed: {e}")
        logger.info(
            f"[halo.restart] execvp {sys.executable} {sys.argv}"
        )
        os.execvp(sys.executable, sys.argv)
    asyncio.create_task(_do_restart())
```

The `asyncio.create_task` runs the coroutine in the
background event loop. The PUT request returns
immediately with `restart_scheduled: true`. The task
sleeps 5 seconds, writes an audit log, then
`os.execvp` replaces the process.

### 4.3 The PUT response

The `put_voice_config` response gets a new field:

```python
{
    "wake_phrases": [...],
    "strict_wake_phrase": true,
    "asr_backend": "yuesub",
    "asr_corrector": "bert",
    "restart_required": true,
    "restart_scheduled": true,  # NEW
    "persisted": true,
}
```

The frontend's `VoiceTab` Save handler (Sprint 18
Track B) reads `result.restart_scheduled` and shows a
special toast:

> "Voice settings saved. The backend is restarting in
> 5 seconds with the new ASR engine."

### 4.4 Audit log

We use stdlib `logging` (already configured by
`app/core/logging.py`) rather than `app/security/audit.py`
(which is for Mac control actions, not generic events).
A `logger.info` line at INFO level with the event name
and details goes to the server log. The user's existing
log shipper / journal picks it up.

## 5. File-by-file change set

| Path | Change | LoC est. |
|---|---|---|
| `backend/app/core/restart.py` | NEW. The `schedule_restart` function described above | +50 / 0 |
| `backend/app/api/voice_ws.py` | Call `schedule_restart` when `restart_required` flips true; add `restart_scheduled` field to PUT response | +15 / -2 |
| `backend/tests/voice/test_voice_config_asr.py` | Add 3 tests: (a) PUT that flips restart returns `restart_scheduled: true` and the `_restart_scheduled` module flag is set, (b) PUT that doesn't change asr returns `restart_scheduled: false`, (c) the restart scheduler module is importable and `schedule_restart` creates an asyncio task (we don't actually exec in tests — the exec is short-circuited by a monkeypatched `os.execvp`) | +120 / 0 |
| `frontend/src/lib/api.ts` | Add `restart_scheduled?: boolean` to the `setVoiceConfig` response type | +3 / 0 |
| `frontend/src/routes/settings/VoiceTab.tsx` | Show a different toast when `result.restart_scheduled` is true: "Backend restarting in 5s with the new ASR engine" | +15 / -3 |
| `docs/FEATURE-SPEC-SPRINT19b.md` | NEW. This file. | +150 / 0 |
| `docs/CHANGELOG.md` | Add Sprint 19b entry under [Unreleased] | +30 / 0 |

**Total**: ~380 LoC. Backend-only logic + small frontend
toast tweak. ~1 day wall clock.

## 6. Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **os.execvp orphans the old process** | Low | Low | `os.execvp` replaces the process image in place (Unix), not fork-and-exec. The PID stays the same. No orphan. |
| **Restart during in-flight voice turn** | Medium | Medium | The 5s grace period gives in-flight turns time to finish. The new process picks up any orphan state. |
| **WebSocket clients see abrupt disconnect** | Medium | Low | The frontend's `useWsEvent` reconnects automatically. The "Restart required" banner tells the user what's happening. |
| **Audit log write fails** | Low | Low | The restart still proceeds (we catch the exception and log a warning). The audit is best-effort. |
| **The user changes asr 3 times in a row** | Low | Medium | Each `schedule_restart` call creates a new asyncio task. Multiple scheduled restarts would race — the last one wins because the new process reads config.toml. We don't deduplicate because the 5s grace is short and the user can't realistically click 3 times in 5s. |
| **Restart loop (bad config causes immediate crash, supervisor restarts, crash again)** | Low | High | We use `os.execvp`, not a supervisor. The user has to fix config.toml and re-launch. |
| **uvicorn `--reload` mode** | Low | Low | `--reload` mode is for dev. Sprint 19b's self-restart would conflict with uvicorn's reload. We log a warning at startup if `--reload` is detected (best-effort, since uvicorn doesn't expose this flag to the app). |

## 7. Acceptance tests

1. **PUT that flips restart returns restart_scheduled=true** —
   a test that PUTs `{asr_backend: "yuesub"}` and asserts
   the response includes `restart_scheduled: true` AND the
   internal `_restart_scheduled` module flag is set.
2. **PUT that doesn't change asr returns restart_scheduled=false** —
   a test that PUTs only `wake_phrases` and asserts
   `restart_scheduled: false`.
3. **schedule_restart is importable + creates asyncio task** —
   a unit test that patches `os.execvp` to a no-op, calls
   `schedule_restart(delay_s=0.1)`, and asserts the
   function returns without raising.
4. **Frontend toast** — verify (via type / build) that
   `setVoiceConfig`'s response type includes
   `restart_scheduled?: boolean` and the toast branches on
   it.

## 8. Sign-off

- [x] **Track 19b scope agreed** — auto-restart on ASR
      change, 5s grace period, `os.execvp` self-restart,
      audit log entry, frontend toast, no supervisor.
- [x] **Out-of-scope items confirmed** — 19c (Tauri
      always-on), 19d (Whisper fine-tune), supervisor
      daemon all deferred.

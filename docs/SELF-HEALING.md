# Gundam Halo — Self-Healing Backend (Sprint 43)

## What this does

The Gundam Halo backend runs 24/7 in the background. When it crashes
(SIGKILL, OOM, uncaught exception, etc.), the launchd supervisor
restarts it within ~5 seconds. But launchd has a few blind spots:

1. **It silently gives up after ~10 retries in 10 minutes.** No UI
   surfaces this — the user finds out when they next open the
   cockpit.
2. **It can't notify the user externally.** If you're at work and
   the Mac at home crashes, you don't find out until you VPN in.
3. **The Tauri tray icon shows animated Unicorn regardless of
   backend health.** Misleading the user into thinking everything
   is fine.

Sprint 43 ships a **3-layer watchdog** that fixes all three:

```
┌─────────────────────────────────────────────────────────────────────┐
│  Layer 1: launchd KeepAlive + 5s ThrottleInterval  (existing)       │
│  → Respawns backend within 5s of crash                              │
│  → Throttles if backend crashes in a tight loop                      │
├─────────────────────────────────────────────────────────────────────┤
│  Layer 2: launchd WatchPaths → scripts/on-launchd-crash.sh  (NEW)  │
│  → Fires when backend writes $HALO_HOME/state/crash_marker          │
│  → Script appends JSONL event to crash_log.jsonl                    │
│  → Single source of truth for "backend crashed N times"             │
├─────────────────────────────────────────────────────────────────────┤
│  Layer 3: Tauri watchdog thread (NEW)                                │
│  → Polls /api/health every 60s (HTTP via curl, no reqwest dep)      │
│  → 3 consecutive failures → emit backend-unhealthy event             │
│  → At 3rd fail, queries /api/system/health-detailed                  │
│    → If crash_count_60m >= 3 → emit backend-respawn-disabled         │
│  → Recovery (success after fail) → emit backend-recovered            │
└─────────────────────────────────────────────────────────────────────┘
```

## What you'll see

### Healthy state (default)

The cockpit looks exactly like before. The tray icon animates
green Unicorn as usual. **Nothing has changed for the happy path.**

### Yellow state — "Backend unreachable"

After **3 consecutive** `/api/health` failures (≈ 3 minutes of
polling), the cockpit shows a yellow banner above the regular
content:

> ◌ Backend unreachable
> 3 consecutive failures (threshold 3). Waiting for the backend
> to recover — checking every 60s.

The banner auto-clears when `/api/health` returns 200 again.

### Red state — "Backend respawn disabled"

If the backend has crashed **3+ times in the last 60 minutes**
(per the crash log), the banner switches to red with two action
buttons:

> ⚠ Backend respawn disabled
> Backend has crashed N times in the last hour. Respawn disabled
> to protect your Mac. Investigate
> `~/.gundam-halo/logs/launchd.err.log` before retrying.

- **Clear crash log & retry** — wipes `state/crash_log.jsonl` via
  the backend's `POST /api/system/clear-crash-log`. The watchdog
  re-checks on its next 60s tick.
- **Install launchd supervisor** — one-click install of the
  `com.gundam.halo.plist` LaunchAgent. Useful if you've never
  run `scripts/install-launchd.sh`.

## Crash log format

`~/.gundam-halo/state/crash_log.jsonl` — one JSON object per line,
oldest first:

```json
{"timestamp":"2026-06-26T10:00:00+00:00","exit_code":137,"reason":"oom-killed","uptime_seconds":7200}
{"timestamp":"2026-06-26T10:15:00+00:00","exit_code":1,"reason":"uncaught:KeyError","uptime_seconds":900}
```

Fields:

- `timestamp` — ISO 8601 UTC, when launchd fired the crash hook.
- `exit_code` — the uvicorn process's exit code (137 = OOM-killed
  on macOS; 1 = generic crash).
- `reason` — "oom-killed" | "uncaught-exception" | "launchd-throttled"
  | "shutdown" | "unknown". The backend's uncaught exception
  handler writes the more specific "uncaught:<ExceptionType>"
  format on the second-to-last category.
- `uptime_seconds` — how long the backend was alive before dying.

The log is auto-pruned: any entry older than 60 minutes is dropped
on the next write. The file is also capped at 1 MB / 1000 lines
(defensive — should never hit this in practice).

## When to investigate vs when to clear

| Symptom | Action |
|---|---|
| 1-2 crashes/hr | Normal Mac flakiness. Clear and move on. |
| 3+ crashes/hr | **Investigate first.** Read `~/.gundam-halo/logs/launchd.err.log` — the last 50 lines usually show the root cause. Common culprits: missing dep, bad TOML config, port collision. |
| Recurring OOM-killed | Reduce `[voice] model_size` from `large` to `base` in `~/.gundam-halo/config.toml`. Or close other memory-heavy apps. |
| Same crash every restart (within 60s) | Bad config — TOML parse error, missing env var, broken model path. Read the err log; fix the root cause; THEN clear the crash log. |
| Crashes only when you open Tauri app | Tauri-side crash (not backend). Read `~/Library/Logs/gundam-halo/` for the Tauri stack trace. |

## False-positive scenarios

These all look like "backend down" but are NOT a respawn-loop
trigger (i.e. `respawn_disabled` stays False):

| Scenario | What you'll see | Why it's fine |
|---|---|---|
| Mac goes to sleep | Yellow banner appears after 3min of failed pings | Mac wake restores the network; next successful ping auto-clears the banner. |
| Tailscale daemon restarts | Brief yellow flash | The `tailscale` connection drops + the backend briefly can't route to its own port — recovers in <60s. |
| Port 8765 collision | Yellow banner + crash log has `Address already in use` | One-shot event; clear the crash log after killing the conflicting process. |
| Manual `kill <uvicorn-pid>` for dev | Yellow banner | Expected. The dev wants to restart manually. |

If `respawn_disabled` flips True on what looks like a false
positive, **check the crash log** — if all entries have
`uptime_seconds > 0`, they're real crashes, not boot loops.

## Disabling the watchdog (dev mode)

If you're actively developing the backend and don't want to be
interrupted by the respawn-loop guard, set this in your shell
before launching the Tauri app:

```bash
export WATCHDOG_DISABLED=true
open /Applications/Gundam\ Halo.app
```

(For now, the env var is documented but not yet wired into the
Rust code — it will be added if there's demand. For Sprint 43,
the simplest dev escape hatch is to comment out the
`watchdog::start_watchdog(...)` call in `lib.rs:setup`.)

## Architecture: why we use curl, not reqwest

The Tauri Rust watchdog shells out to `curl` for HTTP instead of
pulling in the `reqwest` crate. Trade-off:

- **`reqwest` (with `blocking` feature)**: +10 MB binary, but a
  proper Rust HTTP client with retries, TLS, etc.
- **`curl` (system binary)**: 0 MB added, every Mac has it
  pre-installed, 5s timeout via `--max-time`.

We chose curl because:

1. **Binary size matters** — Tauri apps are downloaded by users
   who care about disk space.
2. **The watchdog is a single-purpose HTTP probe** — no retries,
   no streaming, no auth. curl's `-sf` is enough.
3. **Security** — curl's TLS stack is managed by the OS, not our
   Tauri build. We inherit Apple's latest LibreSSL patches
   automatically.

## Operational runbook

### "My backend keeps restarting but I can't figure out why"

```bash
# 1. See the last 50 lines of stderr.
tail -50 ~/.gundam-halo/logs/launchd.err.log

# 2. Check the crash log for patterns.
tail -20 ~/.gundam-halo/state/crash_log.jsonl | python3 -m json.tool --json-lines

# 3. If you see "uncaught:KeyError" or "uncaught:ImportError", the
#    config.toml or venv is broken — fix the underlying issue, then:
#    - Open the cockpit
#    - Click "Clear crash log & retry" on the red banner
#    - Or manually: rm ~/.gundam-halo/state/crash_log.jsonl
```

### "The watchdog fires every minute, even though the backend is fine"

Two likely causes:

1. **Tailscale is between you and the backend.** The watchdog
   pings `http://localhost:8765/api/health` directly. If your
   `config.toml` has `[server] require_tailscale = true`, the
   backend may be refusing connections on the plain
   `localhost` interface. Set `require_tailscale = false`
   temporarily to confirm.
2. **Backend is bound to a different port.** Check
   `~/.gundam-halo/config.toml` `[server] port`. The watchdog
   hard-codes 8765. If you've changed the port, update the
   Rust constants in `src/watchdog.rs` (HEALTH_URL +
   DETAILED_URL).

### "I want to add a custom Telegram alert"

Set these in `~/.gundam-halo/.env` (chmod 600, per the project
security rule):

```
WATCHDOG_TELEGRAM_BOT_TOKEN=123456:abc...   # from @BotFather
WATCHDOG_TELEGRAM_CHAT_ID=987654            # your personal chat ID
```

When `respawn_disabled` flips True, the backend POSTs to
`https://api.telegram.org/bot<TOKEN>/sendMessage` with the crash
summary. The integration is wired in Sprint 43 but **disabled by
default** (no token = no alert, no error).

## Files

| File | Purpose |
|---|---|
| `backend/app/core/watchdog.py` | Crash log + 60-min rolling window + threshold logic |
| `backend/app/api/system.py` | `/api/system/health-detailed` + `/api/system/clear-crash-log` |
| `backend/tests/core/test_watchdog.py` | 7 unit tests for the core logic |
| `backend/tests/api/test_health_detailed.py` | 5 endpoint tests |
| `backend/tests/chaos/test_watchdog_respawn_loop.py` | 6 chaos tests (the H-risk mitigation) |
| `backend/tests/scripts/test_on_launchd_crash.py` | 5 tests for the bash crash hook |
| `frontend/src-tauri/src/watchdog.rs` | Polling thread + 3 IPC commands + 6 unit tests |
| `frontend/src-tauri/src/lib.rs` | Wires `mod watchdog` + IPC commands + tray icon hook |
| `frontend/src/services/halo-watchdog-events.ts` | Frontend singleton + Tauri event subscription |
| `frontend/src/components/gundam/BackendHealthBanner.tsx` | Yellow/red banner with action buttons |
| `frontend/src/components/gundam/BackendHealthBanner.test.tsx` | 3 component tests |
| `frontend/src/components/layout/CockpitLayout.tsx` | Mounts `BackendHealthBanner` above `BackendOutdatedBanner` |
| `scripts/on-launchd-crash.sh` | Bash hook for launchd WatchPaths |
| `scripts/com.gundam.halo.plist` | Adds `<key>WatchPaths</key>` for the state dir |

## Security notes

- `POST /api/system/clear-crash-log` is **currently unprotected**
  (no auth). Same as the rest of the `/api/system/*` surface —
  single-user assumption per the project convention. Sprint 45
  will add an auth layer; tracked in `docs/SECURITY-HARDENING.md`.
- The crash log is at `~/.gundam-halo/state/crash_log.jsonl`.
  If you keep secrets in your `config.toml` (you shouldn't —
  use `.env`), they may appear in the crash log via uncaught
  exception messages. Defensive: the backend's exception handler
  strips `Authorization` headers and `api_key` values from the
  error message before writing the crash marker.
- Telegram bot token is read from env var ONLY (never config.toml).
  Per the project security rule, never paste tokens in chat —
  put them in `~/.gundam-halo/.env` and chmod 600.

## Future work (out of Sprint 43)

- Sprint 45: auth layer for `/api/system/*` endpoints.
- Sprint 47: auto-investigation on crash (scrape `launchd.err.log`
  + surface the top error in the banner).
- M14: multi-host watchdog coordinator (if user has multiple Macs).

# Sprint 43 — Self-Healing Backend (N from 2026-06-26 design review)

**Date**: 2026-06-26
**Status**: Draft
**Author**: Mavis
**Priority**: P0 (user-confirmed pain: out-of-house → backend crash → silent dead)
**Depends on**: Sprint 39 dashboard cards (for the toast + indicator UI), Sprint 42 health alias (for `/api/health` probe target)

## Goal

Close the **silent dead-machine** failure mode: today if the Gundam Halo backend
crashes while the user is away from the Mac (or if `launchd` itself dies),
they find out only when they next open the cockpit. By then voice / agent /
all in-flight work has been lost for hours.

Sprint 43 ships a **respawn-loop-safe watchdog** with three layers:

1. **Tauri Rust watchdog** — pings `/api/health` every 60s; if 3 consecutive
   failures AND the process isn't running, surface a tray-icon red dot + an
   in-app banner (builds on existing `BackendOutdatedBanner.tsx` pattern).
2. **Respawn-loop guard** — track crash count in `~/.gundam-halo/state/crash_log.json`;
   if >3 crashes in any rolling 60-minute window, **stop respawning** + flip
   tray icon to red + fire Telegram alert (if configured).
3. **launchd plist health check** — on Tauri startup, verify
   `launchctl list | grep com.gundam.halo` returns a PID; if not, surface
   "launchd supervisor not installed — install via scripts/install-launchd.sh"
   in the banner (one-click install button if Tauri has the permission).

**Important design constraint**: launchd already does basic KeepAlive respawn
with 5s throttle (`scripts/com.gundam.halo.plist:84`). We **don't replace
launchd** — we complement it. The watchdog detects when launchd itself has
given up (3+ crash/hr) and stops trying to make things worse.

## Scope

### In scope

**Backend** (`~/workspace/working/gundam-halo/backend/`):
- New `app/core/watchdog.py` (~250 LoC):
  - `CrashLog` dataclass — rolling 60-min crash events
  - `record_crash(home)` — append crash event + prune > 60min old
  - `crash_rate(home)` — return crashes-per-hour for the last hour
  - `should_stop_respawning(home, threshold=3)` — bool
  - `clear_crash_log(home)` — for the "I fixed it, resume" button
- New endpoint `GET /api/system/health-detailed` in `app/api/health.py`:
  - returns `{ status, version, name, crash_count_60m, last_crash_at, watchdog: { installed, pid } }`
  - Extends the Sprint 42 `/api/health` payload without breaking it
- New endpoint `POST /api/system/clear-crash-log` — admin-only (no auth
  layer yet — flagged as TODO for Sprint 45)
- 6 pytest tests for the watchdog (crash recording, rolling window prune,
  threshold logic, concurrent crashes, persistence across restarts,
  clear-crash-log)

**Tauri Rust** (`~/workspace/working/gundam-halo/frontend/src-tauri/`):
- New module `src/watchdog.rs` (~300 LoC):
  - `WatchdogState` — `Arc<Mutex<Option<JoinHandle>>>` + `Arc<AtomicBool>` stop
  - `start_watchdog(app)` — spawn dedicated OS thread (NOT tokio task —
    pyo3-style blocking thread; cpal pattern per Sprint 33b)
  - `poll_health()` — `reqwest::blocking::get("http://localhost:8765/api/health")`
    with 5s timeout, 60s interval, 3-strike failure count
  - On 3rd failure: emit Tauri event `backend-unhealthy` to frontend;
    if `crash_count_60m >= 3`, also emit `backend-respawn-disabled`
  - On recovery: emit `backend-recovered`
- New IPC command `get_backend_health` in `commands.rs` — returns
  `{ installed, pid, crash_count_60m, last_crash_at, last_check_at }`
- New IPC command `install_launchd_supervisor` — wraps
  `scripts/install-launchd.sh` (shells out; requires user sudo prompt for
  the LaunchAgent copy step); returns success/error
- 4 Rust unit tests (mock reqwest, assert event emission logic,
  crash threshold logic, concurrent-thread spawn cleanup)
- Tray icon health dot — extend existing tray animation in `lib.rs:103`
  to overlay a red/green/yellow dot when backend is unhealthy

**Frontend** (`~/workspace/working/gundam-halo/frontend/`):
- New `components/gundam/BackendHealthBanner.tsx` (~120 LoC) — modelled on
  `BackendOutdatedBanner.tsx`. Three states:
  - Healthy: hidden (default)
  - Unhealthy: yellow banner "Backend unreachable — checking…" (auto-clears
    on recovery event)
  - Respawn-disabled: red banner "Backend has crashed 3+ times in the
    last hour. Respawn disabled to protect your Mac. [Clear crash log →
    try again] [Install launchd supervisor]"
- Subscribe to `backend-unhealthy` / `backend-recovered` /
  `backend-respawn-disabled` Tauri events (new service
  `services/halo-watchdog-events.ts`, mirrors `halo-voice-ws.ts` pattern)
- Mount in `CockpitLayout.tsx` above `BackendOutdatedBanner`
- 2 vitest tests (renders healthy/unhealthy/respawn-disabled states; click
  "Clear crash log" → calls IPC)

**Backend ↔ Tauri watchdog contract** (no new dep):
- Tauri polls `GET /api/health` every 60s (already in `/api/health` since Sprint 42)
- Backend exposes `GET /api/system/health-detailed` for the **extended**
  payload (crash count, last crash time) — Tauri reads this every 5 min
  (not every 60s — crash count doesn't change that fast)
- **Crash recording happens in launchd, NOT in Tauri**: launchd already
  emits a crash event when KeepAlive triggers; we add a small wrapper
  script `scripts/on-launchd-crash.sh` that the plist calls via
  `WatchPaths` / `QueueDirectories` (launchd doesn't have a built-in
  crash hook, so we use a different approach — see "launchd integration"
  below)

**Docs**:
- `docs/SELF-HEALING.md` NEW (~200 LoC) — operational doc:
  - The 3-layer watchdog architecture (this spec in condensed form)
  - How to read `crash_log.json` manually
  - When to manually clear vs when to investigate
  - Telegram bot setup (optional, opt-in)
  - launchd plist install + verification
  - 4 common false-positive scenarios (Mac sleep / Tailscale down /
    port collision / OOM-killer) and how to distinguish from real crash
- Update `docs/FEATURE-SPEC-SPRINT43.md` (this file)
- Update `docs/CHANGELOG.md` [Unreleased]
- Update `docs/SECURITY-HARDENING.md` — add note about `/api/system/clear-crash-log`
  being unprotected (TODO for Sprint 45 auth layer)
- Update `docs/tickets/M9-E.md` — note watchdog completion as related infra
- Update `docs/DASHBOARD.md` — add BackendHealthBanner to the cockpit top bar

### Out of scope

- **Sprint 44** (F — 8-step wizard): ships separately. The wizard will
  use the watchdog's `/api/system/health-detailed` for its "is the
  backend healthy?" step (step 0), but wizard UI is Sprint 44.
- **Telegram bot auto-setup**: the alert hook is **read from env var only**
  (no wizard step to enter the bot token in Sprint 43). User opts in by
  setting `WATCHDOG_TELEGRAM_BOT_TOKEN` + `WATCHDOG_TELEGRAM_CHAT_ID` in
  `~/.gundam-halo/.env` (chmod 600 — per memory rule "永遠唔接受 raw secret").
- **Auth layer for `/api/system/clear-crash-log`**: tracked as TODO for
  Sprint 45 (M12 hardening). For now the endpoint is unprotected but
  only does a benign file clear — no destructive action.
- **Multi-host watchdog coordination**: if user has multiple Macs,
  each runs its own watchdog independently. No central coordinator.
  Tracked as future work (probably M14).
- **Auto-investigation on crash** (e.g. "scrape last 100 lines of
  launchd.err.log and surface in banner"): out of scope. The watchdog
  just counts crashes; investigation is a manual step the user takes
  by reading `~/.gundam-halo/logs/launchd.err.log`.
- **Custom respawn backoff** (exponential backoff beyond launchd's 5s):
  not needed — launchd already throttles. We only stop respawning above
  the crash threshold.
- **Health check for downstream services** (LLM API / Whisper model /
  Tailscale): each has its own existing health surface. Watchdog only
  checks the backend itself.

## Why now

Per the 2026-06-26 design review, **N is P0** because the pain is
user-confirmed and the cost of NOT having it is silent data loss. The
launchd plist already does basic KeepAlive, but:

1. **launchd silently gives up if it can't restart the process** (after
   ~10 retries in 10 minutes — undocumented macOS behavior). No UI
   surfaces this.
2. **No external notification** — if user is at work and Mac at home
   crashes, they don't find out until they VPN in.
3. **Tray icon shows animated Unicorn regardless of backend health** —
   misleading the user into thinking everything is fine.

Sprint 43 fixes all three with a thin layer on top of the existing infra.
Estimated code: ~700 LoC backend + ~400 LoC Tauri + ~200 LoC frontend +
~200 LoC docs. ~1500 LoC total — fits in 1 sprint comfortably.

## Implementation

### Layer 1: Backend crash log (`app/core/watchdog.py`)

```python
"""Watchdog — crash-rate tracking + Telegram alert hook.

Crash events come from a launchd wrapper script
(`scripts/on-launchd-crash.sh`) that the plist calls via a
QueueDirectories trigger (launchd doesn't have a direct "process
crashed" hook). The wrapper appends a JSON line to
`~/.gundam-halo/state/crash_log.jsonl` and the backend reads it on
demand via `/api/system/health-detailed`.

Crash log schema (one JSON object per line):
    {"timestamp": "2026-06-26T10:30:00+08:00",
     "exit_code": 1,
     "reason": "oom-killed" | "uncaught-exception" | "launchd-throttled",
     "uptime_seconds": 3600}

The log is rotated automatically — entries older than 60 minutes are
pruned on every `record_crash()` call.
"""
```

Key functions:

```python
CRASH_LOG_FILENAME = "state/crash_log.jsonl"
CRASH_THRESHOLD_PER_HOUR = 3  # if >3 crashes in 60min, stop respawning

@dataclass
class CrashEvent:
    timestamp: str  # ISO 8601 UTC
    exit_code: int
    reason: str
    uptime_seconds: int

def record_crash(home: Path, event: CrashEvent) -> None:
    """Append one crash event + prune > 60min old."""
    log_path = home / CRASH_LOG_FILENAME
    log_path.parent.mkdir(parents=True, exist_ok=True)
    # Prune first.
    if log_path.is_file():
        cutoff = time.time() - 3600
        kept: list[str] = []
        for line in log_path.read_text(encoding="utf-8").splitlines():
            try:
                ev = json.loads(line)
                ts = datetime.fromisoformat(ev["timestamp"]).timestamp()
                if ts >= cutoff:
                    kept.append(line)
            except (json.JSONDecodeError, KeyError, ValueError):
                continue  # drop malformed entries
        log_path.write_text("\n".join(kept) + "\n", encoding="utf-8")
    # Append the new event.
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(event), ensure_ascii=False) + "\n")

def crash_count_last_hour(home: Path) -> int:
    """Return count of crashes in the last 60 minutes."""
    log_path = home / CRASH_LOG_FILENAME
    if not log_path.is_file():
        return 0
    cutoff = time.time() - 3600
    count = 0
    for line in log_path.read_text(encoding="utf-8").splitlines():
        try:
            ev = json.loads(line)
            ts = datetime.fromisoformat(ev["timestamp"]).timestamp()
            if ts >= cutoff:
                count += 1
        except (json.JSONDecodeError, KeyError, ValueError):
            continue
    return count

def last_crash_at(home: Path) -> str | None:
    """Return ISO 8601 timestamp of the most recent crash, or None."""
    log_path = home / CRASH_LOG_FILENAME
    if not log_path.is_file():
        return None
    latest: str | None = None
    for line in log_path.read_text(encoding="utf-8").splitlines():
        try:
            ev = json.loads(line)
            ts = ev.get("timestamp")
            if ts and (latest is None or ts > latest):
                latest = ts
        except (json.JSONDecodeError, KeyError):
            continue
    return latest

def should_stop_respawning(home: Path, threshold: int = CRASH_THRESHOLD_PER_HOUR) -> bool:
    """True if crash count in last hour exceeds threshold."""
    return crash_count_last_hour(home) >= threshold

def clear_crash_log(home: Path) -> int:
    """Truncate the crash log. Returns the number of events cleared."""
    log_path = home / CRASH_LOG_FILENAME
    if not log_path.is_file():
        return 0
    count = sum(1 for _ in log_path.read_text(encoding="utf-8").splitlines() if _.strip())
    log_path.unlink()
    return count
```

### Layer 1b: launchd integration (`scripts/on-launchd-crash.sh`)

launchd doesn't fire a "process crashed" callback natively. The
cleanest workaround is `KeepAlive.AfterInitialDemand=true` +
`WatchPaths` pointing at a "crash marker" file that the backend writes
to when it knows it's about to die (uncaught exception handler +
`atexit` hook). On WatchPaths trigger, launchd runs
`scripts/on-launchd-crash.sh`, which appends to the crash log.

```bash
#!/usr/bin/env bash
# scripts/on-launchd-crash.sh
# launchd calls this on WatchPaths trigger (crash marker file changed).
set -euo pipefail
HALO_HOME="${HALO_HOME:-$HOME/.gundam-halo}"
CRASH_MARKER="$HALO_HOME/state/crash_marker"
LOG="$HALO_HOME/state/crash_log.jsonl"
mkdir -p "$(dirname "$LOG")"

# Parse the crash marker (newline-separated KEY=VALUE).
declare -A META
while IFS='=' read -r k v; do
    META["$k"]="$v"
done < "$CRASH_MARKER"

TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%S+00:00")
EXIT_CODE="${META[exit_code]:-1}"
REASON="${META[reason]:-unknown}"
UPTIME="${META[uptime_seconds]:-0}"

# Append JSON line.
printf '{"timestamp":"%s","exit_code":%d,"reason":"%s","uptime_seconds":%d}\n' \
    "$TIMESTAMP" "$EXIT_CODE" "$REASON" "$UPTIME" >> "$LOG"

# Remove marker so next crash starts clean.
rm -f "$CRASH_MARKER"
```

Backend-side crash marker writer (added to `app/main.py:create_app`
shutdown hook):

```python
import atexit
import os
import time

_start_time = time.monotonic()

def _write_crash_marker(exit_code: int = 1, reason: str = "shutdown") -> None:
    halo_home = Path(os.environ.get("HALO_HOME", Path.home() / ".gundam-halo"))
    marker = halo_home / "state" / "crash_marker"
    marker.parent.mkdir(parents=True, exist_ok=True)
    uptime = int(time.monotonic() - _start_time)
    marker.write_text(
        f"exit_code={exit_code}\nreason={reason}\nuptime_seconds={uptime}\n",
        encoding="utf-8",
    )

# Uncaught exception → write marker before propagating.
def _excepthook(exc_type, exc_value, exc_tb):
    _write_crash_marker(exit_code=1, reason=f"uncaught:{exc_type.__name__}")
    sys.__excepthook__(exc_type, exc_value, exc_tb)
sys.excepthook = _excepthook

# Clean shutdown → no marker (launchd won't fire WatchPaths).
atexit.register(lambda: None)  # no-op; intentional
```

Update `com.gundam.halo.plist`:

```xml
<key>WatchPaths</key>
<array>
    <string>__HALO_HOME__/state</string>
</array>
```

### Layer 2: New endpoint `GET /api/system/health-detailed`

In `app/api/health.py` (next to the existing `router`):

```python
@router.get("/system/health-detailed")
async def get_health_detailed(home: Path = Depends(get_halo_home)) -> dict:
    """Extended health payload for the watchdog (Sprint 43).
    
    Includes crash count + last crash time + watchdog install
    status. Consumed by Tauri's watchdog every 5 min (not the
    per-minute /api/health probe).
    """
    from app.core.watchdog import (
        crash_count_last_hour,
        last_crash_at,
        should_stop_respawning,
    )
    
    crash_count = crash_count_last_hour(home)
    last_crash = last_crash_at(home)
    stop_respawn = should_stop_respawning(home)
    
    return {
        "status": "ok",
        "version": __version__,
        "name": "gundam-halo",
        "crash_count_60m": crash_count,
        "last_crash_at": last_crash,
        "respawn_disabled": stop_respawn,
        "watchdog": {
            "installed": _check_launchd_installed(),
            "pid": _get_launchd_pid(),
        },
    }

def _check_launchd_installed() -> bool:
    """Check if com.gundam.halo plist is loaded in launchd."""
    import subprocess
    try:
        result = subprocess.run(
            ["launchctl", "list"],
            capture_output=True, text=True, timeout=2,
        )
        return "com.gundam.halo" in result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False

def _get_launchd_pid() -> int | None:
    """Return PID of the running uvicorn process (via launchctl)."""
    import subprocess
    try:
        result = subprocess.run(
            ["launchctl", "list", "com.gundam.halo"],
            capture_output=True, text=True, timeout=2,
        )
        # launchctl list output format: "PID Status Label"
        # PID is "-" if not running.
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 3 and parts[2] == "com.gundam.halo":
                try:
                    return int(parts[0])
                except ValueError:
                    return None
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
```

### Layer 3: Tauri Rust watchdog (`src/watchdog.rs`)

```rust
//! Watchdog — pings /api/health every 60s, emits Tauri events on
//! state changes. Runs as a dedicated OS thread (NOT tokio task —
//! blocking HTTP via reqwest::blocking keeps the thread alive even
//! during backend restart where tokio runtime might be paused).
//!
//! State machine:
//!   healthy (default) → unhealthy (1st fail) → unhealthy (2nd) →
//!   unhealthy (3rd) → emit "backend-unhealthy"
//!   any state → healthy → emit "backend-recovered"
//!   at 3rd consecutive fail, also call /api/system/health-detailed
//!   and if respawn_disabled=true, emit "backend-respawn-disabled"

use std::sync::atomic::{AtomicBool, AtomicU8, Ordering};
use std::sync::Arc;
use std::thread;
use std::time::Duration;

use serde::Serialize;
use tauri::{AppHandle, Emitter, Manager};

const POLL_INTERVAL_SEC: u64 = 60;
const FAILURE_THRESHOLD: u8 = 3;  // 3 consecutive failures = unhealthy
const HEALTH_ENDPOINT: &str = "http://localhost:8765/api/health";
const DETAILED_HEALTH_ENDPOINT: &str = "http://localhost:8765/api/system/health-detailed";

#[derive(Clone, Serialize)]
struct WatchdogEvent {
    timestamp: String,  // ISO 8601
    consecutive_failures: u8,
    crash_count_60m: u32,
    respawn_disabled: bool,
}

pub fn start_watchdog(app: AppHandle) -> Arc<AtomicBool> {
    let stop_flag = Arc::new(AtomicBool::new(false));
    let stop_flag_clone = stop_flag.clone();
    let app_clone = app.clone();
    
    thread::Builder::new()
        .name("halo-watchdog".into())
        .spawn(move || {
            let consecutive_failures = Arc::new(AtomicU8::new(0));
            let last_state = Arc::new(AtomicU8::new(0));  // 0=healthy, 1=unhealthy, 2=respawn-disabled
            
            while !stop_flag_clone.load(Ordering::SeqCst) {
                thread::sleep(Duration::from_secs(POLL_INTERVAL_SEC));
                if stop_flag_clone.load(Ordering::SeqCst) { break; }
                
                let healthy = poll_health();
                let prev_state = last_state.load(Ordering::SeqCst);
                
                if healthy {
                    consecutive_failures.store(0, Ordering::SeqCst);
                    if prev_state != 0 {
                        last_state.store(0, Ordering::SeqCst);
                        emit_event(&app_clone, "backend-recovered", &consecutive_failures);
                    }
                } else {
                    let fails = consecutive_failures.fetch_add(1, Ordering::SeqCst) + 1;
                    
                    if fails >= FAILURE_THRESHOLD {
                        // Check detailed health for respawn_disabled flag.
                        let detailed = poll_detailed_health();
                        let new_state = if detailed.respawn_disabled { 2 } else { 1 };
                        
                        if new_state != prev_state {
                            last_state.store(new_state, Ordering::SeqCst);
                            let event = WatchdogEvent {
                                timestamp: iso8601_now(),
                                consecutive_failures: fails,
                                crash_count_60m: detailed.crash_count_60m,
                                respawn_disabled: detailed.respawn_disabled,
                            };
                            let event_name = if new_state == 2 {
                                "backend-respawn-disabled"
                            } else {
                                "backend-unhealthy"
                            };
                            let _ = app_clone.emit(event_name, event);
                        }
                    }
                }
            }
        })
        .expect("failed to spawn halo-watchdog thread");
    
    stop_flag
}

fn poll_health() -> bool {
    match reqwest::blocking::Client::new()
        .get(HEALTH_ENDPOINT)
        .timeout(Duration::from_secs(5))
        .send()
    {
        Ok(resp) => resp.status().is_success(),
        Err(_) => false,
    }
}

#[derive(serde::Deserialize)]
struct DetailedHealth {
    crash_count_60m: u32,
    respawn_disabled: bool,
}

fn poll_detailed_health() -> DetailedHealth {
    reqwest::blocking::Client::new()
        .get(DETAILED_HEALTH_ENDPOINT)
        .timeout(Duration::from_secs(5))
        .send()
        .ok()
        .and_then(|r| r.json::<DetailedHealth>().ok())
        .unwrap_or(DetailedHealth { crash_count_60m: 0, respawn_disabled: false })
}
```

Tray icon health dot (extend `lib.rs:103`):

```rust
// After each successful /api/health check, update tray icon overlay.
// Green = healthy, yellow = unhealthy, red = respawn-disabled.
fn update_tray_health_dot(app: &AppHandle, state: u8) {
    if let Some(tray) = app.tray_by_id("main-tray") {
        let dot_color = match state {
            0 => "green", 1 => "yellow", _ => "red",
        };
        // Composite the animated Unicorn frame with a small dot in the corner.
        // For v1, we just toggle between 3 pre-rendered PNG variants:
        // `tray_unicorn_green.png`, `tray_unicorn_yellow.png`, `tray_unicorn_red.png`.
        let icon_path = format!("assets/tray_unicorn_{}.png", dot_color);
        if let Ok(img) = tauri::image::Image::from_path(&icon_path) {
            let _ = tray.set_icon(Some(img));
        }
    }
}
```

### Layer 4: Frontend banner (`components/gundam/BackendHealthBanner.tsx`)

```tsx
/**
 * BackendHealthBanner — Sprint 43.
 *
 * Mounted above BackendOutdatedBanner in CockpitLayout. Hidden by
 * default; renders only on Tauri events from the watchdog:
 *   - `backend-unhealthy`        → yellow "Backend unreachable" banner
 *   - `backend-respawn-disabled` → red "Respawn disabled" banner
 *   - `backend-recovered`        → auto-clear (banner hides)
 *
 * The "Respawn disabled" banner has two action buttons:
 *   1. "Clear crash log & retry" → calls `clear_crash_log` IPC →
 *      backend truncates crash_log.jsonl → watchdog re-checks on
 *      next 60s tick.
 *   2. "Install launchd supervisor" → calls `install_launchd_supervisor`
 *      IPC → if user has no plist installed, this one-clicks it.
 */
```

### Tauri IPC contract (3 new commands)

```rust
#[tauri::command]
async fn get_backend_health() -> BackendHealth {
    // Reads cached state from watchdog thread (no I/O here).
    BackendHealth {
        installed: true,  // from launchctl check
        pid: Some(1234),
        crash_count_60m: 0,
        last_crash_at: None,
        last_check_at: Some("2026-06-26T10:00:00+08:00".into()),
    }
}

#[tauri::command]
async fn install_launchd_supervisor(app: AppHandle) -> Result<String, String> {
    // Run scripts/install-launchd.sh; capture stdout/stderr.
    let output = std::process::Command::new("bash")
        .arg("scripts/install-launchd.sh")
        .current_dir(app.path().resource_dir().unwrap_or_default())
        .output()
        .map_err(|e| e.to_string())?;
    if output.status.success() {
        Ok(String::from_utf8_lossy(&output.stdout).into())
    } else {
        Err(String::from_utf8_lossy(&output.stderr).into())
    }
}
```

The `clear_crash_log` action goes through the existing frontend `api` lib
(POST `/api/system/clear-crash-log`) — no new Tauri command needed.

## Test plan

### Backend (pytest) — 6 tests

`tests/core/test_watchdog.py`:

1. **`test_record_crash_appends_to_log`** — write 3 crashes 1min apart,
   assert log has 3 lines + first crash timestamp is preserved.
2. **`test_record_crash_prunes_old_entries`** — write 5 crashes, manually
   rewrite the oldest 3 with timestamps 90min ago, record a 6th crash,
   assert only 3 entries remain (the new one + the 2 recent ones).
3. **`test_crash_count_last_hour_zero_when_no_log`** — empty dir →
   returns 0, doesn't crash.
4. **`test_should_stop_respawning_at_threshold`** — write 3 crashes in
   30min → `should_stop_respawning()` returns True; clear log → False.
5. **`test_concurrent_crash_recording`** — spawn 10 threads each calling
   `record_crash()` simultaneously, assert all 10 entries in log + no
   file lock corruption.
6. **`test_clear_crash_log_returns_event_count`** — write 5 crashes,
   call clear → returns 5, log file is gone.

`tests/api/test_health_detailed.py`:

7. **`test_health_detailed_includes_crash_count`** — write 2 crashes,
   GET `/api/system/health-detailed` → `crash_count_60m == 2`.
8. **`test_health_detailed_flags_respawn_disabled_at_threshold`** — write
   4 crashes, GET → `respawn_disabled == true`.
9. **`test_health_detailed_includes_launchd_status`** — mock
   `subprocess.run` for `launchctl list`, assert `watchdog.installed`
   matches the mock output.

### Tauri (Rust unit tests) — 4 tests

`src/watchdog.rs::tests`:

1. **`test_poll_health_success`** — mock reqwest, returns 200 → `poll_health()`
   returns True.
2. **`test_poll_health_timeout`** — mock reqwest that sleeps 10s,
   `poll_health()` returns False within 6s.
3. **`test_failure_threshold_emits_unhealthy_event`** — mock poll_health
   to always fail, run watchdog for 3 cycles, assert Tauri event
   `backend-unhealthy` was emitted exactly once.
4. **`test_recovery_resets_consecutive_failures`** — 2 failures + 1
   success + 2 failures, assert NO `backend-unhealthy` event (the
   streak was reset by the success).

### Frontend (vitest) — 2 tests

`src/components/gundam/BackendHealthBanner.test.tsx`:

1. **`test_renders_unhealthy_state`** — mock `listen('backend-unhealthy')`
   to fire once; assert yellow banner with "Backend unreachable" copy.
2. **`test_click_clear_crash_log_calls_api`** — render with respawn-
   disabled state, click "Clear crash log & retry", assert
   `api.clearCrashLog()` was called + the IPC `install_launchd_supervisor`
   was NOT called.

### Manual smoke

1. Start Tauri app + backend. Verify tray icon shows **green** Unicorn.
2. `kill -9 <uvicorn-pid>` (simulate crash). Wait 60s. Verify:
   - Yellow "Backend unreachable" banner appears in cockpit.
   - Tray icon switches to yellow.
   - `crash_log.jsonl` has 1 entry after ~10s (launchd restart + crash marker).
3. Repeat crash 3 more times within 60min. Verify:
   - Red "Respawn disabled" banner appears.
   - Tray icon switches to red.
   - If Telegram configured, alert message received.
4. Click "Clear crash log & retry". Verify:
   - Banner auto-dismisses after next watchdog tick.
   - Tray icon returns to green.
   - Backend is reachable again.
5. `launchctl unload ~/Library/LaunchAgents/com.gundam.halo.plist`.
   Restart Tauri app. Verify banner shows "launchd supervisor not
   installed" with one-click install button.

### Chaos test — the critical H-risk mitigation

Per the design review, the respawn-loop risk is **HIGH severity**.
Sprint 43 MUST ship with a chaos test that proves the safeguard
actually works:

`tests/chaos/test_watchdog_respawn_loop.py`:

```python
"""Chaos test — verify the watchdog stops respawning above threshold.

Simulates 10 backend crashes in 60 minutes (using a fake timer +
mocked crash_log.jsonl) and asserts:
  1. `should_stop_respawning()` returns True after the 3rd crash.
  2. The "backend-respawn-disabled" event would be emitted by Tauri
     (we test the backend logic that the event is based on).
  3. After clearing the log, `should_stop_respawning()` returns False
     again.
  4. The crash log itself is never deleted by the recording function
     (only `clear_crash_log` deletes it — defensive against bugs).
"""
```

## Acceptance criteria

1. **Backend**: `pytest tests/core/test_watchdog.py
   tests/api/test_health_detailed.py tests/chaos/test_watchdog_respawn_loop.py -v`
   → all green.
2. **Tauri**: `cd frontend/src-tauri && cargo test watchdog` → 4/4 green.
3. **Frontend**: `pnpm test:run BackendHealthBanner` → 2/2 green.
4. **Full backend pytest** (excl slow tts): all green (target **1260+** passed).
5. **Full vitest**: all green (target **69+** passed).
6. **`tsc --noEmit`**: 0 errors.
7. **`cargo check --tests`**: clean (no new warnings).
8. **Manual smoke** — the 5-step sequence above passes.
9. **Chaos test** — the 10-crash-in-60min scenario correctly triggers
   `should_stop_respawning=True` at crash 3, and `clear_crash_log()`
   resets it to False.
10. **No false positives** — Mac sleep / Tailscale down / port collision
    scenarios in `docs/SELF-HEALING.md` are tested manually and do NOT
    trigger the respawn-disabled state.

## Risks & mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| **launchd doesn't fire WatchPaths on every crash** | M | Use BOTH WatchPaths AND a Python `atexit` write of the crash marker. Belt-and-braces. |
| **Tauri watchdog thread leaks on app close** | L | `stop_flag: Arc<AtomicBool>` checked every 60s; on app exit, `lib.rs` calls `stop_flag.store(true)` + `thread.join()`. |
| **Race between watchdog poll and backend restart** | M | 60s interval is long enough that the brief "unhealthy" gap during restart is expected behavior (yellow banner for 60-120s after each restart). |
| **`/api/system/health-detailed` `subprocess.run` hangs** | M | 2-second timeout on every subprocess call; never blocks the event loop. |
| **`reqwest::blocking` from inside Tauri tokio runtime** | L | Spawn as a dedicated OS thread (not tokio task), per the cpal pattern from Sprint 33b — `reqwest::blocking` doesn't conflict with tokio this way. |
| **Telegram bot token leaks** | M | Only read from env var (never config.toml); per memory rule "永遠唔接受 raw secret 喺 chat 入面" — the user puts it in `~/.gundam-halo/.env && chmod 600`. |
| **Respawn loop during dev (frequent backend restarts)** | **H** | The chaos test proves the safeguard. ALSO: docs/SELF-HEALING.md warns "if you're actively developing, set `WATCHDOG_DISABLED=true` in env to skip the watchdog entirely". |
| **Crash log grows unbounded if pruning fails** | L | Defensive: `record_crash()` truncates to last 1000 lines if the file exceeds 1MB. |
| **One-click install_launchd_supervisor fails silently** | M | Returns stderr to frontend; banner shows the error + "See ~/.gundam-halo/logs/install-launchd.log". |

## Success metrics

- 100% of real crashes detected within 90s (60s poll + 30s tolerance).
- 0 false-positive respawn-disabled triggers in 30-day field test
  (track via `crash_log.jsonl` audit; alert if any user sees >0).
- Tray icon dot accurate within 60s of any state change.
- Manual recovery (click "Clear crash log") succeeds < 5s end-to-end.

## Post-merge

- Update `docs/CHANGELOG.md` [Unreleased] with Sprint 43 entry.
- Update `docs/SELF-HEALING.md` with the final architecture + screenshots
  of the 3 banner states.
- Bump `app/__init__.py` `__version__` 0.1.13 → **0.1.14** (PATCH — the
  change is operational, not a new user feature; per Mavis memory rule
  PATCH for non-breaking observability).
- Frontend versions synced to 0.1.14 (3 surfaces).
- Single commit: `feat(watchdog): Sprint 43 — self-healing backend with
  respawn-loop guard + tray health dot + Telegram alert`.
- Run `git status` after commit (per memory rule "git add -A safety check")
  to confirm only expected files are staged.

## Future work (out of Sprint 43)

- **Sprint 45**: auth layer for `/api/system/*` endpoints (currently
  unprotected; benign actions only).
- **Sprint 47**: auto-investigation on crash (scrape launchd.err.log →
  surface top error in banner).
- **M14**: multi-host watchdog coordinator (if user has >1 Mac).
- **M15**: ML-based crash prediction (detect OOM precursors before the
  crash happens).

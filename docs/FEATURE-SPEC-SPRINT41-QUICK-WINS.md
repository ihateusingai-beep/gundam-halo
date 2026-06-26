# Sprint 41 — Wave 1 Quick Wins: MissionCard Activity Colors + Restart Nudge Banner

**Date**: 2026-06-27
**Status**: Draft
**Author**: Mavis
**Priority**: P1 (UX polish, no new infra)
**Depends on**: Sprint 19b (restart handler), Sprint 39 (card dashboard infrastructure)
**Combined scope**: 2 small UX features from the 2026-06-26 design review → user-confirmed Wave 1 quick wins

## Goal

Two small UX polish features that close the most visible
"friction" gaps in the cockpit without introducing any new
infrastructure:

1. **MissionCard Activity Colors** (Feature F) — each
   mission card shows a left-border colour encoding its
   recency (green / yellow / red / grey). The pilot sees
   "which projects need attention" at a glance without
   opening anything.

2. **Restart Nudge Banner** (Feature I) — when the backend
   has scheduled a self-restart (Sprint 19b — `asr_backend`
   or `asr_corrector` changed), the cockpit shows a
   persistent banner with a live countdown + cancel button.
   Today only a one-shot toast appears (VoiceTab.tsx:213),
   which is easy to miss.

Both fit in one sprint. Together they take the cockpit
from "looks pretty" to "actively helpful" without changing
any backend infrastructure.

## Scope

### In scope

**Feature F — MissionCard Activity Colors**:

- `frontend/src/components/gundam/MissionCard.tsx`:
  - Compute `activityTier` from `project.last_activity_at`:
    - `< 1 hour`     → "fresh"    (green)
    - `< 24 hours`    → "recent"   (yellow-cyan blend — use accent)
    - `< 7 days`      → "stale"    (amber)
    - `>= 7 days`     → "dormant"  (rose-red)
    - `null` / archive → "archived" (grey)
  - Render a 4 px coloured left border (CSS `border-l-4`)
    via a new `activity-tier-fresh|recent|stale|dormant|archived`
    class (uses existing theme variables — no new CSS).
  - Add the tier name to the existing status dot row
    (currently shows "ACTIVE" / "ARCHIVED" only).
  - Defensive: if `last_activity_at` is a malformed string,
    fall back to "stale" (no crash).

- `frontend/src/styles/gundam.css`:
  - 5 new class selectors (1 line each) — `[data-theme^="gundam-"] .gundam-mission-card-{tier} { border-left-color: var(--tier-color); }`. Reuses `--success` / `--accent` / `--warning` / `--danger` / `--text-muted` (already in the theme).

- 2 vitest tests:
  - `activityTier("2026-06-27T07:00:00Z", now)` → "fresh"
  - `activityTier("2026-06-20T07:00:00Z", now)` → "stale" (7 days ago)

**Feature I — Restart Nudge Banner**:

- `backend/app/core/restart.py`:
  - Add `_restart_scheduled_at: float | None` module-level
    variable (epoch seconds). Set by `schedule_restart()`;
    cleared by `_set_restart_scheduled(False)`.
  - Expose `get_restart_countdown_s()` → returns float
    seconds until scheduled restart, or None if no
    restart is scheduled. Counts down monotonically based
    on the recorded scheduled_at + delay_s.

- `backend/app/api/voice_config_api.py::get_voice_config()`:
  - Add `restart_scheduled: bool` (already there) +
    `restart_in_seconds: float | None` to the response
    payload. Frontend polls this every second while the
    banner is shown.

- `frontend/src/types/api.ts`:
  - Add `restart_scheduled?: boolean` and
    `restart_in_seconds?: number | null` to the
    `VoiceConfig` type.

- `frontend/src/components/gundam/RestartNudgeBanner.tsx`
  (~120 LoC) — new component. Mirrors the existing
  `BackendOutdatedBanner` pattern.
  - Renders only when `restart_scheduled === true`.
  - Shows a cyan pulsing pill:
    > "Backend restarting in 4s… (new ASR engine)"
  - Live countdown via `requestAnimationFrame` (60 fps,
    negligible CPU) OR `setInterval` (1 Hz — simpler).
  - "Cancel restart" button → calls a new Tauri IPC
    command `cancel_restart()` that calls
    `app.core.restart.cancel_scheduled_restart()`. If
    not in Tauri (web dev), the button shows a
    "Run `pkill -f 'uvicorn app.main:app'`" toast instead.
  - Auto-hides when `restart_in_seconds <= 0` (the
    restart is happening — UI disappears before the
    websocket disconnects).

- `frontend/src/services/halo-restart-nudge.ts` (~70 LoC) —
  singleton subscriber mirroring `halo-watchdog-events.ts`
  pattern. Polls `/voice/config` every 1s while a restart
  is scheduled; subscribers (the banner) re-render.

- `frontend/src-tauri/src/lib.rs`:
  - Add `cancel_restart` IPC command → shells out to
    `curl POST /api/system/cancel-restart` (new endpoint
    below). Defensive: returns success if no restart is
    scheduled (idempotent).

- `backend/app/api/system.py`:
  - New endpoint `POST /api/system/cancel-restart` → calls
    `app.core.restart.cancel_scheduled_restart()`. Returns
    `{ok: true}` always (idempotent — safe to call when no
    restart is scheduled).

- `backend/app/core/restart.py::cancel_scheduled_restart()`:
  - Cancel the pending `asyncio.Task` (use `task.cancel()` +
    catch `asyncio.CancelledError`). Clear the module-level
    flag. Set `_restart_scheduled_at = None`. Logged at
    INFO level so the audit log shows the cancellation.

- `frontend/src/components/layout/CockpitLayout.tsx`:
  - Mount `<RestartNudgeBanner />` above the existing
    `BackendHealthBanner` (both at the top of the cockpit).

- 4 vitest tests:
  - `restart-countdown-ticks-down-by-1-each-second` — set
    scheduled_at to now-2s, verify countdown shows 3s (for
    the default 5s delay).
  - `restart-countdown-shows-null-when-not-scheduled` —
    restart_scheduled=false → restart_in_seconds=null.
  - `cancel-restart-button-calls-ipc` — click → invoke IPC.
  - `banner-hides-when-restart-completed` — restart_in_seconds
    drops to 0 → banner unmounts.

- 3 pytest tests:
  - `schedule_restart_records_scheduled_at_timestamp` —
    `schedule_restart(5.0, ...)` sets `_restart_scheduled_at`
    to ~now; `get_restart_countdown_s()` returns ~5.0.
  - `cancel_scheduled_restart_clears_flag` — after cancel,
    `is_restart_scheduled()` is False, `_restart_scheduled_at`
    is None.
  - `cancel_endpoint_returns_ok` — POST /api/system/cancel-restart
    → 200 + `{ok: true}`.

**Docs**:
- `docs/FEATURE-SPEC-SPRINT41-QUICK-WINS.md` (this file).
- `docs/CHANGELOG.md` [Unreleased] — Sprint 41 entry.
- `docs/DASHBOARD.md` — note the MissionCard activity colours
  + the RestartNudgeBanner placement.

### Out of scope

- **MissionSelect overview page polish** (other cards) —
  MissionCard is the most visible card; ProjectCard and
  the in-page project list get the same tier treatment in
  a follow-up sprint if user feedback warrants.
- **Customisable tier thresholds** — the 1h / 24h / 7d
  thresholds are hardcoded. User can override via a future
  `[ui]` config block; tracked under "Future work".
- **Server-side activity tier computation** — we compute
  tiers in the frontend from `last_activity_at`. The
  backend could pre-compute (saves a few hundred bytes of
  JSON) but it's not worth a new endpoint.
- **In-page "Activity:" label** on the card — only the
  border colour + status dot change. Adding a 3rd row
  would crowd the layout.
- **Cancel-restart via the cockpit menu bar** — only the
  banner button. If the user wants menu integration,
  track under "Future work".

## Why now

Per the 2026-06-26 design review, these two are the highest
"small effort, high visible value" UX wins available. The
backend already has all the data (`last_activity_at` on
`ProjectSummary`, `restart_required` + `restart_scheduled`
flags), so both features are **frontend-only with trivial
backend additions** for the cancel button.

Cost: ~600 LoC across both features (350 frontend + 200
backend + 50 docs). One sprint easily.

## Implementation

### Feature F — activity tier function

```ts
// frontend/src/lib/activity-tier.ts (~30 LoC, new file)

export type ActivityTier = "fresh" | "recent" | "stale" | "dormant" | "archived";

export function activityTier(
  lastActivityAt: string | null,
  now: Date = new Date(),
  archived: boolean = false,
): ActivityTier {
  if (archived) return "archived";
  if (!lastActivityAt) return "dormant";
  const lastMs = Date.parse(lastActivityAt);
  if (Number.isNaN(lastMs)) return "stale";  // defensive
  const ageMs = now.getTime() - lastMs;
  const ONE_HOUR = 60 * 60 * 1000;
  const ONE_DAY = 24 * ONE_HOUR;
  const SEVEN_DAYS = 7 * ONE_DAY;
  if (ageMs < ONE_HOUR) return "fresh";
  if (ageMs < ONE_DAY) return "recent";
  if (ageMs < SEVEN_DAYS) return "stale";
  return "dormant";
}

export const TIER_COLORS: Record<ActivityTier, string> = {
  fresh: "var(--success)",
  recent: "var(--accent)",
  stale: "var(--warning)",
  dormant: "var(--danger)",
  archived: "var(--text-muted)",
};

export const TIER_LABELS: Record<ActivityTier, string> = {
  fresh: "ACTIVE",
  recent: "RECENT",
  stale: "STALE",
  dormant: "DORMANT",
  archived: "ARCHIVED",
};
```

MissionCard usage:

```tsx
const tier = activityTier(project.last_activity_at, new Date(), isArchived);
const tierColor = TIER_COLORS[tier];
// Replace the existing statusColor logic.
const statusLabel = TIER_LABELS[tier];
```

Add to className: `"border-l-4"` + inline style
`{ borderLeftColor: tierColor }`. Done.

### Feature I — restart nudge banner

Backend additions:

```python
# app/core/restart.py — add to module-level state:
_restart_scheduled_at: float | None = None

# In schedule_restart():
_restart_scheduled_at = time.monotonic() + delay_s  # uses monotonic clock

# In _set_restart_scheduled(False):
_restart_scheduled_at = None

# New function:
def get_restart_countdown_s() -> float | None:
    """Seconds until scheduled restart, or None if not scheduled.
    
    Uses time.monotonic() so it's immune to wall-clock changes.
    Returns the original delay value (not negative) if the
    scheduled time has passed — the actual exec happens
    in a background task.
    """
    if _restart_scheduled_at is None:
        return None
    remaining = _restart_scheduled_at - time.monotonic()
    return max(0.0, remaining)

# New function:
def cancel_scheduled_restart() -> bool:
    """Cancel a pending self-restart. Returns True if cancelled,
    False if no restart was scheduled (idempotent)."""
    global _restart_scheduled, _restart_scheduled_reason, _restart_scheduled_at
    was_scheduled = _restart_scheduled
    _restart_scheduled = False
    _restart_scheduled_reason = ""
    _restart_scheduled_at = None
    # Note: we can't cancel the asyncio.Task directly from
    # sync code (it's a different event loop). The Task's
    # CancelledError handler will catch it. This is the same
    # as the "best-effort cancel" pattern Sprint 19b used.
    if was_scheduled:
        logger.info("[halo.restart] scheduled restart cancelled by user")
    return was_scheduled
```

`/voice/config` GET payload addition:

```python
return {
    # ... existing fields ...
    "restart_required": get_restart_required(),
    "restart_scheduled": is_restart_scheduled(),
    "restart_in_seconds": get_restart_countdown_s(),
}
```

Frontend banner:

```tsx
// components/gundam/RestartNudgeBanner.tsx
export function RestartNudgeBanner() {
  const [config, setConfig] = useState<VoiceConfig | null>(null);
  const [cancelling, setCancelling] = useState(false);
  // Poll /voice/config every 1s while restart is scheduled.
  useEffect(() => {
    let cancelled = false;
    let intervalId: ReturnType<typeof setInterval> | null = null;

    async function poll() {
      try {
        const c = await api.getVoiceConfig();
        if (cancelled) return;
        setConfig(c);
        if (c.restart_scheduled) {
          if (intervalId === null) intervalId = setInterval(poll, 1000);
        } else {
          if (intervalId !== null) {
            clearInterval(intervalId);
            intervalId = null;
          }
        }
      } catch (e) {
        // best-effort
      }
    }

    void poll();
    return () => {
      cancelled = true;
      if (intervalId !== null) clearInterval(intervalId);
    };
  }, []);

  if (!config?.restart_scheduled) return null;

  const inSeconds = Math.max(0, Math.ceil(config.restart_in_seconds ?? 0));

  async function handleCancel() {
    setCancelling(true);
    try {
      const res = await tryTauriInvoke<{ ok: boolean }>("cancel_restart");
      if (res === null) {
        // Outside Tauri — show manual instructions toast.
        toast.info("Manual restart required", {
          description: "pkill -f 'uvicorn app.main:app' && cd backend && uv run --project . uvicorn app.main:app",
        });
      } else {
        toast.success("Restart cancelled");
      }
    } finally {
      setCancelling(false);
    }
  }

  return (
    <HudCard pulse>
      <div data-testid="restart-nudge-banner">
        <span>Backend restarting in {inSeconds}s…</span>
        <Button onClick={handleCancel} disabled={cancelling}>
          Cancel
        </Button>
      </div>
    </HudCard>
  );
}
```

Mount in `CockpitLayout.tsx` (above the existing
`BackendHealthBanner`):

```tsx
<RestartNudgeBanner />
<BackendHealthBanner />
<MaybeBackendOutdatedBanner ... />
```

## Test plan

### Frontend (vitest) — 6 tests

`lib/activity-tier.test.ts`:

1. `test_fresh_under_one_hour` — lastActivity = 30 min ago →
   "fresh".
2. `test_stale_seven_days_ago` — lastActivity = 7 days ago →
   "stale".
3. `test_dormant_thirty_days_ago` — lastActivity = 30 days ago
   → "dormant".
4. `test_archived_overrides` — archived=true regardless of
   lastActivity → "archived".
5. `test_null_last_activity_falls_back_to_dormant` — no
   timestamp → "dormant".

`components/gundam/RestartNudgeBanner.test.tsx`:

6. `test_banner_renders_only_when_restart_scheduled` — mock
   getVoiceConfig to return restart_scheduled=true → banner
   visible with countdown; mock false → banner absent.

### Backend (pytest) — 3 tests

`tests/core/test_restart_nudge.py`:

7. `test_schedule_restart_records_scheduled_at` —
   `schedule_restart(5.0, "test")` sets `_restart_scheduled_at`
   to within ±0.5s of `time.monotonic() + 5.0`.
8. `test_get_restart_countdown_s_decrements` — schedule with
   5s delay, sleep 1s, verify countdown returns ~4.0.
9. `test_cancel_scheduled_restart_clears_state` — schedule,
   cancel, verify `is_restart_scheduled()` returns False +
   `get_restart_countdown_s()` returns None.

### Manual smoke (5 minutes)

1. Open the cockpit. See the System Status grid + MissionCard
   roster.
2. Verify the MissionCard activity colours are sensible —
   recently-active projects should have green left-borders;
   old projects should have red.
3. Open Settings → Voice → change the ASR backend from
   `whisper_local` to `yuesub` → click Save.
4. Navigate back to `/` (the cockpit). Within 1 second the
   RestartNudgeBanner appears with a 5-second countdown.
5. Click "Cancel". The banner disappears. Verify with
   `curl localhost:8765/voice/config` that
   `restart_scheduled: false`.
6. (Optional) Repeat steps 3-4 but don't click Cancel. Verify
   the banner disappears when the countdown reaches 0 (the
   backend is restarting — websocket briefly disconnects then
   reconnects).

## Acceptance criteria

1. **Backend `pytest`** (excl slow tts): all green; target
   **1311+** passed (was 1308 baseline).
2. **Frontend `vitest`**: all green; target **92+** passed
   (was 86 baseline).
3. **`tsc --noEmit`**: 0 errors.
4. **`cargo check --tests`**: clean (one new IPC command).
5. **Manual smoke**: the 5-step sequence above passes within
   5 minutes.

## Risks & mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| `last_activity_at` parsing fails on weird formats | L | `activityTier` returns "stale" on `NaN` parse; defensive fallback. |
| RestartNudgeBanner polls every 1s, adds load | M | Polling is gated — interval only starts when `restart_scheduled=true`, stops immediately when false. CPU ~0.001% during a restart. |
| User clicks Cancel after the restart already started | L | `cancel_scheduled_restart()` returns False; banner toast says "Restart already in progress, please wait." |
| `time.monotonic()` vs `time.time()` mismatch | L | We use monotonic for the countdown (immune to clock changes) but `_restart_scheduled_at` is exposed as a relative duration (not an absolute timestamp), so there's no clock-source confusion. |
| Tier thresholds too aggressive for some users | L | Hardcoded for v1. Future work: `[ui]` config block + per-tier override. |
| Cancel button breaks the actual restart on the server | L | `cancel_scheduled_restart` clears the flag but the asyncio task may have already entered `os.execvp`. The Task's `CancelledError` handler catches it cleanly. Worst case: restart happens anyway after cancel — the user can just retry. |

## Success metrics

- MissionCard tier colours render in < 16ms per card (no
  measurable jank when the roster scrolls).
- RestartNudgeBanner countdown ticks smoothly within 100ms
  of the actual backend restart time.
- Cancel button works within 1 round-trip (~50ms on
  localhost).

## Post-merge

- Update `docs/CHANGELOG.md` [Unreleased] with Sprint 41
  entry.
- Update `docs/DASHBOARD.md` — note the new card + banner.
- Bump `app/__init__.py` `__version__` 0.1.16 → **0.1.17**
  (PATCH per Mavis memory rule: small UX polish).
- Frontend versions 0.1.16 → **0.1.17** (3 surfaces).
- Single commit: `feat(ui): Sprint 41 — MissionCard activity
  colours + restart nudge banner (Wave 1 quick wins)`.
- Run `git status` after commit (per memory rule "git add -A
  safety check").

## Future work (out of Sprint 41)

- **Sprint 42**: per-user `[ui]` config block for tier
  thresholds + custom colours.
- **Sprint 43**: same treatment for `ProjectCard` + the
  in-page project list.
- **Sprint 44**: cancel-restart from the menu bar (Tauri
  tray context menu).
- **M10**: dashboard layout v2 — replace the System Status
  grid with a more dynamic layout that includes these
  banners as inline annotations.
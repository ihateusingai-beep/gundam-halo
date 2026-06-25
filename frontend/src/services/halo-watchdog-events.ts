/**
 * halo-watchdog-events — Sprint 43 Tauri event subscriber.
 *
 * The Tauri Rust watchdog emits three events on state transitions:
 *   - `backend-unhealthy`        → yellow banner
 *   - `backend-recovered`        → auto-clear (banner hides)
 *   - `backend-respawn-disabled` → red banner (H-risk: 3+ crashes/hr)
 *
 * This module is the singleton subscriber — mirrors the
 * `services/halo-voice-ws.ts` pattern (module-level singleton,
 * console-debug global on `window.__haloWatchdog`). Components
 * consume the snapshot via `getWatchdogStatus()`; the BackendHealthBanner
 * in `components/gundam/BackendHealthBanner.tsx` re-renders on every
 * transition.
 *
 * In Tauri dev mode the event subscription is a no-op (the
 * `@tauri-apps/api/event` import returns undefined). The banner
 * then falls back to its initial-fetch behaviour (the `get_backend_health`
 * IPC at mount time).
 */

import type { UnlistenFn } from "@tauri-apps/api/event";

/** Health snapshot derived from the watchdog events. */
export interface WatchdogStatus {
  /** "healthy" | "unhealthy" | "respawn-disabled" */
  state: "healthy" | "unhealthy" | "respawn-disabled";
  /** Number of consecutive /api/health failures (resets on success). */
  consecutiveFailures: number;
  /** Crash count in the last 60 minutes (from /api/system/health-detailed). */
  crashCount60m: number;
  /** ISO 8601 timestamp of the most recent crash, or null. */
  lastCrashAt: string | null;
  /** ISO 8601 timestamp of the last state transition, or null. */
  lastTransitionAt: string | null;
}

// Module-level singleton — mirrors halo-voice-ws.ts.
let currentStatus: WatchdogStatus = {
  state: "healthy",
  consecutiveFailures: 0,
  crashCount60m: 0,
  lastCrashAt: null,
  lastTransitionAt: null,
};

const subscribers: Set<(s: WatchdogStatus) => void> = new Set();
let unlisten: UnlistenFn | null = null;
let started = false;

/**
 * Initialize the watchdog event subscriber. Idempotent — calling
 * twice is a no-op.
 *
 * Called automatically on first `getWatchdogStatus()` call (lazy
 * init), but can also be called explicitly from the app's main
 * entry to ensure the events are subscribed before the first render.
 */
export async function initWatchdogEvents(): Promise<void> {
  if (started) return;
  started = true;

  // Tauri only — outside the shell, we stay in the "healthy" default.
  if (typeof window === "undefined") return;
  const w = window as any;
  if (typeof w.__TAURI_INTERNALS__ === "undefined") return;

  try {
    const { listen } = await import("@tauri-apps/api/event");

    const onTransition = (newState: WatchdogStatus["state"], extra: Partial<WatchdogStatus> = {}) => {
      currentStatus = {
        ...currentStatus,
        ...extra,
        state: newState,
        lastTransitionAt: new Date().toISOString(),
      };
      // Console debug (mirror halo-voice-ws).
      // eslint-disable-next-line no-console
      console.debug("[halo-watchdog]", currentStatus);
      for (const cb of subscribers) {
        try {
          cb(currentStatus);
        } catch (e) {
          console.warn("[halo-watchdog] subscriber threw:", e);
        }
      }
    };

    const unlistens: UnlistenFn[] = await Promise.all([
      listen<{
        timestamp: string;
        consecutive_failures: number;
        crash_count_60m: number;
        respawn_disabled: boolean;
      }>("backend-unhealthy", (e) => {
        onTransition("unhealthy", {
          consecutiveFailures: e.payload.consecutive_failures,
          crashCount60m: e.payload.crash_count_60m,
        });
      }),
      listen<{
        timestamp: string;
        consecutive_failures: number;
        crash_count_60m: number;
        respawn_disabled: boolean;
      }>("backend-recovered", () => {
        onTransition("healthy", {
          consecutiveFailures: 0,
        });
      }),
      listen<{
        timestamp: string;
        consecutive_failures: number;
        crash_count_60m: number;
        respawn_disabled: boolean;
      }>("backend-respawn-disabled", (e) => {
        onTransition("respawn-disabled", {
          consecutiveFailures: e.payload.consecutive_failures,
          crashCount60m: e.payload.crash_count_60m,
        });
      }),
    ]);

    unlisten = () => {
      for (const fn of unlistens) {
        try {
          fn();
        } catch {
          // ignore — listener may already be removed
        }
      }
    };

    // Console debug global.
    w.__haloWatchdog = {
      getStatus: () => currentStatus,
      subscribe: (cb: (s: WatchdogStatus) => void) => {
        subscribers.add(cb);
        return () => subscribers.delete(cb);
      },
    };
  } catch (e) {
    console.warn("[halo-watchdog] init failed:", e);
    started = false; // allow retry
  }
}

/** Read the current watchdog status. Lazy-inits the subscriber. */
export function getWatchdogStatus(): WatchdogStatus {
  if (!started) {
    // Fire-and-forget; status stays at the default until events arrive.
    void initWatchdogEvents();
  }
  return currentStatus;
}

/**
 * Subscribe to status transitions. Returns an unsubscribe function.
 * Mirrors the `getVoiceStatus()` + manual listener pattern used by
 * the cockpit layout.
 */
export function subscribeWatchdog(
  cb: (s: WatchdogStatus) => void,
): () => void {
  subscribers.add(cb);
  // Fire current state immediately so the subscriber doesn't have to
  // wait for the next transition to render correctly.
  cb(currentStatus);
  return () => {
    subscribers.delete(cb);
  };
}

/** Test-only — reset module state. Not exported in production builds. */
export function _resetWatchdogForTests(): void {
  currentStatus = {
    state: "healthy",
    consecutiveFailures: 0,
    crashCount60m: 0,
    lastCrashAt: null,
    lastTransitionAt: null,
  };
  subscribers.clear();
  if (unlisten) {
    try {
      unlisten();
    } catch {
      // ignore
    }
    unlisten = null;
  }
  started = false;
  if (typeof window !== "undefined") {
    delete (window as any).__haloWatchdog;
  }
}

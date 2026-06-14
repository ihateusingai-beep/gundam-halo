/**
 * useBackendVersion — poll /api/system/info and detect backend staleness.
 *
 * Returns the live backend's git SHA, build_id, and feature list, plus
 * a derived `outdated` boolean that's true when the backend's git SHA
 * doesn't match the frontend bundle's `__GIT_SHA__` (a new code drop
 * was pulled + the frontend reloaded, but the uvicorn process is
 * still running an older commit).
 *
 * Polling cadence: every 30s, plus an immediate check on mount. The
 * polling stops on tab visibility change (so we don't hammer the
 * backend when the user is on another tab).
 *
 * Usage:
 *   const { backend, outdated, missingFeatures, reload } = useBackendVersion();
 *   if (outdated) <BackendOutdatedBanner onReload={reload} ... />;
 */

import { useCallback, useEffect, useState } from "react";

import { api, ApiError } from "@/lib/api";

export interface BackendInfo {
  app_version: string;
  git_sha: string;
  build_id: number;
  features: string[];
  platform: string;
  python_version: string;
}

/** Build-time SHA injected by vite.config.ts. */
const FRONTEND_GIT_SHA = __GIT_SHA__;

/**
 * The minimum set of feature flags this frontend bundle *requires*
 * from the backend. If the backend is older and doesn't advertise
 * these, we surface a "missing features" warning so the user knows
 * some cockpit interactions may not work as expected.
 */
const REQUIRED_FEATURES = ["voice_streaming"] as const;

export interface UseBackendVersionResult {
  backend: BackendInfo | null;
  loading: boolean;
  error: string | null;
  /** True when the backend's git_sha != the frontend's git_sha. */
  outdated: boolean;
  /**
   * True when the backend is missing features this frontend relies
   * on. The backend may have a matching git_sha (e.g. on a clean
   * pull) but be running an older code drop where some features
   * hadn't landed yet.
   */
  missingFeatures: string[];
  /** Reload the browser page — useful after restarting the backend. */
  reload: () => void;
}

const POLL_MS = 30_000;

export function useBackendVersion(): UseBackendVersionResult {
  const [backend, setBackend] = useState<BackendInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchOnce = useCallback(async () => {
    try {
      const info = (await api.getSystemInfo()) as BackendInfo;
      setBackend(info);
      setError(null);
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : String(e);
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchOnce();
    const id = setInterval(() => {
      if (typeof document === "undefined" || !document.hidden) {
        void fetchOnce();
      }
    }, POLL_MS);
    const onVis = () => {
      if (!document.hidden) void fetchOnce();
    };
    document.addEventListener("visibilitychange", onVis);
    return () => {
      clearInterval(id);
      document.removeEventListener("visibilitychange", onVis);
    };
  }, [fetchOnce]);

  const outdated = !!(
    backend &&
    backend.git_sha !== "unknown" &&
    FRONTEND_GIT_SHA !== "unknown" &&
    backend.git_sha !== FRONTEND_GIT_SHA
  );

  const missingFeatures = backend
    ? REQUIRED_FEATURES.filter((f) => !backend.features.includes(f))
    : [];

  return {
    backend,
    loading,
    error,
    outdated,
    missingFeatures,
    reload: () => window.location.reload(),
  };
}

/**
 * Auth bootstrap — Sprint 48.
 *
 * Side-effect module: on import, checks for `window.__haloApiToken`
 * (set by the Tauri Rust shell at startup via `eval(init_script)`).
 * If present, leaves it alone (the api.ts `authedRequest()` wrapper
 * reads it on every fetch).
 *
 * If absent (e.g. dev mode without Tauri, or backend token missing),
 * the wrapper falls through silently and the protected endpoints
 * will 503/401 — the UI surfaces the error inline.
 *
 * The Tauri Rust shell also exposes `get_api_token` IPC for cases
 * where the bootstrap was missed (e.g. the webview reloaded before
 * the init_script ran). We don't call it here — the init script
 * runs synchronously during `app.setup()`, before any frontend
 * JS executes.
 */

// Diagnostic: log presence at boot so the user can see auth
// is wired even before they hit a protected endpoint.
declare global {
  interface Window {
    __haloApiToken?: string;
  }
}

if (typeof window !== "undefined") {
  const token = window.__haloApiToken;
  if (token && token.length > 0) {
    console.log("[Sprint 48 auth] bearer token loaded into webview.");
  } else {
    console.warn(
      "[Sprint 48 auth] no bearer token on window.__haloApiToken. " +
        "Protected endpoints will fail. " +
        "If you're running via Tauri, run scripts/generate-auth-token.sh " +
        "and restart the Tauri shell.",
    );
  }
}

export {};
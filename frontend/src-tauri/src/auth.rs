//! Sprint 48 — auth bootstrap for the Tauri shell.
//!
//! Reads `$HALO_HOME/.env` at startup, extracts `HALO_API_TOKEN`,
//! and injects it into the webview as `window.__haloApiToken` via
//! an init script. The frontend's `authedRequest()` wrapper reads
//! this global and adds `Authorization: Bearer <token>` to every
//! privileged fetch.
//!
//! If `$HALO_HOME/.env` doesn't exist or `HALO_API_TOKEN` isn't set,
//! the auth bootstrap logs an ERROR and the protected endpoints
//! will refuse every request (fail-closed). The Tauri shell still
//! runs — only the privileged API calls are blocked.
//!
//! Security:
//! - The token is read ONCE at startup; never re-read.
//! - The token is never written to disk from the Tauri side.
//! - The init script uses `JSON.parse()` so escaping is correct.
//! - If the user rotates the token via `scripts/rotate-auth-token.sh`,
//!   they MUST restart the Tauri shell to pick up the new value.

use serde::{Deserialize, Serialize};
use std::fs;
use std::path::PathBuf;
use tauri::{Manager, State};

/// Sprint 48: bearer token storage. Held in process memory only;
/// never serialised to disk. The frontend accesses it via the
/// `get_api_token` IPC command (which returns the value into the
/// webview's `window.__haloApiToken` global).
pub struct AuthState {
    pub token: String,
}

/// Wire shape for the `get_api_token` IPC command. Returns the
/// bearer token so the frontend can store it on `window.__haloApiToken`.
#[derive(Debug, Serialize, Deserialize)]
pub struct ApiTokenResponse {
    pub token: String,
    pub source: String, // "env" | "missing"
}

impl AuthState {
    /// Read the bearer token from `$HALO_HOME/.env`.
    /// Returns None if the file doesn't exist or the line isn't set.
    pub fn load_from_env(home: &PathBuf) -> Option<String> {
        let env_path = home.join(".env");
        if !env_path.is_file() {
            return None;
        }
        let contents = fs::read_to_string(&env_path).ok()?;
        for raw_line in contents.lines() {
            let line = raw_line.trim();
            if line.is_empty() || line.starts_with('#') {
                continue;
            }
            // Format: HALO_API_TOKEN=value (no quoting required for
            // base64 / random tokens; quoted values are stripped).
            if let Some(rest) = line.strip_prefix("HALO_API_TOKEN=") {
                let value = rest.trim().trim_matches('"').trim_matches('\'');
                if !value.is_empty() {
                    return Some(value.to_string());
                }
            }
        }
        None
    }

    /// Bootstrap the auth state. Called from `lib.rs::run()` at startup.
    /// Logs an ERROR if the token is missing (protected endpoints will
    /// 503 — fail-closed).
    pub fn bootstrap(home: &PathBuf) -> Self {
        let token = Self::load_from_env(home).unwrap_or_else(|| {
            eprintln!(
                "[Sprint 48 auth] HALO_API_TOKEN not found in {}/.env. \
                 Protected endpoints (/api/system/*, /voice/run-*, /api/setup/*) \
                 will refuse all requests. Run scripts/generate-auth-token.sh \
                 to create the token, then restart the Tauri shell.",
                home.display()
            );
            String::new()
        });
        AuthState { token }
    }

    /// Inject `window.__haloApiToken` into the webview via an init
    /// script. Called once per app start.
    ///
    /// Skipped when the token is empty (avoids leaking the "missing"
    /// sentinel into the webview where it could confuse the frontend).
    pub fn inject_into_webview(&self, app: &tauri::App) -> Result<(), String> {
        if self.token.is_empty() {
            return Ok(()); // Token missing; error already logged at bootstrap.
        }
        // JSON-encode the token so escaping is unambiguous.
        let token_json = serde_json::to_string(&self.token)
            .map_err(|e| format!("failed to serialise token: {e}"))?;
        let init_script = format!(
            r#"window.__haloApiToken = JSON.parse({token_json:?});"#
        );
        let window = app
            .get_webview_window("main")
            .ok_or_else(|| "main webview window not found".to_string())?;
        window
            .eval(&init_script)
            .map_err(|e| format!("failed to inject auth init script: {e}"))?;
        eprintln!("[Sprint 48 auth] bearer token injected into webview.");
        Ok(())
    }
}

/// Tauri IPC command: return the bearer token to the webview.
/// Called once on app start by `frontend/src/lib/auth-bootstrap.ts`
/// to populate `window.__haloApiToken`.
///
/// Always returns a value (even if missing) so the frontend can
/// distinguish "no auth required" from "auth failed". The source
/// field tells the frontend whether the token is real.
#[tauri::command]
pub fn get_api_token(state: State<'_, AuthState>) -> ApiTokenResponse {
    ApiTokenResponse {
        token: state.token.clone(),
        source: if state.token.is_empty() {
            "missing".to_string()
        } else {
            "env".to_string()
        },
    }
}

/// Resolve $HALO_HOME (mirrors backend/app/core/config_loader.py).
fn resolve_halo_home(app: &tauri::App) -> PathBuf {
    if let Ok(env_val) = std::env::var("HALO_HOME") {
        return PathBuf::from(env_val);
    }
    // Default: ~/.gundam-halo
    if let Some(home_dir) = app.path().home_dir().ok() {
        return home_dir.join(".gundam-halo");
    }
    PathBuf::from(".gundam-halo")
}

/// Sprint 48: top-level bootstrap. Reads the bearer token from
/// $HALO_HOME/.env, registers the AuthState, and injects the
/// token into the webview. Called from `lib.rs::run()` AFTER
/// the app is built but BEFORE the frontend's first IPC call.
pub fn bootstrap_auth(app: &tauri::App) -> Result<(), String> {
    let home = resolve_halo_home(app);
    let state = AuthState::bootstrap(&home);
    state.inject_into_webview(app)?;
    app.manage(state);
    Ok(())
}
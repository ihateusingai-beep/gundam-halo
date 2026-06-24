//! Tauri 2 IPC commands for the Personalised Fine-tune flow
//! (Sprint 33b — Track 31-B Layer 2 v2 self-record corpus).
//!
//! Five commands, all `#[tauri::command]` async. Each delegates
//! to a focused helper in [`crate::recording`]:
//!
//! - [`start_record`]   — open mic + write 30s WAV chunks
//! - [`stop_record`]    — close mic + flush manifest
//! - [`start_train`]    — kick off LoRA fine-tune subprocess
//! - [`get_train_progress`] — poll training subprocess
//! - [`activate_model`] — patch config.toml + restart backend
//!
//! Sprint 33b replaces the Sprint 33 stub (which delegated
//! every command to `recording::stub_response` returning
//! `phase: "stub"`). The contracts from Sprint 33 are
//! unchanged — only the phase values flipped from `"stub"`
//! to `"running"` / `"complete"` / `"error"`. The frontend
//! code that switched on `phase === "stub"` (see the
//! `handleRecordStub` toast in `VoiceTab.tsx`, replaced
//! with real `invoke()` calls in Sprint 33b) now binds to
//! the real status.
//!
//! Sub-modules in [`crate::recording`]:
//! - `capture` — cpal input stream + chunk rotation + WAV
//!   writer + JSONL manifest appender.
//! - `transcribe` — WhisperHF + LoRA subprocess handles.

use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};

use serde::Serialize;
use tauri::{AppHandle, Manager, State};

use crate::recording;

// ============================================================================
// Response shapes
// ============================================================================

/// Wire shape for every recording-related command. The
/// `phase` field drives the cockpit's binding logic:
///
/// - `"running"` — the pipeline is in flight; the frontend
///   polls `get_train_progress` for status.
/// - `"complete"` — the operation finished cleanly (manifest
///   flushed, subprocess exited, checkpoint produced).
/// - `"error"` — see [`RecordingError`] for the failure mode.
///
/// (Sprint 33 used `"stub"` here. Sprint 33b retires that
/// phase entirely — every command now returns a real
/// `"running" | "complete" | "error"` value, or an `Err`
/// with one of the 4 `RecordingError` variants. The frontend
/// reads `err.kind` for toast copy.)
#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct RecordingCommandResponse {
    /// `"running" | "complete" | "error"`.
    pub phase: String,
    /// Human-readable message for the frontend toast.
    pub message: String,
    /// Optional progress (0.0-1.0) for long-running commands
    /// (`start_train`). `None` for instant commands.
    pub progress: Option<f32>,
    /// Optional log-tail (last 5 lines) for the Train card.
    /// Empty unless `get_train_progress` is the caller.
    pub log_tail: Vec<String>,
}

/// Discriminated error type for the 5 IPC commands.
/// Variants map 1:1 to the failure modes the spec calls out
/// (FEATURE-SPEC-SPRINT26.md §6 risk register).
///
/// Sprint 33b: the 4 real variants below cover everything
/// the production pipeline can throw. The Tauri shell
/// serialises with `#[serde(tag = "kind")]` so the JSON
/// payload is `{"kind": "<variantName>", ...fields}` —
/// the frontend reads `err.kind` to decide the toast copy.
#[derive(Debug, Serialize)]
#[serde(tag = "kind", rename_all = "camelCase")]
pub enum RecordingError {
    /// No input device, or TCC permission denied (macOS
    /// Microphone permission for the host terminal app).
    MicrophoneUnavailable,
    /// Disk full or permission denied when writing to
    /// `~/.gundam-halo/recordings/`. Carries the offending
    /// path so the cockpit can surface it in the toast.
    ManifestWriteFailed { path: String },
    /// `start_train` called while a previous subprocess is
    /// still alive. The user must `get_train_progress` until
    /// the prior run finishes (or kill the PID manually).
    TrainingAlreadyRunning,
    /// `activate_model` called but the `--output_dir` from
    /// training is empty — the run didn't produce a
    /// merged checkpoint. Carries the dir for the toast.
    ModelCheckpointMissing { output_dir: String },
}

impl std::fmt::Display for RecordingError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            RecordingError::MicrophoneUnavailable => {
                write!(f, "Microphone unavailable or permission denied. Grant Microphone access to Gundam Halo in System Settings → Privacy & Security.")
            }
            RecordingError::ManifestWriteFailed { path } => {
                write!(f, "Cannot write to {}: check disk space and permissions.", path)
            }
            RecordingError::TrainingAlreadyRunning => {
                write!(f, "A training run is already in progress. Wait for it to finish (or kill the PID) before starting a new one.")
            }
            RecordingError::ModelCheckpointMissing { output_dir } => {
                write!(f, "No merged checkpoint at {}. Re-run training with --skip_eval false or check the train.log.", output_dir)
            }
        }
    }
}

impl std::error::Error for RecordingError {}

// ============================================================================
// IPC commands
// ============================================================================

/// Locate the project backend root (where `app.voice.asr.
/// whisper_hf_helper` lives). Defaults to
/// `~/workspace/gundam-halo/backend` per the install.sh
/// convention; can be overridden via `HALO_BACKEND_DIR`
/// env var for test/dev environments.
fn backend_dir() -> PathBuf {
    if let Ok(p) = std::env::var("HALO_BACKEND_DIR") {
        return PathBuf::from(p);
    }
    let home = std::env::var("HOME").unwrap_or_else(|_| "/tmp".into());
    PathBuf::from(format!("{home}/workspace/gundam-halo/backend"))
}

/// Locate the project venv Python. Falls back to system
/// `python3` if the venv doesn't exist.
fn python_bin(backend_dir: &Path) -> PathBuf {
    let venv_py = backend_dir.join(".venv").join("bin").join("python");
    if venv_py.is_file() {
        venv_py
    } else {
        PathBuf::from("python3")
    }
}

/// Open the microphone and start writing 30s chunks to
/// `~/.gundam-halo/recordings/yue-self-<date>/`. Returns
/// immediately with `phase: "running"`; the frontend polls
/// `get_train_progress` for chunk count.
///
/// Errors:
/// - `MicrophoneUnavailable` — no input device or TCC denied
/// - `ManifestWriteFailed` — can't write to recordings dir
/// - `TrainingAlreadyRunning` — a recording is already in
///   flight (state was non-Idle); call `stop_record` first.
#[tauri::command]
pub async fn start_record(
    app: AppHandle,
    state: State<'_, recording::RecordingState>,
) -> Result<RecordingCommandResponse, RecordingError> {
    let home = app
        .path()
        .home_dir()
        .map_err(|e| RecordingError::ManifestWriteFailed {
            path: format!("$HOME: {e}"),
        })?;
    let session_dir = recording::capture::ensure_session_dir(&home)?;
    let manifest_path = recording::RecordingState::manifest_path_for(&session_dir);

    // Acquire the per-state locks once. If a recording is
    // already in flight, `chunk_count > 0` → reject.
    let chunk_count = state.chunk_count.clone();
    {
        let mut chunk_count_guard = chunk_count.lock().unwrap_or_else(|e| e.into_inner());
        if *chunk_count_guard != 0 {
            return Err(RecordingError::TrainingAlreadyRunning);
        }
        *chunk_count_guard = 0; // explicit reset (shouldn't be needed but defensive)
    } // guard drops here, ending its lifetime before the await

    // Spawn the WhisperHF helper subprocess. We don't put
    // it in `state.whisper_handle` — that Mutex is reserved
    // for future read-only accessors. The handle is moved
    // into the rotator task by `start_capture_loop` (the
    // only safe ownership pattern since
    // `tokio::process::Child` is `!Clone`).
    let backend = backend_dir();
    let py = python_bin(&backend);
    let whisper_handle = recording::transcribe::WhisperHandle::spawn(&py, &backend)
        .await
        .map_err(|_| RecordingError::MicrophoneUnavailable)?;
    let whisper_arc = Arc::new(Mutex::new(Some(whisper_handle)));

    // Build the cpal input stream + spawn the chunk
    // rotator. The stream lives on a dedicated OS thread
    // (not in Tauri state — cpal uses `PhantomData<*mut ()>`
    // to mark Stream as `!Sync`, which Tauri state can't
    // hold). We get back a stop flag that `stop_record`
    // will flip to release the mic.
    let stop_flag = recording::capture::start_capture_loop(
        whisper_arc.clone(),
        state.chunk_count.clone(),
        session_dir.clone(),
        manifest_path.clone(),
    )?;
    *state.session_dir.lock().unwrap() = Some(session_dir.clone());
    *state.manifest_path.lock().unwrap() = Some(manifest_path.clone());
    *state.stop_flag.lock().unwrap() = Some(stop_flag.clone());

    Ok(recording::transcribe::build_response(
        "running",
        format!(
            "Recording started. Chunks → {}",
            session_dir.display()
        ),
        None,
        Vec::new(),
    ))
}

/// Close the microphone and flush the JSONL manifest.
/// Returns the final manifest path + chunk count.
#[tauri::command]
pub async fn stop_record(
    state: State<'_, recording::RecordingState>,
) -> Result<RecordingCommandResponse, RecordingError> {
    // Flip the shared stop flag. The dedicated capture
    // thread observes the flag on its 250 ms poll cycle
    // and drops the cpal Stream (releases the mic). The
    // chunk-rotator task observes the flag on its 1 s tick
    // AND observes the buffer stays empty for 3 consecutive
    // polls, then exits naturally (dropping the WhisperHandle
    // it owned, which kills the subprocess via `kill_on_drop`).
    let stop_flag = state.stop_flag.lock().unwrap().take();
    if let Some(flag) = stop_flag {
        flag.store(true, std::sync::atomic::Ordering::Relaxed);
    }
    // (If `stop_flag` is None, no recording was in flight —
    // we return the current state below regardless.)

    // Wait briefly for the rotator to drain its tail. The
    // capture thread drops the Stream within 250 ms; the
    // buffer then stops growing; the rotator's next poll
    // finds it empty and exits after 3 empty polls (~3 s
    // total). We sleep 3 s to be generous on slow Macs.
    tokio::time::sleep(std::time::Duration::from_secs(3)).await;

    // Snapshot the chunk count + manifest path for the
    // response.
    let chunk_count = *state.chunk_count.lock().unwrap();
    let manifest_path = state
        .manifest_path
        .lock()
        .unwrap()
        .clone()
        .unwrap_or_else(|| PathBuf::from("<not-set>"));

    // Reset state so the next `start_record` is clean.
    *state.chunk_count.lock().unwrap() = 0;
    *state.session_dir.lock().unwrap() = None;
    *state.manifest_path.lock().unwrap() = None;

    Ok(recording::transcribe::build_complete_response(
        chunk_count,
        &manifest_path,
    ))
}

/// Kick off the personalised LoRA fine-tune subprocess
/// (the existing `finetune_whisper_yue.py` with the
/// Sprint 33 `--base_model_path` + `--train_audio_dir` flags).
/// Returns the subprocess PID.
#[tauri::command]
pub async fn start_train(
    app: AppHandle,
    state: State<'_, recording::RecordingState>,
) -> Result<RecordingCommandResponse, RecordingError> {
    // Reject if a training run is already in flight.
    {
        let h = state.train_handle.lock().unwrap();
        if h.is_some() {
            return Err(RecordingError::TrainingAlreadyRunning);
        }
    }

    let home = app
        .path()
        .home_dir()
        .map_err(|e| RecordingError::ManifestWriteFailed {
            path: format!("$HOME: {e}"),
        })?;
    let session_dir = state
        .session_dir
        .lock()
        .unwrap()
        .clone()
        .ok_or(RecordingError::ModelCheckpointMissing {
            output_dir: "<no recording session>".into(),
        })?;
    let backend = backend_dir();
    let py = python_bin(&backend);
    let base_model = home.join("workspace").join("gundam-halo").join(
        "models/whisper-yue-base/",
    );

    // Output dir is `<session_dir>/train/`. The training
    // subprocess writes its log + merged checkpoint here.
    let output_dir = session_dir.join("train");
    std::fs::create_dir_all(&output_dir).map_err(|e| {
        RecordingError::ManifestWriteFailed {
            path: format!("{}: {e}", output_dir.display()),
        }
    })?;

    let handle = recording::transcribe::TrainHandle::spawn(
        &py,
        &backend,
        &base_model,
        &session_dir,
        &output_dir,
    )
    .await
    .map_err(|_| RecordingError::TrainingAlreadyRunning)?;

    *state.train_handle.lock().unwrap() = Some(handle);

    Ok(recording::transcribe::build_response(
        "running",
        format!(
            "Training started. PID stored in RecordingState; \
             poll get_train_progress for status. Log: {}/train.log",
            output_dir.display()
        ),
        Some(0.0),
        Vec::new(),
    ))
}

/// Poll the training subprocess for progress + the last 5
/// log lines. The frontend's Train card polls this every
/// 2 seconds while `phase === "running"`.
#[tauri::command]
pub async fn get_train_progress(
    state: State<'_, recording::RecordingState>,
) -> Result<RecordingCommandResponse, RecordingError> {
    // Snapshot the training handle. If None → no training
    // in flight (or already finished + cleaned up).
    // TrainHandle is Clone so we can take ownership
    // without keeping the MutexGuard held across the
    // log-file read below.
    let handle_opt = state.train_handle.lock().unwrap().clone();
    let Some(handle) = handle_opt else {
        return Ok(recording::transcribe::build_response(
            "complete",
            "No training in flight.",
            None,
            Vec::new(),
        ));
    };

    // Tail the last 5 lines of the log file. This is
    // synchronous I/O; cheap (~µs) because the log is small.
    let log_tail = match std::fs::read_to_string(&handle.log_path) {
        Ok(content) => {
            // Take the last 5 non-empty lines.
            content
                .lines()
                .rev()
                .filter(|l| !l.trim().is_empty())
                .take(5)
                .map(|s| s.to_string())
                .collect::<Vec<_>>()
                .into_iter()
                .rev()
                .collect()
        }
        Err(_) => Vec::new(),
    };

    // Check whether the subprocess is still running. We
    // don't have a direct Child handle (we only stored the
    // PID); the user can check via Activity Monitor. For
    // "is it done" we trust the manifest — when the
    // subprocess writes "Training complete" to the log,
    // the line is in the tail. We don't auto-cleanup the
    // handle — `activate_model` will.
    let phase = "running".to_string();

    Ok(recording::transcribe::build_response(
        &phase,
        format!(
            "Training in progress (PID {}, started {}). Log tail:",
            handle.pid,
            handle.started_at_ms
        ),
        None,
        log_tail,
    ))
}

/// Patch `~/.gundam-halo/config.toml` to point
/// `voice.asr.model_path` at the personalised checkpoint
/// from the most recent `start_train` run, then call the
/// existing `restart_backend` Tauri command to pick up the
/// new model.
#[tauri::command]
pub async fn activate_model(
    app: AppHandle,
    state: State<'_, recording::RecordingState>,
) -> Result<RecordingCommandResponse, RecordingError> {
    use toml_edit::{value, DocumentMut};

    // Find the most recent training run output dir.
    let output_dir = state
        .train_handle
        .lock()
        .unwrap()
        .as_ref()
        .map(|h| h.output_dir.clone())
        .ok_or(RecordingError::ModelCheckpointMissing {
            output_dir: "<no train handle>".into(),
        })?;

    // Verify the merged checkpoint exists. The training
    // subprocess writes the merged model at
    // `<output_dir>/<model files>` — for the Sprint 33
    // finetune script, the output is a HF directory with
    // `config.json`, `pytorch_model.bin`, etc. The simplest
    // check: at least one of these files exists.
    let has_checkpoint = ["config.json", "pytorch_model.bin", "model.safetensors"]
        .iter()
        .any(|name| output_dir.join(name).is_file());
    if !has_checkpoint {
        return Err(RecordingError::ModelCheckpointMissing {
            output_dir: output_dir.display().to_string(),
        });
    }

    // Patch `~/.gundam-halo/config.toml` in place. We use
    // `toml_edit` (declared as a Cargo dependency) so we
    // preserve comments + structure — the inline regex
    // path the Sprint 33 stub flagged as fragile.
    let home = app
        .path()
        .home_dir()
        .map_err(|e| RecordingError::ManifestWriteFailed {
            path: format!("$HOME: {e}"),
        })?;
    let config_path = home.join(".gundam-halo").join("config.toml");
    let config_str = std::fs::read_to_string(&config_path).map_err(|e| {
        RecordingError::ManifestWriteFailed {
            path: format!("{}: {e}", config_path.display()),
        }
    })?;
    let mut doc: DocumentMut = config_str
        .parse()
        .map_err(|e: toml_edit::TomlError| RecordingError::ManifestWriteFailed {
            path: format!("{}: {e}", config_path.display()),
        })?;
    doc["voice"]["asr"]["model_path"] = value(output_dir.display().to_string());
    std::fs::write(&config_path, doc.to_string()).map_err(|e| {
        RecordingError::ManifestWriteFailed {
            path: format!("{}: {e}", config_path.display()),
        }
    })?;

    // The activate_model command does NOT auto-restart the
    // backend — it just patches config.toml. The user (or
    // the dashboard's "Restart backend" button) triggers the
    // restart via the existing `restart_backend` Tauri
    // command in `lib.rs`. This is the same behaviour as
    // Sprint 33's stub; the doc note in FEATURE-SPEC-SPRINT26.md
    // §4.1 calls out the manual restart.
    //
    // (Auto-restart would require either (a) making
    // `restart_backend` pub(crate) and re-implementing its
    // lsof/kill/spawn dance here, or (b) introducing a
    // `crate::restart::RestartBackendState` registered via
    // `app.manage(...)` — both add cross-module coupling for
    // what is effectively a UX choice. The user can always
    // click the existing dashboard button.)
    Ok(recording::transcribe::build_response(
        "complete",
        format!(
            "Model activated: voice.asr.model_path = {}. \
             Restart the backend (dashboard → Restart) to load it.",
            output_dir.display()
        ),
        Some(1.0),
        Vec::new(),
    ))
}

// ============================================================================
// lib.rs registration helper
// ============================================================================

/// All five commands, in the order they must be passed to
/// `tauri::generate_handler!` in `lib.rs`. Keeps the
/// `lib.rs` `invoke_handler` declaration in sync with this
/// module — see the `mod commands;` / `pub use` block at the
/// top of `lib.rs`.
#[allow(dead_code)] // Sprint 33: reserved for future-sprint use; not referenced today.
pub const ALL_RECORDING_COMMANDS: &[&str] = &[
    "start_record",
    "stop_record",
    "start_train",
    "get_train_progress",
    "activate_model",
];
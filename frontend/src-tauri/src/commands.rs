//! Tauri 2 IPC commands for the Personalised Fine-tune flow
//! (Sprint 33 / Track 31-B — Layer 2 v2 self-record corpus).
//!
//! Five commands, all `#[tauri::command]` async, each delegating
//! to the corresponding stub in [`recording`].
//!
//! - [`start_record`]   — open the mic + write 30s chunks
//! - [`stop_record`]    — close the mic + flush the manifest
//! - [`start_train`]    — kick off the LoRA fine-tune subprocess
//! - [`get_train_progress`] — poll the training subprocess
//! - [`activate_model`] — swap `voice.asr.model_path` + restart
//!
//! Scope (Sprint 33, FEATURE-SPEC-SPRINT26.md §4.1):
//!
//! The `recording.rs` module ships as a **stub** in this sprint.
//! The real audio capture + parallel WhisperHFASR transcription
//! + JSONL manifest write pipeline is too heavy for a single
//! sprint on top of the UI work (~+770 LoC across 6 files
//! including 2 NEW Rust files). The IPC command contracts
//! below are pinned so the follow-up sprint can drop in the
//! real `recording.rs` impl without touching the frontend or
//! `lib.rs` (only the `recording` module changes). All five
//! commands currently return a `RecordingError::NotImplemented`
//! with a `phase: "stub"` field so the frontend can show a
//! clear "coming soon" state — see the `handleRecordStub`
//! toast in `VoiceTab.tsx`.
//!
//! The frontend wiring (`frontend/src/routes/settings/VoiceTab.tsx`)
//! already calls `invoke('start_record', ...)` etc. via the
//! stub handler. When the follow-up sprint lands, the only
//! change on the frontend side is replacing the toast with a
//! real status-bound render — no JSX changes, no contract
//! changes.
//!
//! Future-sprint wiring (Sprint 33 follow-up):
//!
//! 1. `recording::start_recording` — uses `cpal` (or `coreaudio`
//!    via the `oboe` crate on iOS, irrelevant on Mac) to open
//!    the default input device at 16kHz mono. Spawns a
//!    background thread that:
//!      a. Captures 30s of audio into a `Vec<i16>`.
//!      b. Writes `chunk-NNN.wav` to
//!         `~/.gundam-halo/recordings/yue-self-<date>/`.
//!      c. Spawns the v0.1.4 WhisperHFASR backend (subprocess
//!         of `backend/.venv/bin/python` + a small Python
//!         script that loads the model once and accepts
//!         audio chunks via stdin/stdout JSON).
//!      d. Appends `{audio_path, text, duration_s, sample_rate}`
//!         to `manifest.jsonl` in the same dir.
//! 2. `recording::stop_recording` — joins the capture thread,
//!    kills the Whisper subprocess, returns the final manifest
//!    row count.
//! 3. `recording::start_training` — spawns the existing
//!    `backend/scripts/finetune_whisper_yue.py` subprocess
//!    with `--base_model_path ~/.gundam-halo/models/whisper-yue-base/`
//!    + `--train_audio_dir <self-record-dir>` + a per-run
//!    `--output_dir`. Returns the subprocess PID so the
//!    frontend can poll `get_train_progress`.
//! 4. `recording::get_training_progress` — tails the training
//!    log file the subprocess writes, returns the last 5 lines
//!    + epoch progress bar.
//! 5. `recording::activate_model` — patches
//!    `~/.gundam-halo/config.toml` (using `toml_edit` or a
//!    manual string-replace on the `voice.asr.model_path`
//!    line) + calls the existing `restart_backend` Tauri
//!    command (in `lib.rs`) to pick up the new model.

use serde::Serialize;

use crate::recording;

// ============================================================================
// Response shapes
// ============================================================================

/// Wire shape for every recording-related command. The
/// `phase` field distinguishes the Sprint 33 stub from the
/// future-sprint real impl — when the frontend sees
/// `phase: "stub"` it shows the "coming soon" toast; when
/// it sees `phase: "running" | "complete" | "error"` it
/// binds to the real status.
#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct RecordingCommandResponse {
    /// `"stub"` in Sprint 33; `"running"`, `"complete"`, or
    /// `"error"` in the follow-up sprint.
    pub phase: String,
    /// Human-readable message for the frontend toast.
    pub message: String,
    /// Optional progress (0.0-1.0) for long-running commands
    /// (`start_train`). `None` for instant commands.
    pub progress: Option<f32>,
    /// Optional log-tail (last 5 lines) for the Train card.
    /// Empty in Sprint 33.
    pub log_tail: Vec<String>,
}

/// Discriminated error type. Variants map 1:1 to the failure
/// modes the spec calls out (FEATURE-SPEC-SPRINT26.md §6
/// risk register). `NotImplemented` is the Sprint 33 stub
/// case; the real variants land with the follow-up sprint.
#[derive(Debug, Serialize)]
#[serde(tag = "kind", rename_all = "camelCase")]
#[allow(dead_code)] // Sprint 33: only the `Ok(...)` stub path is used today; error variants are reserved.
pub enum RecordingError {
    /// Sprint 33 stub marker. The frontend shows the
    /// "coming soon" toast.
    #[serde(rename_all = "camelCase")]
    NotImplemented { command: String, phase: String },
    /// Future-sprint variants (reserved for the real impl):
    /// - `MicrophoneUnavailable` — no input device, or
    ///   permission denied (TCC prompt required).
    /// - `ManifestWriteFailed` — disk full, permission denied
    ///   on `~/.gundam-halo/recordings/`.
    /// - `TrainingAlreadyRunning` — `start_train` called
    ///   while a previous subprocess is still alive.
    /// - `ModelCheckpointMissing` — `activate_model` called
    ///   but the `--output_dir` from training is empty.
    #[serde(other)]
    ReservedForFutureSprint,
}

// ============================================================================
// IPC commands
// ============================================================================

/// Open the microphone and start writing 30s chunks to
/// `~/.gundam-halo/recordings/yue-self-<date>/`. Returns
/// immediately with `phase: "running"`; the frontend polls
/// `get_train_progress` (same polling endpoint, see the
/// design note in [`recording`]) for chunk count + SNR.
///
/// Sprint 33: stub. Returns `phase: "stub"` + the deferred-
/// scope toast message.
#[tauri::command]
pub async fn start_record() -> Result<RecordingCommandResponse, RecordingError> {
    Ok(recording::stub_response("start_record"))
}

/// Close the microphone and flush the JSONL manifest.
/// Returns the final manifest path + row count.
///
/// Sprint 33: stub. Returns `phase: "stub"`.
#[tauri::command]
pub async fn stop_record() -> Result<RecordingCommandResponse, RecordingError> {
    Ok(recording::stub_response("stop_record"))
}

/// Kick off the personalised LoRA fine-tune subprocess
/// (the existing `finetune_whisper_yue.py` with the
/// `--base_model_path` + `--train_audio_dir` flags added
/// in Sprint 33). Returns the subprocess PID.
///
/// Sprint 33: stub. Returns `phase: "stub"`.
#[tauri::command]
pub async fn start_train() -> Result<RecordingCommandResponse, RecordingError> {
    Ok(recording::stub_response("start_train"))
}

/// Poll the training subprocess for progress + the last 5
/// log lines. The frontend's Train card polls this every
/// 2 seconds while `phase === "running"`.
///
/// Sprint 33: stub. Returns `phase: "stub"` + an empty
/// `log_tail`.
#[tauri::command]
pub async fn get_train_progress() -> Result<RecordingCommandResponse, RecordingError> {
    Ok(recording::stub_response("get_train_progress"))
}

/// Patch `~/.gundam-halo/config.toml` to point
/// `voice.asr.model_path` at the personalised checkpoint
/// from the most recent `start_train` run, then call the
/// existing `restart_backend` Tauri command (see `lib.rs`)
/// to pick up the new model.
///
/// Sprint 33: stub. Returns `phase: "stub"`.
#[tauri::command]
pub async fn activate_model() -> Result<RecordingCommandResponse, RecordingError> {
    Ok(recording::stub_response("activate_model"))
}

// ============================================================================
// lib.rs registration helper
// ============================================================================

/// All five commands, in the order they must be passed to
/// `tauri::generate_handler!` in `lib.rs`. Keeps the
/// `lib.rs` `invoke_handler` declaration in sync with this
/// module — see the `mod commands;` / `pub use` block at
/// the top of `lib.rs`.
#[allow(dead_code)] // Sprint 33: reserved for future-sprint use; not referenced today.
pub const ALL_RECORDING_COMMANDS: &[&str] = &[
    "start_record",
    "stop_record",
    "start_train",
    "get_train_progress",
    "activate_model",
];

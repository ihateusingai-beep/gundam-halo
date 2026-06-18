//! Tauri 2 recording + training pipeline (Sprint 33 / Track 31-B).
//!
//! **Sprint 33 status: STUB.** The real recording pipeline is
//! deferred to a follow-up sprint per scope realism (~+770 LoC
//! across 6 files including 2 NEW Rust files is too heavy for
//! a single sprint). See FEATURE-SPEC-SPRINT26.md §4.1 + §5
//! for the full design and the Sprint 33 commit message for
//! the scope decision.
//!
//! What this module ships in Sprint 33:
//!
//! - [`stub_response`] — a single function that every command
//!   in [`crate::commands`] delegates to. Returns a
//!   `RecordingCommandResponse` with `phase: "stub"` + a
//!   human-readable message pointing at the follow-up sprint.
//! - [`RecordingState`] — the in-memory state container the
//!   follow-up sprint will fill in (capture thread handle,
//!   manifest path, training subprocess PID, progress log).
//!   Declared here so the `lib.rs` `app.manage(...)` wiring
//!   compiles today.
//!
//! What this module will ship in the follow-up sprint:
//!
//! - `start_recording` — cpal (or `coreaudio`) mic capture,
//!   30s WAV chunks, parallel WhisperHFASR subprocess, JSONL
//!   manifest write.
//! - `stop_recording` — join capture thread + flush.
//! - `start_training` — `Command::new(...).arg("python")` on
//!   `finetune_whisper_yue.py` with the Sprint 33
//!   `--base_model_path` + `--train_audio_dir` flags.
//! - `get_training_progress` — tail the subprocess log file.
//! - `activate_model` — patch config.toml + call
//!   `restart_backend` from `lib.rs`.
//!
//! The contract for every command is pinned by the rustdoc
//! on each `#[tauri::command]` in [`crate::commands`], so
//! the follow-up sprint doesn't have to revisit the
//! frontend wiring.

use std::sync::Mutex;

use crate::commands::RecordingCommandResponse;

// ============================================================================
// Stub response helper
// ============================================================================

/// Build a `RecordingCommandResponse` for the Sprint 33 stub
/// case. Every command in [`crate::commands`] calls this on
/// the happy path — when the real impl lands, each command
/// will replace its call to `stub_response` with the real
/// `RecordingCommandResponse` constructed from the recording
/// state.
///
/// `command_name` is the IPC command name (matches the
/// `#[tauri::command]` function name in [`crate::commands`]).
pub fn stub_response(command_name: &str) -> RecordingCommandResponse {
    RecordingCommandResponse {
        phase: "stub".to_string(),
        message: format!(
            "{} is not wired to the recording pipeline yet. \
             Sprint 33 (Track 31-B) ships the UI + IPC command \
             contracts; the Tauri Rust recording + training \
             pipeline (this module's real impl) is deferred \
             to a follow-up sprint per scope realism. See the \
             Sprint 33 commit message + \
             docs/FEATURE-SPEC-SPRINT26.md §4.1 for the \
             deferred scope.",
            command_name,
        ),
        progress: None,
        log_tail: Vec::new(),
    }
}

// ============================================================================
// State container (declared today, populated in follow-up sprint)
// ============================================================================

/// In-memory state for the recording + training pipeline.
///
/// `lib.rs` will register an instance of this via
/// `app.manage(RecordingState::default())` once the follow-up
/// sprint lands; for Sprint 33 we ship the type + a
/// `Default` impl so the registration compiles today without
/// any real fields needing to be filled.
///
/// The fields are deliberately `Mutex<Option<...>>` (not
/// bare `Option<...>`) because Tauri's `manage` requires
/// `Send + Sync` and the capture thread + training
/// subprocess both write to the state from background
/// threads.
#[derive(Default)]
#[allow(dead_code)] // Sprint 33: fields are reserved for the follow-up sprint's real impl.
pub struct RecordingState {
    /// Handle to the mic capture thread (follow-up sprint).
    /// `None` when no recording is in flight.
    capture_thread: Mutex<Option<std::thread::JoinHandle<()>>>,
    /// PID of the WhisperHFASR transcription subprocess
    /// (follow-up sprint). `None` when no transcription is
    /// in flight.
    whisper_pid: Mutex<Option<u32>>,
    /// PID of the LoRA fine-tune subprocess (follow-up sprint).
    /// `None` when no training is in flight.
    train_pid: Mutex<Option<u32>>,
    /// Absolute path to the current recording session's
    /// manifest file, e.g.
    /// `/Users/.../.gundam-halo/recordings/yue-self-2026-06-18/manifest.jsonl`.
    /// `None` between sessions.
    manifest_path: Mutex<Option<std::path::PathBuf>>,
    /// Last 5 lines of the training subprocess log (follow-up
    /// sprint). The frontend's Train card reads this via
    /// `get_train_progress`.
    log_tail: Mutex<Vec<String>>,
}

impl RecordingState {
    /// Public constructor so the follow-up sprint can wire
    /// `app.manage(RecordingState::default())` without
    /// needing to expose the field types.
    #[allow(dead_code)] // Sprint 33: reserved for future-sprint use.
    pub fn new() -> Self {
        Self::default()
    }
}

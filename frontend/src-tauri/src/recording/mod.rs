//! Tauri 2 recording + training pipeline (Sprint 33b — Track 31-B).
//!
//! **Sprint 33b replaces the Sprint 33 stub** with the real
//! capture → chunk → transcribe → manifest pipeline. The
//! architecture follows `docs/FEATURE-SPEC-SPRINT26.md` §4.1:
//!
//! 1. `start_recording` opens the default mic via `cpal`,
//!    spawns a chunk-rotator task on the Tokio runtime, and
//!    spawns a long-lived Python WhisperHF subprocess
//!    (`python -m app.voice.asr.whisper_hf_helper`) that
//!    reads chunk paths from stdin and emits JSONL transcripts
//!    to stdout.
//! 2. Every ~30 s the rotator drains the shared i16 buffer,
//!    writes a `chunk-NNN.wav` to
//!    `~/.gundam-halo/recordings/yue-self-<date>/` via `hound`,
//!    ships the path to the WhisperHF subprocess's stdin,
//!    then awaits the matching JSONL line on stdout and
//!    appends it to `manifest.jsonl`.
//! 3. `stop_recording` joins the rotator, kills the subprocess,
//!    flushes the manifest, and returns the final row count.
//!
//! The pipeline state lives in `RecordingState` (registered
//! via `app.manage(...)` in `lib.rs`). Three background actors
//! write to the state: the cpal callback (writes i16 samples),
//! the chunk rotator (drains + ships paths), and the JSONL
//! reader (appends manifest rows). All three go through
//! `Mutex<Option<...>>` fields that Tauri can read from any
//! IPC handler.
//!
//! Sub-modules:
//! - [`capture`] — cpal input stream + chunk rotation + WAV
//!   writer + JSONL manifest appender. The pure-async layer.
//! - [`transcribe`] — WhisperHF subprocess lifecycle (spawn,
//!   write-stdin, read-stdout, kill). The pure-IO layer.
//!
//! Cross-module types (`RecordingCommandResponse`,
//! `RecordingError`, the 5 IPC command handlers themselves)
//! live in the sibling `crate::commands` module — this module
//! only exposes the pipeline primitives that the commands
//! call into.

#![cfg_attr(mobile, allow(unused_imports))]

use std::path::PathBuf;
use std::sync::{Arc, Mutex};

use chrono::Local;

use crate::commands::RecordingCommandResponse;

/// Hard-coded pipeline constants. Kept here so they're easy
/// to grep for when the user wants to tune the chunk length
/// or sample rate. In a future sprint these may move to
/// `~/.gundam-halo/config.toml` under `[recording]` — for now
/// they're locked to the values the voice pipeline uses
/// (`VoiceConfig.sample_rate = 16000`).
pub mod capture;
pub mod transcribe;

pub const SAMPLE_RATE_HZ: u32 = 16_000;
pub const CHANNELS: u16 = 1;
pub const CHUNK_SECONDS: u32 = 30;
/// Number of i16 samples per 30 s chunk at 16 kHz mono.
pub const CHUNK_SAMPLES: usize = (SAMPLE_RATE_HZ as usize) * (CHUNK_SECONDS as usize);

/// The in-memory pipeline state. `lib.rs::run` registers one
/// instance via `app.manage(RecordingState::default())` so
/// the IPC commands can `app.state::<RecordingState>()` to
/// read/write fields from any thread.
///
/// Fields:
///
/// - `capture_stream`: the live `cpal::Stream` while a recording
///   is in flight. `None` when no recording is happening.
///   `Drop`ping the stream stops capture and releases the
///   mic.
/// - `chunk_count`: monotonically increasing counter; each
///   chunk the rotator writes is named `chunk-{count:03}.wav`.
/// - `session_dir`: absolute path to the current recording
///   session's directory (e.g.
///   `/Users/.../.gundam-halo/recordings/yue-self-2026-06-23/`).
///   `None` between sessions.
/// - `manifest_path`: absolute path to the current
///   `manifest.jsonl`. `None` between sessions.
/// - `whisper_handle`: PID + stdin handle for the running
///   WhisperHF helper subprocess. `None` when no helper is
///   running.
/// - `train_handle`: PID + log-tail for the running LoRA
///   fine-tune subprocess. `None` when no training is
///   running.
/// - `last_5_log_lines`: rolling buffer of the last 5 lines
///   of the training subprocess log. Surfaced via
///   `get_train_progress`.
///
/// Fields are wrapped in `Arc<Mutex<T>>` (or
/// `Arc<AtomicBool>` for the stop flag) so the capture-
/// thread task + the rotator task + the IPC handler can
/// each hold their own clone of the reference. This is the
/// canonical Tauri-state pattern for shared mutable state
/// across threads — Tauri's `app.manage(...)` returns a
/// single `State<'_, T>` to each IPC handler call, but the
/// inner values need `Send + Sync` so background tasks
/// spawned from inside the handler can keep a handle to
/// them.
///
/// Lock-contention note: `whisper_handle` and `train_handle`
/// are written by `start_record` / `start_train` (taken by
/// the rotator / training subprocess respectively) and read
/// only inside the same call chain. `get_train_progress`
/// reads `last_5_log_lines` + `train_handle` only — never
/// `whisper_handle`. So no live-reader-blocks-rotator case
/// in the v0.1.6 surface.
#[derive(Default, Clone)]
pub struct RecordingState {
    /// Shared stop flag. `start_record` puts `Some(flag)`
    /// here and clones the `Arc` into the dedicated capture
    /// thread + the rotator task. `stop_record` takes the
    /// flag and flips it to `true`; both threads observe
    /// the flip on their next poll (≤ 1 s for the rotator,
    /// ≤ 250 ms for the capture thread) and exit cleanly.
    pub(crate) stop_flag: Arc<Mutex<Option<Arc<std::sync::atomic::AtomicBool>>>>,
    pub(crate) chunk_count: Arc<Mutex<u32>>,
    pub(crate) session_dir: Arc<Mutex<Option<PathBuf>>>,
    pub(crate) manifest_path: Arc<Mutex<Option<PathBuf>>>,
    pub(crate) whisper_handle: Arc<Mutex<Option<transcribe::WhisperHandle>>>,
    pub(crate) train_handle: Arc<Mutex<Option<transcribe::TrainHandle>>>,
    pub(crate) last_5_log_lines: Arc<Mutex<Vec<String>>>,
}

impl RecordingState {
    /// Public constructor so `lib.rs` can register an
    /// instance via `app.manage(RecordingState::default())`.
    /// All fields are `None` until the first
    /// `start_recording` / `start_train` call.
    pub fn new() -> Self {
        Self::default()
    }

    /// Compute (or reuse) the session directory path. Called
    /// once at the start of every recording session.
    pub fn session_dir_for(&self, home: &std::path::Path) -> PathBuf {
        let dir = home
            .join("recordings")
            .join(format!("yue-self-{}", Local::now().format("%Y-%m-%d")));
        dir
    }

    /// Manifest path is always `<session_dir>/manifest.jsonl`.
    pub fn manifest_path_for(session_dir: &std::path::Path) -> PathBuf {
        session_dir.join("manifest.jsonl")
    }
}

// `capture_stream` holds a Box<dyn Any> instead of the
// concrete `cpal::Stream` because `Stream` isn't `Sync` (it's
// a platform handle that's `Send` but not safely shareable
// across threads). The capture thread owns the stream
// exclusively; the IPC handler only ever sees `Option<...>`.
// The `Any + Send + Sync` bound lets us drop the stream from
// any thread (Tauri state cleanup runs on the runtime thread,
// not the capture thread).
//
// In practice we never read this field — it's owned by the
// rotator task via the same Mutex<Option<...>> pattern; the
// IPC handlers only check `chunk_count` + `manifest_path` to
// report progress. We keep it here as a backstop so
// `stop_recording` can drop the stream from any thread.

// Re-export the response helper so `commands.rs` can build
// the same shape from any of the 5 handlers without
// duplicating the field-mapping logic. Defined in
// `transcribe.rs` (where the `RecordingCommandResponse` type
// itself lives in `commands.rs`); re-exported via the
// `pub use transcribe::{build_response, ...}` block below.

// ---------------------------------------------------------------------------
// RecordingCommandResponse — thin re-export so `commands.rs`
// doesn't need to import from `crate::commands` AND
// `crate::recording`. Single source of truth: see
// `crate::commands::RecordingCommandResponse` for the wire
// schema.
// ---------------------------------------------------------------------------

pub use crate::commands::RecordingCommandResponse as Response;

// Re-export the constants and helpers so callers can do
// `use crate::recording::{CHUNK_SAMPLES, build_response};`
// instead of nested paths. `__all__` isn't a macro in 2018+
// edition — the convention is `pub use` for explicit re-
// exports. The names below are the public surface of the
// recording module.
pub use capture::{
    append_manifest_line,
    ensure_session_dir,
    start_capture_loop,
    write_wav_i16,
};
pub use transcribe::{
    build_complete_response,
    build_error_response,
    build_response,
    TrainHandle,
    WhisperHandle,
};

// `Response` is an alias for `RecordingCommandResponse` from
// `crate::commands` — re-exported via the `use` at the top
// of this module. No additional re-export needed here.
//
// The constants `SAMPLE_RATE_HZ`, `CHANNELS`, `CHUNK_SECONDS`,
// `CHUNK_SAMPLES` are declared `pub` at the top of this file
// (so they're visible to `capture::start_capture_loop` via
// `super::` imports). External callers should reference
// them as `crate::recording::SAMPLE_RATE_HZ` etc.
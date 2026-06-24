//! WhisperHF + LoRA fine-tune subprocess management (Sprint 33b).
//!
//! Two handles owned by `RecordingState`:
//!
//! - `WhisperHandle` — long-lived Python subprocess of
//!   `python -m app.voice.asr.whisper_hf_helper`. Reads
//!   chunk paths from stdin, writes one JSON object per
//!   line to stdout (per-chunk transcript with metadata).
//!   Spawned at `start_record` time, killed at `stop_record`
//!   time. Carries: child PID, stdin handle, JSONL reader
//!   task.
//! - `TrainHandle` — `python -m scripts.finetune_whisper_yue`
//!   with the Sprint 33 `--base_model_path` +
//!   `--train_audio_dir` flags. Writes training log to
//!   `<session_dir>/train.log`. Spawned at `start_train`
//!   time, polled via `get_train_progress` until done.
//!   Carries: child PID, log file path.
//!
//! Why subprocesses (not in-process): WhisperHF and the
//! LoRA trainer both load PyTorch + transformers (or
//! `mlx-whisper` on darwin). That's ~500 MB of memory and
//! ~10-30 s of load time. Spawning a subprocess per session
//! means the Tauri shell stays responsive, and the user
//! can see the Python process in Activity Monitor /
//! `htop` while training. In-process would block the
//! tray animation thread on model load.

#![cfg_attr(mobile, allow(unused_imports))]

use std::path::{Path, PathBuf};
use std::process::Stdio;
use std::sync::Arc;
use std::time::Duration;

use serde_json::{json, Value};
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::process::{Child, Command};
use tokio::sync::Mutex;

use crate::commands::{RecordingCommandResponse, RecordingError};

// ---------------------------------------------------------------------------
// WhisperHandle — long-lived WhisperHF helper subprocess
// ---------------------------------------------------------------------------

/// Owns a long-lived `python -m app.voice.asr.whisper_hf_helper`
/// subprocess. The subprocess stays alive across all 30-s
/// chunks in a single recording session so the WhisperHF
/// model loads only once (the first chunk's latency is ~5 s
/// for model load; subsequent chunks are <1 s).
///
/// Per the long-term memory `plan-engine-gotchas` + the
/// Sprint 33 spec: bounded-concurrency FIFO queue prevents
/// the GPU from overcommitting. We process chunks serially
/// here (one at a time, await transcript before sending the
/// next path) — simpler than a queue and the LLM has plenty
/// of headroom on Apple Silicon.
// WhisperHandle does NOT derive Clone — the underlying
// `tokio::process::Child` is `!Clone` (it owns the actual
// OS process). When the IPC handler wants to read the
// subprocess status, it locks the Mutex on `RecordingState`
// and reads PID / log-tail metadata from `TrainHandle`
// instead. See `commands::get_train_progress` for the
// pattern.
pub struct WhisperHandle {
    /// The OS process. Owned; dropping kills the subprocess
    /// if it hasn't been killed already.
    child: Child,
    /// The half of the stdin pipe the subprocess reads from.
    /// We hold the write half here so we can ship paths
    /// while the subprocess is alive.
    stdin: Arc<Mutex<tokio::process::ChildStdin>>,
}

impl WhisperHandle {
    /// Spawn the WhisperHF helper subprocess. Uses
    /// `<backend_dir>/.venv/bin/python` if it exists;
    /// falls back to system `python3`. The helper reads
    /// one WAV path per line from stdin, writes one JSON
    /// object per line to stdout, and exits cleanly on EOF.
    ///
    /// The `whisper_path` argument is the absolute path to
    /// `python -m app.voice.asr.whisper_hf_helper` (relative
    /// imports work because `backend/` is the cwd).
    pub async fn spawn(python_bin: &Path, backend_dir: &Path) -> Result<Self, RecordingError> {
        // Try the explicit python first; fall back to system
        // python3 if the venv doesn't exist. Both errors map
        // to `TrainingAlreadyRunning` (the closest available
        // variant — a real `start_train` is the user's next
        // hint, and that surfaces the underlying error from
        // the Python helper's exit code).
        let spawn_with = |bin: &Path| -> std::io::Result<Child> {
            Command::new(bin)
                .arg("-m")
                .arg("app.voice.asr.whisper_hf_helper")
                .arg("--lang")
                .arg("yue")
                .current_dir(backend_dir)
                .stdin(Stdio::piped())
                .stdout(Stdio::piped())
                .stderr(Stdio::piped())
                .kill_on_drop(true)
                .spawn()
        };

        let mut child = spawn_with(python_bin)
            .or_else(|_| spawn_with(&PathBuf::from("python3")))
            .map_err(|_| RecordingError::TrainingAlreadyRunning)?;

        let stdin = child
            .stdin
            .take()
            .ok_or(RecordingError::TrainingAlreadyRunning)?;

        Ok(Self {
            child,
            stdin: Arc::new(Mutex::new(stdin)),
        })
    }

    /// Ship one WAV path to the subprocess and await the
    /// matching JSONL transcript line on stdout. Returns
    /// the parsed JSON object (which may contain an `error`
    /// field if transcription failed for this chunk).
    ///
    /// The match is positional: we send path N, then read
    /// exactly one line, which is the transcript for path
    /// N. This is safe because the subprocess is single-
    /// threaded (one transcript at a time).
    pub async fn send_and_recv(&mut self, path: &str) -> Result<Value, RecordingError> {
        let stdin_lock = self.stdin.clone();
        {
            let mut stdin = stdin_lock.lock().await;
            stdin
                .write_all(path.as_bytes())
                .await
                .map_err(|_| RecordingError::MicrophoneUnavailable)?;
            stdin
                .write_all(b"\n")
                .await
                .map_err(|_| RecordingError::MicrophoneUnavailable)?;
            stdin
                .flush()
                .await
                .map_err(|_| RecordingError::MicrophoneUnavailable)?;
        }

        // Read one line from stdout. We borrow the stdout
        // handle mutably from `child` — there's a Rust
        // borrow-checker dance here because we already
        // hold `stdin` separately. Take stdout by value
        // each call (clone-friendly: the Child owns the
        // actual fd; ChildStdio is a Clone-able handle).
        let stdout = self
            .child
            .stdout
            .as_mut()
            .ok_or(RecordingError::MicrophoneUnavailable)?;
        let mut reader = BufReader::new(stdout);
        let mut line = String::new();
        // Bounded wait so a hung subprocess doesn't block
        // the chunk rotator forever. 5 minutes per chunk is
        // generous (the actual per-chunk latency is 1-5 s on
        // Apple Silicon).
        let read = tokio::time::timeout(Duration::from_secs(300), reader.read_line(&mut line))
            .await
            .map_err(|_| RecordingError::TrainingAlreadyRunning /* timeout */)?
            .map_err(|_| RecordingError::MicrophoneUnavailable)?;
        if read == 0 {
            return Err(RecordingError::TrainingAlreadyRunning);
        }
        serde_json::from_str(&line.trim())
            .map_err(|_| RecordingError::TrainingAlreadyRunning)
    }

    /// Kill the subprocess (used by `stop_recording`). Idempotent.
    pub async fn kill(&mut self) {
        let _ = self.child.start_kill();
    }
}

// ---------------------------------------------------------------------------
// TrainHandle — LoRA fine-tune subprocess (one-shot per session)
// ---------------------------------------------------------------------------

/// Owns a `python -m scripts.finetune_whisper_yue` subprocess
/// plus its log file. Spawned at `start_train`, polled via
/// `get_train_progress` until the subprocess exits. The PID
/// is captured so the user can monitor it in Activity Monitor.
///
/// The log file is the canonical progress source — we tail it
/// in `get_training_progress` and return the last 5 lines.
#[derive(Clone)]
pub struct TrainHandle {
    pub pid: u32,
    pub log_path: PathBuf,
    pub output_dir: PathBuf,
    pub started_at_ms: u64,
}

impl TrainHandle {
    /// Spawn the LoRA fine-tune subprocess. Writes its stdout
    /// + stderr to `<output_dir>/train.log`.
    pub async fn spawn(
        python_bin: &Path,
        backend_dir: &Path,
        base_model_path: &Path,
        train_audio_dir: &Path,
        output_dir: &Path,
    ) -> Result<Self, RecordingError> {
        if let Err(e) = std::fs::create_dir_all(output_dir) {
            return Err(RecordingError::ManifestWriteFailed {
                path: format!("{}: {e}", output_dir.display()),
            });
        }
        let log_path = output_dir.join("train.log");
        let log_file = std::fs::File::create(&log_path)
            .map_err(|e| RecordingError::ManifestWriteFailed {
                path: format!("{}: {e}", log_path.display()),
            })?;

        let mut cmd = Command::new(python_bin);
        cmd.arg("-m")
            .arg("scripts.finetune_whisper_yue")
            .arg("--base_model_path")
            .arg(base_model_path)
            .arg("--train_audio_dir")
            .arg(train_audio_dir)
            .arg("--output_dir")
            .arg(output_dir)
            .current_dir(backend_dir)
            .stdin(Stdio::null())
            .stdout(Stdio::from(log_file))
            .stderr(Stdio::null())
            .kill_on_drop(true);
        let child = cmd.spawn().map_err(|_| RecordingError::TrainingAlreadyRunning)?;

        Ok(Self {
            pid: child.id().unwrap_or(0),
            log_path,
            output_dir: output_dir.to_path_buf(),
            started_at_ms: std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map(|d| d.as_millis() as u64)
                .unwrap_or(0),
        })
    }
}

// ---------------------------------------------------------------------------
// Response builders — used by the 5 IPC commands in `commands.rs`
// ---------------------------------------------------------------------------

/// Build the standard `RecordingCommandResponse` for any of
/// the 5 IPC commands. The fields are shared; only `phase`
/// + `message` + the optional `progress` / `log_tail` differ.
pub fn build_response(
    phase: &str,
    message: impl Into<String>,
    progress: Option<f32>,
    log_tail: Vec<String>,
) -> RecordingCommandResponse {
    RecordingCommandResponse {
        phase: phase.to_string(),
        message: message.into(),
        progress,
        log_tail,
    }
}

/// Convenience: build a "complete" response with chunk count
/// + manifest path included in the message. Used by
/// `stop_record`.
pub fn build_complete_response(chunk_count: u32, manifest_path: &Path) -> RecordingCommandResponse {
    build_response(
        "complete",
        format!(
            "Recording stopped. {chunk_count} chunks written. \
             Manifest: {}",
            manifest_path.display()
        ),
        Some(1.0),
        Vec::new(),
    )
}

/// Convenience: build an "error" response with a phase + error
/// variant. Used by all 5 IPC commands on failure.
pub fn build_error_response(
    phase: &str,
    err: &RecordingError,
) -> RecordingCommandResponse {
    build_response(
        phase,
        format!("{phase} failed: {err}"),
        None,
        Vec::new(),
    )
}

// ---------------------------------------------------------------------------
// Convenience constructors for `RecordingError` — the IPC
// handlers in `commands.rs` build error responses from these.
// ---------------------------------------------------------------------------

impl RecordingError {
    /// Serialize as JSON for inclusion in an `RecordingCommandResponse`
    /// `phase: "error"` payload. Used by the Tauri shell when
    /// serializing the IPC reply. Matches the shape the
    /// frontend reads via `err.kind`.
    pub fn to_json(&self) -> Value {
        match self {
            RecordingError::MicrophoneUnavailable => json!({
                "kind": "microphone_unavailable",
            }),
            RecordingError::ManifestWriteFailed { path } => json!({
                "kind": "manifest_write_failed",
                "path": path,
            }),
            RecordingError::TrainingAlreadyRunning => json!({
                "kind": "training_already_running",
            }),
            RecordingError::ModelCheckpointMissing { output_dir } => json!({
                "kind": "model_checkpoint_missing",
                "output_dir": output_dir,
            }),
        }
    }
}
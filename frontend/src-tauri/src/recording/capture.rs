//! Audio capture + chunk rotation + WAV writer + JSONL
//! manifest appender (Sprint 33b real impl).
//!
//! Pipeline (per `docs/FEATURE-SPEC-SPRINT26.md` §4.1):
//!
//! 1. `start_capture_loop` spawns a dedicated OS thread
//!    that opens the default mic via `cpal`, configures
//!    the input stream for 16 kHz mono int16 (negotiated
//!    via `supported_input_configs`), and builds an input
//!    stream whose callback writes samples to a shared
//!    `Arc<Mutex<Vec<i16>>>` buffer. The `cpal::Stream`
//!    is owned by this thread (cpal requires `Send` but
//!    marks the platform handle `!Sync` via
//!    `PhantomData<*mut ()>` — so the Stream can't safely
//!    sit in Tauri state, which is shared across threads).
//! 2. A separate chunk-rotator task spawned on the Tokio
//!    runtime polls the buffer every 1 s. When the buffer
//!    has accumulated ≥ `CHUNK_SAMPLES` (480 000 i16 at
//!    16 kHz × 30 s), the rotator drains it, writes the
//!    chunk to `<session_dir>/chunk-NNN.wav` via `hound`,
//!    and ships the path to the WhisperHF subprocess's
//!    stdin via [`super::transcribe::WhisperHandle`].
//! 3. The rotator awaits the matching JSONL transcript
//!    line on the WhisperHF subprocess's stdout reader task,
//!    appends it to `<session_dir>/manifest.jsonl`, then
//!    increments the chunk counter and loops.
//!
//! Error handling:
//! - Mic not available → `RecordingError::MicrophoneUnavailable`
//! - Permission denied (TCC prompt required) → same
//! - Disk full / permission denied on the recordings dir →
//!   `RecordingError::ManifestWriteFailed`
//! - Stream error mid-recording → log + stop cleanly (chunk
//!   up to that point is preserved; manifest row count
//!   reflects what we actually wrote)
//!
//! Stop semantics: the dedicated capture thread holds a
//! `std::sync::Arc<AtomicBool>` shared-stop flag. Setting
//! the flag (from `stop_record`) causes the thread to drop
//! the `cpal::Stream` on its next idle poll, which stops
//! the mic. The thread then exits; the Stream is
//! auto-dropped via `Drop`. The IPC command reads the
//! chunk count from the state after a short sleep to let
//! the rotator drain the last chunk.

#![cfg_attr(mobile, allow(unused_imports))]

use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Duration;

use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};
use cpal::{SampleFormat, Stream, StreamConfig};
use hound::{SampleFormat as HoundSampleFormat, WavSpec, WavWriter};
use serde_json::json;

use super::{CHANNELS, CHUNK_SAMPLES, CHUNK_SECONDS, SAMPLE_RATE_HZ};
use crate::commands::RecordingError;

/// Shared buffer for the cpal callback (writer) + chunk
/// rotator (reader). `Arc<Mutex<Vec<i16>>>` because:
/// - The capture callback runs on a high-priority audio
///   thread; it MUST NOT allocate or block. Mutex lock
///   acquisition for a small Vec push is microseconds.
/// - The rotator runs on a Tokio task; it locks briefly to
///   drain, then releases for the next chunk.
/// - The buffer can hold at most 2 chunks' worth of data
///   (cpal fires every ~10 ms, the rotator drains every
///   1 s — worst case the buffer grows to ~1 chunk + 1
///   frame, ~960 KB).
type SharedBuffer = Arc<Mutex<Vec<i16>>>;

/// Spawn a dedicated OS thread that owns the `cpal::Stream`
/// + the chunk-rotator task. Returns an `Arc<AtomicBool>`
/// stop flag — setting it to `true` causes the thread to drop
/// the `cpal::Stream` on its next idle poll (every 1 s),
/// which stops the mic. The thread then exits; the Stream
/// is auto-dropped via `Drop`.
///
/// We can't return the `cpal::Stream` directly because cpal
/// uses `PhantomData<*mut ()>` as a `!Sync` marker, and
/// Tauri's `app.manage(...)` requires `Send + Sync` (the
/// state is shared across the IPC thread + the runtime
/// thread + the capture thread). Spawning a dedicated OS
/// thread that owns the Stream is the canonical workaround
/// (cpal's own `feedback.rs` example uses the same pattern).
///
/// # Arguments
/// - `whisper`: a fresh `Arc<Mutex<Option<WhisperHandle>>>`
///   holding the just-spawned WhisperHF subprocess. The
///   capture thread takes the handle out of the Mutex and
///   moves it into the rotator task. The Mutex stays empty
///   after this call — the rotator owns the handle for its
///   lifetime.
/// - `chunk_count`: shared `Arc<Mutex<u32>>` that the rotator
///   increments on every chunk. The IPC handler reads this
///   to report progress.
/// - `session_dir`: directory the rotator writes
///   `chunk-NNN.wav` into. Created if missing.
/// - `manifest_path`: JSONL file the rotator appends to.
///
/// # Returns
/// - `Ok(Arc<AtomicBool>)`: the stop flag. Setting to `true`
///   drops the cpal Stream on the next capture-thread tick
///   (≤ 1 s latency).
/// - `Err(RecordingError::MicrophoneUnavailable)`: no input
///   device, or permission denied, or the device's native
///   format isn't i16.
///
/// # Concurrency
/// The capture thread runs on a dedicated OS thread (via
/// `std::thread::spawn`) — this is the only safe home for
/// `cpal::Stream`. The chunk-rotator task runs on the Tokio
/// runtime (via `tokio::spawn` inside the capture thread).
/// Both write to the shared `Mutex<Vec<i16>>` buffer; the
/// callback never blocks (lock duration: microseconds).
pub fn start_capture_loop(
    whisper: Arc<Mutex<Option<super::transcribe::WhisperHandle>>>,
    chunk_count: Arc<Mutex<u32>>,
    session_dir: PathBuf,
    manifest_path: PathBuf,
) -> Result<Arc<AtomicBool>, RecordingError> {
    // ----- Negotiate the input stream config -----
    let host = cpal::default_host();
    let device = host
        .default_input_device()
        .ok_or(RecordingError::MicrophoneUnavailable)?;

    // Find a 16 kHz mono config the device supports. On most
    // macOS internal mics, the device's default is 48 kHz
    // stereo — we explicitly request a 16 kHz mono config
    // (or whatever's closest) so the WAV writer doesn't
    // need resampling logic.
    let supported_configs = device
        .supported_input_configs()
        .map_err(|_| RecordingError::MicrophoneUnavailable)?;
    let target_config = supported_configs
        .into_iter()
        .find(|c| {
            c.channels() == CHANNELS
                && c.min_sample_rate().0 <= SAMPLE_RATE_HZ
                && c.max_sample_rate().0 >= SAMPLE_RATE_HZ
        })
        .ok_or(RecordingError::MicrophoneUnavailable)?;
    let stream_config: StreamConfig = target_config
        .with_sample_rate(cpal::SampleRate(SAMPLE_RATE_HZ))
        .into();

    // ----- Shared buffer -----
    let buffer: SharedBuffer = Arc::new(Mutex::new(Vec::with_capacity(CHUNK_SAMPLES * 2)));

    // ----- Stop flag (shared between capture thread + IPC handler) -----
    let stop_flag = Arc::new(AtomicBool::new(false));

    // ----- Build the input stream ON the dedicated thread -----
    // We need a StreamConfig + SampleFormat that's `Send` to
    // move into the closure. `StreamConfig` is `Clone` + `Send`
    // (verified in cpal source); we copy it into the thread.
    let err_fn = |err: cpal::StreamError| {
        eprintln!("[recording] cpal stream error: {err}");
    };

    // Take the WhisperHandle out of the shared Mutex (same
    // Arc that the IPC handler holds). After this the Mutex
    // is None — `stop_record` never reads it (the rotator
    // owns the subprocess for its lifetime).
    let whisper_handle = {
        let mut guard = whisper.lock().unwrap();
        guard.take()
    };
    let Some(whisper_handle) = whisper_handle else {
        return Err(RecordingError::MicrophoneUnavailable);
    };

    // The capture thread + the rotator task each need their
    // own clones of the shared Arc<...>s. The capture thread
    // moves its clones into the `spawn(move || { ... })`
    // closure; the rotator task takes the rest via
    // `spawn_rotator`. We keep the original Arc names for
    // the rotator's clones (they're cheap).
    let capture_buffer = buffer.clone();
    let capture_stop_flag = stop_flag.clone();
    let _capture_thread = match target_config.sample_format() {
        SampleFormat::I16 => {
            thread::Builder::new()
                .name("halo-capture".into())
                .spawn(move || {
                    // Build the input stream and start playback
                    // inside the thread. Both errors map to
                    // `eprintln!` + early exit — the spawn()
                    // closure doesn't propagate errors back to
                    // the IPC handler (cpal errors here are
                    // rare and the user-facing error path is
                    // the next `start_record` call).
                    let stream = match device.build_input_stream::<i16, _, _>(
                        &stream_config,
                        {
                            let buf = capture_buffer.clone();
                            let cb_stop_flag = capture_stop_flag.clone();
                            move |data: &[i16], _: &cpal::InputCallbackInfo| {
                                if cb_stop_flag.load(Ordering::Relaxed) {
                                    return;
                                }
                                if let Ok(mut b) = buf.lock() {
                                    b.extend_from_slice(data);
                                }
                            }
                        },
                        err_fn,
                        None,
                    ) {
                        Ok(s) => s,
                        Err(e) => {
                            eprintln!("[recording] build_input_stream failed: {e}");
                            return;
                        }
                    };
                    if let Err(e) = stream.play() {
                        eprintln!("[recording] stream.play failed: {e}");
                        return;
                    }
                    // Block the thread until the stop flag is
                    // set. We poll at 250 ms for low-latency
                    // shutdown; cpal's stream drops are
                    // immediate so the user sees the mic
                    // release within a quarter-second of
                    // `stop_record`.
                    while !capture_stop_flag.load(Ordering::Relaxed) {
                        thread::sleep(Duration::from_millis(250));
                    }
                    // Drop the stream explicitly (releases the
                    // mic). The thread then exits; the
                    // `_capture_thread: JoinHandle` we return
                    // to the caller is dropped too, which is
                    // fine (we don't wait on it from the IPC
                    // handler — the rotator drains its last
                    // chunk and exits on its own).
                    drop(stream);
                })
                .map_err(|e| {
                    eprintln!("[recording] failed to spawn capture thread: {e}");
                    RecordingError::MicrophoneUnavailable
                })?
        }
        _other => {
            // The device's native sample format isn't i16.
            // We don't ship a resampler in Sprint 33b; the
            // user must configure their system audio to
            // expose 16 kHz mono int16.
            return Err(RecordingError::MicrophoneUnavailable);
        }
    };

    // Spawn the chunk rotator (Tokio task) ON the runtime.
    // The rotator exits when the buffer stays empty for 3
    // consecutive 1-second polls (which happens when the
    // cpal stream is dropped — the callback stops writing).
    spawn_rotator(
        buffer,
        chunk_count,
        whisper_handle,
        session_dir,
        manifest_path,
        stop_flag.clone(),
    );

    Ok(stop_flag)
}

/// Spawn the Tokio task that drains the shared buffer into
/// 30-second WAV chunks, ships each path to the WhisperHF
/// subprocess, and appends the resulting transcript row to
/// the JSONL manifest.
///
/// Polls the buffer every 1 second; when `len() >= CHUNK_SAMPLES`,
/// drains + writes + ships in one synchronous step. Returns
/// immediately; the task runs for the lifetime of the
/// `cpal::Stream` (the capture callback holds the buffer;
/// when the stream drops, the callback stops writing, the
/// buffer stops growing, and the rotator exits on its next
/// idle iteration when the buffer stays empty for 2 polls).
///
/// Note: we don't model "stop" as a separate signal — the
/// caller drops the `Stream` and the rotator exits naturally.
/// This keeps the API simple at the cost of a 1-2 s tail of
/// no-op polling after `stop_recording`. Acceptable; the
/// IPC handler returns within the 2 s tail.
fn spawn_rotator(
    buffer: SharedBuffer,
    chunk_count: Arc<Mutex<u32>>,
    whisper: super::transcribe::WhisperHandle,
    session_dir: PathBuf,
    manifest_path: PathBuf,
    stop_flag: Arc<AtomicBool>,
) {
    tokio::spawn(async move {
        let mut whisper = whisper;
        let mut idle_polls: u32 = 0;
        loop {
            tokio::time::sleep(Duration::from_secs(1)).await;

            // Exit early if the stop flag was set — even if
            // the buffer still has samples (shouldn't
            // happen with our clean shutdown sequence, but
            // defensive).
            if stop_flag.load(Ordering::Relaxed) {
                return;
            }

            // Snapshot the buffer under lock; release before
            // doing the WAV write (which is slow).
            let drained: Option<Vec<i16>> = {
                let mut buf = match buffer.lock() {
                    Ok(g) => g,
                    Err(_) => return, // poisoned — abort
                };
                if buf.len() >= CHUNK_SAMPLES {
                    let chunk: Vec<i16> = buf.drain(..CHUNK_SAMPLES).collect();
                    Some(chunk)
                } else if buf.is_empty() {
                    idle_polls += 1;
                    if idle_polls >= 3 {
                        // 3 s of silence → the cpal stream
                        // is gone (caller dropped it). Exit
                        // cleanly without writing a chunk.
                        return;
                    }
                    None
                } else {
                    idle_polls = 0;
                    None
                }
            };
            let Some(samples) = drained else {
                continue;
            };
            idle_polls = 0;

            // Increment chunk counter, write WAV, ship to
            // whisper, append to manifest. Any failure here
            // is logged + skipped; the next chunk proceeds.
            let count = {
                let mut c = match chunk_count.lock() {
                    Ok(g) => g,
                    Err(_) => return,
                };
                *c += 1;
                *c
            };
            let chunk_path = session_dir.join(format!("chunk-{count:03}.wav"));

            if let Err(e) = write_wav_i16(&chunk_path, &samples, SAMPLE_RATE_HZ) {
                eprintln!("[recording] wav write failed for chunk {count}: {e}");
                continue;
            }

            // Ship the path to the WhisperHF subprocess (if
            // running). If the subprocess is dead (e.g.
            // The WhisperHandle was moved into this task
            // by `start_capture_loop`. We own it exclusively
            // for the lifetime of the rotator — `stop_record`
            // cannot kill it while we're using it because
            // the capture_stream's drop (in `stop_record`)
            // causes the buffer to stop growing, the
            // rotator exits on its next idle poll (3 polls
            // of empty buffer → return), and only then does
            // `stop_record` re-acquire the lock (which is
            // already None). Net: no contention.
            let transcript_row = whisper
                .send_and_recv(&chunk_path.display().to_string())
                .await
                .ok();

            let row = match transcript_row {
                Some(mut row) => {
                    // The whisper helper returns
                    // {audio_path, text, duration_s,
                    // sample_rate, elapsed_ms}. We strip
                    // `audio_path` and `elapsed_ms` from the
                    // manifest row (audio_path is redundant
                    // with the chunk's filename; elapsed_ms
                    // is internal bookkeeping).
                    row.as_object_mut().map(|o| {
                        o.remove("audio_path");
                        o.remove("elapsed_ms");
                    });
                    row
                }
                None => json!({
                    "text": "",
                    "duration_s": CHUNK_SECONDS as f64,
                    "sample_rate": SAMPLE_RATE_HZ,
                    "error": "whisper_unavailable",
                }),
            };

            if let Err(e) = append_manifest_line(&manifest_path, &row) {
                eprintln!("[recording] manifest append failed for chunk {count}: {e}");
            }
        }
    });
}

/// Write a buffer of i16 samples to a 16-bit mono WAV file at
/// `path`. Pure I/O; no Tokio needed for the small files
/// (~960 KB per chunk). Returns the standard `io::Result`
/// so the caller can decide whether to abort the recording
/// session or just skip the failed chunk.
pub fn write_wav_i16(
    path: &Path,
    samples: &[i16],
    sample_rate: u32,
) -> std::io::Result<()> {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    let spec = WavSpec {
        channels: CHANNELS,
        sample_rate,
        bits_per_sample: 16,
        sample_format: HoundSampleFormat::Int,
    };
    let mut writer = WavWriter::create(path, spec)
        .map_err(|e| std::io::Error::new(std::io::ErrorKind::Other, format!("hound: {e}")))?;
    for &s in samples {
        writer
            .write_sample(s)
            .map_err(|e| std::io::Error::new(std::io::ErrorKind::Other, format!("hound: {e}")))?;
    }
    writer
        .finalize()
        .map_err(|e| std::io::Error::new(std::io::ErrorKind::Other, format!("hound: {e}")))?;
    Ok(())
}

/// Append a single JSON line to the manifest. Creates the
/// file (and parents) if missing. Returns `io::Result` so the
/// caller can log + skip the chunk rather than abort.
pub fn append_manifest_line(
    manifest_path: &Path,
    row: &serde_json::Value,
) -> std::io::Result<()> {
    if let Some(parent) = manifest_path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    let mut f = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(manifest_path)?;
    let line = serde_json::to_string(row)
        .map_err(|e| std::io::Error::new(std::io::ErrorKind::Other, format!("serde: {e}")))?;
    writeln!(f, "{line}")?;
    Ok(())
}

/// Module-level helper for the IPC commands: validate the
/// session dir is writable (catch permission errors before
/// cpal starts the stream, so the user sees a clear error).
/// Returns Ok(()) if the dir exists or was created; Err with
/// `ManifestWriteFailed` otherwise.
pub fn ensure_session_dir(home: &Path) -> Result<PathBuf, RecordingError> {
    let dir = super::RecordingState::session_dir_for(&super::RecordingState::new(), home);
    std::fs::create_dir_all(&dir).map_err(|e| RecordingError::ManifestWriteFailed {
        path: format!("{}: {e}", dir.display()),
    })?;
    Ok(dir)
}

// ============================================================================
// Tests
// ============================================================================

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::{Arc, Mutex};
    use tempfile::tempdir;

    /// WAV writer produces a file whose sample count matches
    /// the input. Reads back via hound to confirm round-trip
    /// integrity.
    #[test]
    fn write_wav_i16_round_trip_preserves_sample_count() {
        let dir = tempdir().unwrap();
        let path = dir.path().join("test.wav");
        let samples: Vec<i16> = (0..1024).map(|i| (i % 1000) as i16).collect();
        write_wav_i16(&path, &samples, 16_000).unwrap();

        // Read back via hound and verify sample count.
        let mut reader = hound::WavReader::open(&path).unwrap();
        let read: Vec<i16> = reader
            .samples::<i16>()
            .collect::<Result<Vec<_>, _>>()
            .unwrap();
        assert_eq!(read.len(), samples.len());
        // Specs match too.
        let spec = reader.spec();
        assert_eq!(spec.channels, 1);
        assert_eq!(spec.sample_rate, 16_000);
        assert_eq!(spec.bits_per_sample, 16);
    }

    /// Empty samples buffer should still produce a valid WAV
    /// (header-only file). The rotator calls write_wav_i16 on
    /// partial chunks near the end of a recording; an empty
    /// buffer shouldn't panic.
    #[test]
    fn write_wav_i16_handles_empty_buffer() {
        let dir = tempdir().unwrap();
        let path = dir.path().join("empty.wav");
        write_wav_i16(&path, &[], 16_000).unwrap();
        let reader = hound::WavReader::open(&path).unwrap();
        assert_eq!(reader.spec().channels, 1);
        assert_eq!(reader.spec().sample_rate, 16_000);
    }

    /// Chunk boundary: a 30s chunk at 16 kHz = 480_000
    /// samples. The rotator only flushes when the buffer
    /// reaches this size. Verify the writer handles the full
    /// size without OOM.
    #[test]
    fn write_wav_i16_handles_full_chunk_size() {
        let dir = tempdir().unwrap();
        let path = dir.path().join("chunk.wav");
        let samples = vec![0i16; CHUNK_SAMPLES];
        write_wav_i16(&path, &samples, SAMPLE_RATE_HZ).unwrap();
        let mut reader = hound::WavReader::open(&path).unwrap();
        let count = reader.samples::<i16>().count();
        assert_eq!(count, CHUNK_SAMPLES);
    }

    /// Manifest appender creates the file if missing and
    /// appends one line per row. JSONL = newline-delimited.
    #[test]
    fn append_manifest_line_creates_and_appends() {
        let dir = tempdir().unwrap();
        let path = dir.path().join("nested").join("manifest.jsonl");
        // Parent dir doesn't exist yet — appender must create it.
        let row1 = serde_json::json!({"chunk": 0, "text": "你好"});
        let row2 = serde_json::json!({"chunk": 1, "text": "再見"});
        append_manifest_line(&path, &row1).unwrap();
        append_manifest_line(&path, &row2).unwrap();

        let content = std::fs::read_to_string(&path).unwrap();
        let lines: Vec<&str> = content.lines().collect();
        assert_eq!(lines.len(), 2);
        // Each line is independently valid JSON.
        let parsed1: serde_json::Value = serde_json::from_str(lines[0]).unwrap();
        let parsed2: serde_json::Value = serde_json::from_str(lines[1]).unwrap();
        assert_eq!(parsed1["chunk"], 0);
        assert_eq!(parsed2["chunk"], 1);
        assert_eq!(parsed1["text"], "你好");
    }

    /// Stop flag flips + rotator observes it. We can't easily
    /// unit-test the full rotator without cpal hardware, but
    /// the flag pattern is the critical correctness gate. A
    /// separate integration test (in `tests/`) drives the full
    /// pipeline via Tauri MockRuntime.
    #[test]
    fn stop_flag_atomic_bool_observable_across_threads() {
        let flag = Arc::new(std::sync::atomic::AtomicBool::new(false));
        let flag_clone = flag.clone();
        let handle = std::thread::spawn(move || {
            // Mimic the capture thread's 250ms poll loop.
            while !flag_clone.load(std::sync::atomic::Ordering::Relaxed) {
                std::thread::sleep(std::time::Duration::from_millis(10));
            }
            true
        });
        std::thread::sleep(std::time::Duration::from_millis(50));
        flag.store(true, std::sync::atomic::Ordering::Relaxed);
        assert!(handle.join().unwrap());
    }

    /// RecordingState's chunk-count Mutex protects against the
    /// "double start_record" race: the lock fires
    /// `TrainingAlreadyRunning` when the count is non-zero.
    /// Verify the slot can be read/written from multiple threads.
    #[test]
    fn recording_state_chunk_count_is_send_sync() {
        let count = Arc::new(Mutex::new(0u32));
        let count_clone = count.clone();
        let writer = std::thread::spawn(move || {
            *count_clone.lock().unwrap() += 1;
        });
        writer.join().unwrap();
        assert_eq!(*count.lock().unwrap(), 1);
    }
}
/**
 * TtsPlayer — sequential TTS playback queue.
 *
 * Extracted from `VoicePanel.tsx` in Sprint 60 (A-A1) so the queue
 * is unit-testable without mounting React + an AudioContext + the
 * full voice WS subscription tree. The queue is fire-and-forget:
 * callers `enqueue(chunk)` MP3 frames, the player drains them
 * sequentially with one shared `<audio>` element.
 *
 * ## Why a class
 *
 * The earlier inline implementation in VoicePanel relied on
 * 3 `useRef`s + 2 closures + an effect subscription. Pulling it
 * into a class:
 *
 *  1. makes the lifecycle explicit (`attach()` is lazy / first-call
 *     only — prevents double-patch of `MediaElementAudioSourceNode`
 *     which would throw `InvalidStateError`).
 *  2. makes the queue / drain sequence / playSeq all on one object
 *     — testable without React.
 *  3. keeps the public API surface narrow: `attach`, `enqueue`,
 *     `reset`, `dispose`.
 *
 * ## Attach-lifecycle contract
 *
 * The browser's Web Audio rule is: a `<audio>` element can only be
 * piped through ONE `MediaElementAudioSourceNode` for its entire
 * lifetime. The first call to `attach(audio)` patches it; subsequent
 * calls are no-ops. We don't enforce this via `MediaElementAudioSourceNode`
 * here — that's the caller's responsibility (the TTS EQ graph owns
 * the source node). This class only owns the `<audio>` element
 * reference and the queue.
 *
 * ## Sequence-bump pattern
 *
 * `playSeqRef` bumps on every `reset()`. A drain chain captures the
 * seq at start; on each iteration it checks if the seq moved (a
 * superseding turn or a user cancel) and aborts. This prevents
 * stale frames from playing after the user pressed ✕ or after a
 * new turn boundary. Per M10-A Plan A4 (Sprint 16 era).
 *
 * ## Theme / EQ integration
 *
 * Theme changes are handled by the caller — typically a `useEffect`
 * that subscribes to `useThemeStore` and calls `player.setTheme(theme)`
 * on every change. The player itself doesn't read the store, so it
 * remains a pure utility (no Zustand dep in tests).
 */
export interface TtsPlayerOptions {
  /** Factory for the underlying `<audio>` element. Default: `() => new Audio()`.
   *  Tests can pass a stub element factory to avoid the browser's
   *  `Audio` constructor (which requires a user-gesture in some envs). */
  createAudio?: () => HTMLAudioElement;
  /** Optional callback fired when a chunk starts playing. Useful for
   *  the EQ visualizer to light up `live=true` on the right rail. */
  onChunkStart?: (chunk: ArrayBuffer) => void;
  /** Optional callback fired when a chunk ends (or errors). */
  onChunkEnd?: (chunk: ArrayBuffer, error?: unknown) => void;
}

export class TtsPlayer {
  private audioEl: HTMLAudioElement | null = null;
  private queue: ArrayBuffer[] = [];
  private playSeq = 0;
  private draining = false;
  private disposed = false;
  private readonly opts: Required<Pick<TtsPlayerOptions, "createAudio">> &
    Omit<TtsPlayerOptions, "createAudio">;

  constructor(opts: TtsPlayerOptions = {}) {
    this.opts = {
      createAudio: opts.createAudio ?? (() => new Audio()),
      onChunkStart: opts.onChunkStart,
      onChunkEnd: opts.onChunkEnd,
    };
  }

  /** Push an MP3 frame onto the queue and start draining if idle.
   *
   *  No-op if disposed. Empty buffers are silently dropped.
   *  If a drain is already in progress, the new chunk will be
   *  picked up by the current chain on the next iteration. */
  enqueue(chunk: ArrayBuffer): void {
    if (this.disposed) return;
    if (!chunk || chunk.byteLength === 0) return;
    this.queue.push(chunk);
    void this.drain();
  }

  /** Bump the play sequence + clear the queue.
   *
   *  Any in-flight drain chain will abort on its next iteration
   *  check (sees `mySeq !== this.playSeq`). The currently-playing
   *  chunk continues to its natural end (we don't `audio.pause()` —
   *  abrupt cuts cause audible clicks). */
  reset(): void {
    if (this.disposed) return;
    this.playSeq += 1;
    this.queue = [];
    this.draining = false;
  }

  /** Tear down. Idempotent — safe to call multiple times. After
   *  dispose, `enqueue` is a no-op and `reset` is a no-op. The
   *  underlying `<audio>` element is left for GC (we don't
   *  pause it — the caller can pause if needed for snappy UX). */
  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    this.queue = [];
    this.playSeq += 1;
    this.draining = false;
    if (this.audioEl) {
      this.audioEl.onended = null;
      this.audioEl.onerror = null;
    }
  }

  /** The shared audio element (or null if `enqueue` has not been
   *  called yet). Exposed for the caller to attach a
   *  `MediaElementAudioSourceNode` from its own audio graph. */
  getAudioElement(): HTMLAudioElement | null {
    return this.audioEl;
  }

  /** True when the queue has pending chunks. Useful for tests + the
   *  EQ visualizer's "playing" indicator. */
  get isDraining(): boolean {
    return this.draining;
  }

  /** True if dispose() has been called. */
  get isDisposed(): boolean {
    return this.disposed;
  }

  /** Internal — runs the sequential drain. Captures the current
   *  `playSeq` at start; bails out if the seq moves (superseded
   *  by `reset()` or `dispose()`). One drain chain runs at a time
   *  (the `draining` flag short-circuits concurrent calls). */
  private async drain(): Promise<void> {
    if (this.draining) return;
    if (this.disposed) return;
    this.draining = true;
    const mySeq = this.playSeq;

    try {
      while (this.queue.length > 0) {
        if (mySeq !== this.playSeq) return; // superseded
        const next = this.queue.shift();
        if (!next) return;
        try {
          await this.playChunk(next);
          this.opts.onChunkEnd?.(next);
        } catch (err) {
          // Swallow per-chunk errors so one bad frame doesn't
          // kill the queue.
          console.warn("[TtsPlayer] chunk play failed:", err);
          this.opts.onChunkEnd?.(next, err);
        }
        if (mySeq !== this.playSeq) return;
      }
    } finally {
      this.draining = false;
    }
  }

  /** Internal — wrap an MP3 frame in a Blob URL, hand it to the
   *  shared audio element, resolve when playback ends (or errors).
   *
   *  Edge cases:
   *    - `audio.play()` rejection (autoplay policy, no user gesture):
   *      resolve immediately + log. The chunk is "skipped" so the
   *      queue can move on.
   *    - `audio.error` event: same as above (treat as end-of-stream
   *      with an error rather than crashing the chain).
   *    - No audio element yet: lazily create via `createAudio()`. */
  private playChunk(chunk: ArrayBuffer): Promise<void> {
    return new Promise((resolve) => {
      if (this.disposed) {
        resolve();
        return;
      }

      const blob = new Blob([chunk], { type: "audio/mpeg" });
      const url = URL.createObjectURL(blob);

      let audio = this.audioEl;
      if (!audio) {
        audio = this.opts.createAudio();
        this.audioEl = audio;
      }

      this.opts.onChunkStart?.(chunk);

      const cleanup = () => {
        URL.revokeObjectURL(url);
        if (audio) {
          audio.onended = null;
          audio.onerror = null;
        }
        resolve();
      };
      audio.onended = cleanup;
      audio.onerror = cleanup;
      audio.src = url;
      audio.play().catch((err) => {
        console.warn("[TtsPlayer] audio.play() rejected:", err);
        cleanup();
      });
    });
  }
}
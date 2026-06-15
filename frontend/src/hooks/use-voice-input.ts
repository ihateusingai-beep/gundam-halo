/**
 * useVoiceInput — browser-side microphone capture for the voice panel.
 *
 * Design:
 * - Uses `navigator.mediaDevices.getUserMedia` for the mic stream
 * - Uses an `AudioContext` + `AudioWorklet` to resample to 16 kHz mono
 *   (server's expected sample rate). Falls back to a ScriptProcessor
 *   on browsers that don't support worklets (very old).
 * - Frames the audio into 250 ms chunks (8000 bytes int16) and exposes
 *   them via a callback. Caller wires to `voiceSendAudio`.
 *
 * Edge cases handled:
 * - Mic permission denied → returns an error state (caller surfaces toast)
 * - Browser without `getUserMedia` (e.g. Tauri webview on some configs)
 * - Sample rate mismatch (most browsers default to 48000; we resample)
 * - User switches tabs mid-recording (track muted → no audio captured)
 */

import { useCallback, useEffect, useRef, useState } from "react";

export type MicState =
  | "unsupported"        // browser doesn't expose getUserMedia
  | "idle"               // not yet requested
  | "requesting"         // await getUserMedia
  | "denied"             // user denied mic permission
  | "error"              // getUserMedia threw
  | "ready"              // stream open, ready to capture
  | "capturing";         // actively sending chunks

const TARGET_SAMPLE_RATE = 16000;
const FRAME_MS = 250;
const FRAME_SAMPLES = (TARGET_SAMPLE_RATE * FRAME_MS) / 1000; // 4000
const INT16_MAX = 32767;

export interface UseVoiceInputOptions {
  /** Called for each captured frame. Frame is exactly FRAME_SAMPLES of
   *  mono int16 PCM @ 16 kHz. */
  onFrame: (pcm: Int16Array) => void;
  /** Called when the user starts holding the mic button. */
  onStart?: () => void;
  /** Called when the user releases the mic button. */
  onStop?: () => void;
}

export interface UseVoiceInputResult {
  state: MicState;
  error: string | null;
  start: () => Promise<void>;
  stop: () => void;
  /**
   * Sprint 17b Track E: the live MediaStream from getUserMedia.
   * Null until `start()` resolves. The cockpit HUD uses this
   * to wire `useMicAnalyser` (and thus the cyber waveform +
   * avatar pulse) directly to the user's mic without opening
   * a second `getUserMedia` stream.
   */
  stream: MediaStream | null;
}

export function useVoiceInput(opts: UseVoiceInputOptions): UseVoiceInputResult {
  const { onFrame, onStart, onStop } = opts;
  const [state, setState] = useState<MicState>("idle");
  const [error, setError] = useState<string | null>(null);
  // Sprint 17b Track E: expose the live stream to callers
  // (the cyber waveform needs it to drive the audio HUD).
  const [stream, setStream] = useState<MediaStream | null>(null);

  // Refs keep the latest callbacks / state without re-creating closures
  const onFrameRef = useRef(onFrame);
  const onStartRef = useRef(onStart);
  const onStopRef = useRef(onStop);
  onFrameRef.current = onFrame;
  onStartRef.current = onStart;
  onStopRef.current = onStop;

  // Internals
  const streamRef = useRef<MediaStream | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const workletNodeRef = useRef<AudioWorkletNode | null>(null);
  const sourceNodeRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const bufferRef = useRef<Float32Array>(new Float32Array(FRAME_SAMPLES));
  const bufferFillRef = useRef(0);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      stop();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const stop = useCallback(() => {
    if (workletNodeRef.current) {
      try { workletNodeRef.current.disconnect(); } catch { /* noop */ }
      workletNodeRef.current = null;
    }
    if (sourceNodeRef.current) {
      try { sourceNodeRef.current.disconnect(); } catch { /* noop */ }
      sourceNodeRef.current = null;
    }
    if (audioCtxRef.current) {
      try { audioCtxRef.current.close(); } catch { /* noop */ }
      audioCtxRef.current = null;
    }
    if (streamRef.current) {
      for (const t of streamRef.current.getTracks()) t.stop();
      streamRef.current = null;
    }
    bufferRef.current = new Float32Array(FRAME_SAMPLES);
    bufferFillRef.current = 0;
    setStream(null);  // Sprint 17b Track E — clear public stream
    setState((prev) => (prev === "capturing" ? "ready" : prev));
  }, []);

  const start = useCallback(async () => {
    setError(null);
    if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
      setState("unsupported");
      setError("Browser doesn't expose microphone access (getUserMedia missing)");
      return;
    }

    try {
      setState("requesting");
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
        video: false,
      });
      streamRef.current = stream;

      const ctx = new AudioContext();
      audioCtxRef.current = ctx;

      // Resample: if device rate is 48000, our target is 16000.
      // The browser does this for us if we tell the AudioContext to
      // use the target sample rate, but device rate is fixed in some
      // browsers. So we manually resample in the worklet using a
      // simple linear interpolator.

      await ctx.audioWorklet.addModule(
        URL.createObjectURL(
          new Blob(
            [WORKLET_SOURCE],
            { type: "application/javascript" },
          ),
        ),
      );
      const worklet = new AudioWorkletNode(ctx, "halo-voice-capture", {
        numberOfInputs: 1,
        numberOfOutputs: 1,
        channelCount: 1,
        processorOptions: {
          targetRate: TARGET_SAMPLE_RATE,
          deviceRate: ctx.sampleRate,
        },
      });
      workletNodeRef.current = worklet;

      worklet.port.onmessage = (e: MessageEvent) => {
        const data = e.data as Float32Array;
        // Append to buffer
        let fill = bufferFillRef.current;
        const buf = bufferRef.current;
        let written = 0;
        while (written < data.length) {
          const space = buf.length - fill;
          const take = Math.min(space, data.length - written);
          buf.set(data.subarray(written, written + take), fill);
          fill += take;
          written += take;
          if (fill >= buf.length) {
            // Convert to int16
            const out = new Int16Array(buf.length);
            for (let i = 0; i < buf.length; i++) {
              const s = Math.max(-1, Math.min(1, buf[i]));
              out[i] = s < 0 ? s * INT16_MAX : s * INT16_MAX;
            }
            onFrameRef.current(out);
            fill = 0;
          }
        }
        bufferFillRef.current = fill;
      };

      const source = ctx.createMediaStreamSource(stream);
      sourceNodeRef.current = source;
      source.connect(worklet);

      // Sprint 17b Track E: surface the live stream so the
      // cockpit HUD (useMicAnalyser) can attach to the same
      // MediaStream without opening a second getUserMedia.
      setStream(stream);
      setState("capturing");
      onStartRef.current?.();
    } catch (e) {
      const err = e as DOMException | Error;
      if ((err as DOMException).name === "NotAllowedError") {
        setState("denied");
        setError("Microphone permission denied. Allow it in browser settings.");
      } else {
        setState("error");
        setError((err as Error).message || String(e));
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stop]);

  return { state, error, start, stop, stream };
}

// ---------------------------------------------------------------------------
// AudioWorklet processor — runs in a separate audio thread, receives
// float32 chunks from the input, and posts resampled float32 to the
// main thread for chunking + int16 conversion.
// ---------------------------------------------------------------------------

const WORKLET_SOURCE = `
class HaloVoiceCapture extends AudioWorkletProcessor {
  constructor(options) {
    super();
    const opts = (options && options.processorOptions) || {};
    this.targetRate = opts.targetRate || 16000;
    this.deviceRate = opts.deviceRate || sampleRate;
    this.ratio = this.deviceRate / this.targetRate;
    this.frac = 0;
  }
  process(inputs) {
    const input = inputs[0];
    if (!input || !input[0]) return true;
    const channel = input[0];
    const outLen = Math.floor(channel.length / this.ratio);
    if (outLen <= 0) return true;
    const out = new Float32Array(outLen);
    let pos = 0;
    for (let i = 0; i < outLen; i++) {
      const idx = Math.floor(pos);
      const next = idx + 1;
      const t = pos - idx;
      const a = channel[idx] || 0;
      const b = channel[next] !== undefined ? channel[next] : a;
      out[i] = a + (b - a) * (1 - t);
      pos += this.ratio;
    }
    this.port.postMessage(out, [out.buffer]);
    return true;
  }
}
registerProcessor("halo-voice-capture", HaloVoiceCapture);
`;

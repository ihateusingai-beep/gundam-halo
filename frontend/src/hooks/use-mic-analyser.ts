/**
 * useMicAnalyser — derive a 0-1 RMS amplitude from the user's mic.
 *
 * Sprint 17b Track E. The voice panel drives a `MediaStream` from
 * `useVoiceInput`'s `getUserMedia` call. This hook attaches an
 * `AnalyserNode` to that stream and polls RMS at 20Hz, which
 * the cyber cockpit's waveform + avatar pulse consume via
 * `useSharedAmplitude(source: "mic")`.
 *
 * If the caller doesn't pass a stream (e.g. the voice panel
 * hasn't opened one yet because the user isn't holding the
 * mic button), the hook can either:
 *
 *   1. Open its own `getUserMedia` stream (independent of the
 *      voice panel). Browser permits multiple concurrent
 *      `getUserMedia` calls on the same physical mic input.
 *      Trade-off: 2x the AudioContext work + an extra
 *      "second-mic" indicator on macOS mic-permission UI.
 *
 *   2. Return 0 (idle) until a stream is provided. This is
 *      the default — we let `VoicePanel` hand us the stream
 *      via the `stream` prop whenever it has one.
 *
 * We default to option (2) so the visual HUD doesn't grab
 * the mic independently. Pass `stream` once `useVoiceInput`
 * has it.
 */
import { useEffect, useRef, useState } from "react";

const POLL_INTERVAL_MS = 50; // 20Hz — matches server-side broadcast rate
const SMOOTHING_TIME_CONSTANT_S = 0.12; // ~120ms — perceptually smooth

/**
 * Compute RMS from a 0-255 time-domain byte array.
 *
 * `getByteTimeDomainData` returns 0-centered samples (-1..1)
 * scaled to unsigned bytes (0..255, with 128 = silence).
 * The standard formula is:
 *   sum((byte - 128) / 128)^2  / N
 * then sqrt. We avoid the per-sample division and just
 * normalize at the end — same result modulo a constant.
 */
function rmsFromTimeDomain(bytes: Uint8Array): number {
  let sumSq = 0;
  for (let i = 0; i < bytes.length; i++) {
    const centered = (bytes[i] - 128) / 128;
    sumSq += centered * centered;
  }
  const meanSq = sumSq / bytes.length;
  return Math.sqrt(meanSq);
}

export interface UseMicAnalyserResult {
  /** Latest smoothed amplitude in [0, 1]. Returns 0 when no
   *  stream is attached or AudioContext isn't available. */
  amplitude: number;
  /** True if the analyser is actively producing values. */
  active: boolean;
  /** Last error from `getUserMedia` or AnalyserNode setup. */
  error: string | null;
}

/**
 * Hook that derives a smoothed 0-1 amplitude from a mic stream.
 *
 * @param stream  The `MediaStream` returned from `getUserMedia`.
 *                If undefined, the hook returns amplitude=0 and
 *                does not open the mic.
 */
export function useMicAnalyser(
  stream: MediaStream | null | undefined,
): UseMicAnalyserResult {
  const [amplitude, setAmplitude] = useState(0);
  const [active, setActive] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Refs let us reach into the AudioContext from the cleanup
  // closure without re-creating it on every render.
  const ctxRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const sourceNodeRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const intervalRef = useRef<number | null>(null);
  const lastAmpRef = useRef(0);
  const lastPollMsRef = useRef(Date.now());

  useEffect(() => {
    // Detach the previous analyser when the stream changes or
    // unmounts. We own the AudioContext (we created it here);
    // we do NOT own the stream (caller owns that).
    function teardown() {
      if (intervalRef.current !== null) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
      if (sourceNodeRef.current) {
        try { sourceNodeRef.current.disconnect(); } catch { /* noop */ }
        sourceNodeRef.current = null;
      }
      if (analyserRef.current) {
        try { analyserRef.current.disconnect(); } catch { /* noop */ }
        analyserRef.current = null;
      }
      if (ctxRef.current) {
        try { ctxRef.current.close(); } catch { /* noop */ }
        ctxRef.current = null;
      }
      setActive(false);
      setAmplitude(0);
      lastAmpRef.current = 0;
    }

    if (!stream) {
      teardown();
      return teardown;
    }

    // Browsers without AudioContext (very old or some
    // non-mainstream webviews) — return idle.
    if (typeof window === "undefined" || typeof window.AudioContext === "undefined") {
      setError("AudioContext not available");
      return teardown;
    }

    let cancelled = false;
    try {
      const ctx = new window.AudioContext();
      // We use fftSize 256 → 128 time-domain bins per poll.
      // Smaller = lower latency but noisier RMS; this is a
      // good middle ground for voice.
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 256;
      analyser.smoothingTimeConstant = 0; // we do our own smoothing
      const source = ctx.createMediaStreamSource(stream);
      source.connect(analyser);
      // Note: we deliberately do NOT connect the analyser to
      // ctx.destination — that would route the mic to the
      // user's speakers. The analyser is a silent tap.
      ctxRef.current = ctx;
      analyserRef.current = analyser;
      sourceNodeRef.current = source;

      const bytes = new Uint8Array(analyser.fftSize);

      const poll = () => {
        if (cancelled) return;
        analyser.getByteTimeDomainData(bytes);
        const rms = rmsFromTimeDomain(bytes);
        // Log compression (per the FsmnVAD's tuning on the
        // backend side — keep the two sources visually
        // consistent). For typical conversational Cantonese
        // (peak ~0.3 RMS), this maps to ~0.5-0.8 on the
        // 0-1 scale the HUD consumes.
        const compressed = Math.log(1 + 30 * rms) / Math.log(1 + 30);
        // Exponential smoothing — frame-rate-independent.
        const nowMs = Date.now();
        const dt = (nowMs - lastPollMsRef.current) / 1000;
        lastPollMsRef.current = nowMs;
        const k = 1 - Math.exp(-dt / SMOOTHING_TIME_CONSTANT_S);
        const smoothed =
          lastAmpRef.current + (compressed - lastAmpRef.current) * k;
        lastAmpRef.current = smoothed;
        setAmplitude(smoothed);
      };

      intervalRef.current = window.setInterval(poll, POLL_INTERVAL_MS);
      setActive(true);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      teardown();
    }

    return () => {
      cancelled = true;
      teardown();
    };
  }, [stream]);

  return { amplitude, active, error };
}

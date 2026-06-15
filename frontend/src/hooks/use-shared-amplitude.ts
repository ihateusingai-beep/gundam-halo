// Shared amplitude source for the cyber cockpit.
//
// Sprint 17b Track E: the hook now accepts a `source` argument
// to switch between the deterministic idle drift and the
// real mic RMS via `useMicAnalyser`. See the file-level
// comment for the dual-source rationale.
//
// In the original Sprint 16 design, the amplitude was
// deterministic + smooth (two slow sines plus a 7-12s
// "burst" envelope). The cyber waveform and avatar pulse
// subscribe to the same value so visual pulses stay in sync.
// That drift is still the default fallback (`source: "idle"`).
//
// When `source: "mic"`, the hook transparently subscribes to
// a sibling `useMicAnalyser()` instance that reads the
// browser's `AnalyserNode` from the user's mic stream. The
// voice panel flips the source to "mic" while the user holds
// the mic button and back to "idle" on release.

import { useEffect, useState } from "react";

import { useMicAnalyser } from "./use-mic-analyser";

export type AmplitudeSource = "idle" | "mic";

const FRAME_BUDGET_MS = 50; // 20Hz tick — lazy on purpose, allows the visual to "breathe"

// Layered sines with irrational ratios → never quite repeats, never
// accelerates. Periods chosen to feel like idle breath (6.5s and 9.2s
// are slow enough that 5+ seconds of viewing feels intentional).
const PRIMARY_PERIOD_MS = 6500;
const SECONDARY_PERIOD_MS = 9200;
const PRIMARY_AMP = 0.18; // baseline sway range
const SECONDARY_AMP = 0.10;
const BASELINE = 0.45; // center of the pulse range (was 0.15 — felt like "off then on")

// Burst layer: every 7-12 seconds, ramp up to 0.85 for 3-5s, then
// decay. This is the "talking" pulse. scheduleBurst() picks the
// next burst anchor when the current one ends.
type Burst = { startMs: number; peakMs: number; endMs: number; peak: number };
let nextBurstAnchor = 7000; // first burst at t=7s
let activeBurst: Burst | null = null;

function scheduleBurst(now: number) {
  if (activeBurst) return;
  const gap = 7000 + Math.random() * 5000; // 7-12s gaps
  const start = now + gap;
  const peak = start + 1500 + Math.random() * 2000; // ramp up over 1.5-3.5s
  const end = peak + 1500 + Math.random() * 3500; // hold peak 1.5-5s then decay
  activeBurst = { startMs: start, peakMs: peak, endMs: end, peak: 0.78 + Math.random() * 0.15 };
  nextBurstAnchor = end;
}

function burstEnvelope(t: number, b: Burst): number {
  if (t < b.startMs || t > b.endMs) return 0;
  if (t < b.peakMs) {
    const p = (t - b.startMs) / (b.peakMs - b.startMs);
    return b.peak * smoothStep(p);
  }
  const p = (t - b.peakMs) / (b.endMs - b.peakMs);
  return b.peak * (1 - smoothStep(p));
}

function smoothStep(t: number): number {
  // Quintic smoothstep: 6t^5 - 15t^4 + 10t^3 — S-curve, no jerk
  const x = Math.max(0, Math.min(1, t));
  return x * x * x * (x * (x * 6 - 15) + 10);
}

let idleSubscribers = new Set<(v: number) => void>();
let timerId: number | null = null;
let startMs: number = Date.now();

function computeIdleAmp(now: number): number {
  const t = now - startMs;
  // Two slow sines, combined additively, clamped to envelope.
  const primary = Math.sin((t / PRIMARY_PERIOD_MS) * 2 * Math.PI) * PRIMARY_AMP;
  const secondary = Math.sin((t / SECONDARY_PERIOD_MS) * 2 * Math.PI + 1.7) * SECONDARY_AMP;
  let amp = BASELINE + primary + secondary;

  // Burst layer
  scheduleBurst(now);
  if (activeBurst) {
    amp += burstEnvelope(now, activeBurst);
    if (now >= activeBurst.endMs) activeBurst = null;
  }

  return Math.max(0.15, Math.min(1.0, amp));
}

function idleLoop() {
  const now = Date.now();
  const amp = computeIdleAmp(now);
  for (const cb of idleSubscribers) cb(amp);
  timerId = window.setTimeout(idleLoop, FRAME_BUDGET_MS) as unknown as number;
}

function ensureIdleLoopRunning() {
  if (timerId === null) {
    startMs = Date.now();
    timerId = window.setTimeout(idleLoop, FRAME_BUDGET_MS) as unknown as number;
  }
}

function stopIdleLoop() {
  if (timerId !== null) {
    clearTimeout(timerId);
    timerId = null;
  }
}

/**
 * useSharedAmplitude — subscribes to the amplitude tick.
 *
 * @param source  "idle" (default) — deterministic breath
 *                animation. "mic" — live RMS from the user's
 *                mic via `useMicAnalyser`. The mic path
 *                requires a stream; pass it as the second
 *                argument. Without a stream, "mic" returns 0.
 *
 * Returns a value in [0, 1] that the caller uses to scale
 * size / opacity / glow.
 */
// Internal helper: idle-drift amplitude. Always called by
// useSharedAmplitude on every render so the rule of hooks
// (same number of hooks in the same order on every render)
// is satisfied even when `source` flips between renders.
function useIdleAmplitude(): number {
  const [amp, setAmp] = useState(BASELINE);
  useEffect(() => {
    ensureIdleLoopRunning();
    idleSubscribers.add(setAmp);
    return () => {
      idleSubscribers.delete(setAmp);
      if (idleSubscribers.size === 0) stopIdleLoop();
    };
  }, []);
  return amp;
}

/**
 * useSharedAmplitude — subscribes to the amplitude tick.
 *
 * @param source  "idle" (default) — deterministic breath
 *                animation. "mic" — live RMS from the user's
 *                mic via `useMicAnalyser`. The mic path
 *                requires a stream; pass it as the second
 *                argument. Without a stream, "mic" returns 0.
 *
 * Returns a value in [0, 1] that the caller uses to scale
 * size / opacity / glow.
 *
 * Implementation note: both branches always invoke the same
 * number of hooks in the same order (`useIdleAmplitude` is
 * always called, then `useMicAnalyser` is always called).
 * The active source is picked at the end. This avoids the
 * rules-of-hooks violation that would come from a
 * conditional `if (source === ...) { useX() } else { useY() }`.
 */
export function useSharedAmplitude(
  source: AmplitudeSource = "idle",
  stream?: MediaStream | null,
): number {
  // Always run both hooks — same order on every render.
  const idleAmp = useIdleAmplitude();
  const { amplitude: micAmp } = useMicAnalyser(stream ?? null);
  return source === "mic" ? micAmp : idleAmp;
}

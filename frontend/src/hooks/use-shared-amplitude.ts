// Shared amplitude source for the cyber cockpit.
//
// Drives a smooth, slowly-drifting amplitude value. Components
// (CyberWaveform, CSSAvatar, future voice-reactive HUD elements)
// all subscribe to the same value so visual pulses stay in sync.
//
// The amplitude is **deterministic + smooth**, not random-walk:
// we layer two slow sine waves (~6.5s and ~9.2s periods) and add
// a sparse "burst" envelope that fires every 7-12s. The result
// feels organic and breathy rather than "starts slow, then
// accelerates" — which is what a uniform-random + lerp produces.
//
// If a real audio source is wired in later, replace the `computeAmp`
// body with an AnalyserNode RMS readout; the public hook signature
// stays the same.

import { useEffect, useState } from "react";

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

let subscribers = new Set<(v: number) => void>();
let timerId: number | null = null;
let startMs: number = Date.now();

function computeAmp(now: number): number {
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

function loop() {
  const now = Date.now();
  const amp = computeAmp(now);
  for (const cb of subscribers) cb(amp);
  timerId = window.setTimeout(loop, FRAME_BUDGET_MS) as unknown as number;
}

function ensureLoopRunning() {
  if (timerId === null) {
    startMs = Date.now();
    timerId = window.setTimeout(loop, FRAME_BUDGET_MS) as unknown as number;
  }
}

function stopLoop() {
  if (timerId !== null) {
    clearTimeout(timerId);
    timerId = null;
  }
}

/**
 * useSharedAmplitude — subscribes to the global amplitude tick.
 * Returns a value in [0, 1] that the caller can use to scale any
 * size / opacity / glow variable.
 */
export function useSharedAmplitude(): number {
  const [amp, setAmp] = useState(BASELINE);
  useEffect(() => {
    ensureLoopRunning();
    subscribers.add(setAmp);
    return () => {
      subscribers.delete(setAmp);
      if (subscribers.size === 0) stopLoop();
    };
  }, []);
  return amp;
}

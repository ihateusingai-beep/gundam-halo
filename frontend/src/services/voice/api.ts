/**
 * Voice WebSocket — public turn control + subscription API +
 * console debug.
 *
 * Sprint 56 R7: extracted from `services/halo-voice-ws.ts` (532
 * LoC monolith). This module owns:
 *   1. The module-level singleton (auto-connects on first
 *      browser load).
 *   2. The 5 public turn-control helpers (`voiceBegin`,
 *      `voiceSendAudio`, `voiceEnd`, `voiceText`, `voiceCancel`,
 *      `voicePing`).
 *   3. The 4 subscription helpers (`subscribeToVoiceEvent`,
 *      `onVoiceBinary`, `getVoiceStatus`, `onVoiceStatusChange`).
 *   4. The dev-console `window.__haloVoice` debug API.
 *
 * The class itself lives in `connection.ts`; the event/state
 * types live in `types.ts`. This file is the public surface
 * other modules import.
 */

import { VoiceWsClient } from "./connection";
import type { BinaryHandler, VoiceEventHandler, VoiceStatus } from "./types";

// Module-level singleton — auto-connects on first browser load.
const singleton = new VoiceWsClient();

// ---------------------------------------------------------------------------
// Public turn control
// ---------------------------------------------------------------------------

/** Start a new turn. Allocates a session id. Server resets the pipeline. */
export function voiceBegin(): string {
  const snap = singleton.snapshot();
  if (snap.state !== "ready" && snap.state !== "idle") {
    console.warn(`[Voice] begin() called while in state ${snap.state} — auto-resetting`);
  }
  const sid = `voice-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  singleton.setCurrentSession(sid);
  singleton.resetToListening();
  singleton.send({ type: "voice.begin", session_id: sid });
  return sid;
}

/** Stream a PCM chunk (16 kHz mono int16, ~250 ms = 8000 bytes). */
export function voiceSendAudio(pcm: Int16Array) {
  // Int16Array.buffer is an ArrayBuffer — but WebSocket.send wants
  // either a string, Blob, or ArrayBuffer. Pass the underlying buffer.
  singleton.send(pcm.buffer);
}

/** End the turn — server runs ASR (if not already) → agent → TTS. */
export function voiceEnd() {
  singleton.send({ type: "voice.end" });
}

/** Bypass VAD/ASR — send a text turn directly. Useful for the manual
 *  input box and for tests. */
export function voiceText(text: string) {
  if (!text.trim()) return;
  const sid = singleton.getCurrentSession() ?? `text-${Date.now()}`;
  singleton.setCurrentSession(sid);
  singleton.resetToThinking();
  singleton.send({ type: "voice.text", text, session_id: sid });
}

/** Abort the in-flight turn. */
export function voiceCancel() {
  singleton.send({ type: "voice.cancel" });
}

/** Ping the server (round-trip liveness check). */
export function voicePing() {
  singleton.send({ type: "ping" });
}

// ---------------------------------------------------------------------------
// Subscription API
// ---------------------------------------------------------------------------

export function subscribeToVoiceEvent(
  type: string | "*",
  handler: VoiceEventHandler,
): () => void {
  return singleton.subscribeTo(type, handler);
}

export function onVoiceBinary(handler: BinaryHandler): () => void {
  return singleton.onBinary(handler);
}

export function getVoiceStatus(): VoiceStatus {
  return singleton.snapshot();
}

export function onVoiceStatusChange(cb: (s: VoiceStatus) => void): () => void {
  return singleton.subscribeStatus(cb);
}

/** Public test-helper + dev-console API: trigger a forced reconnect
 *  with the same backoff as a normal failure. Useful when the user
 *  suspects the panel is stuck — call from the JS console. */
export function forceVoiceReconnect(reason = "manual"): void {
  singleton.forceReconnect(reason);
}

// ---------------------------------------------------------------------------
// Console debug API
// ---------------------------------------------------------------------------

if (typeof window !== "undefined") {
  (window as any).__haloVoice = {
    subscribe: subscribeToVoiceEvent,
    onBinary: onVoiceBinary,
    getStatus: getVoiceStatus,
    begin: voiceBegin,
    end: voiceEnd,
    text: voiceText,
    cancel: voiceCancel,
    ping: voicePing,
    help: () => {
      console.log(`
Halo Voice Service — Console Debug API
  __haloVoice.begin()                — start a new turn
  __haloVoice.end()                  — flush the turn (run ASR → agent → TTS)
  __haloVoice.text("hi")             — bypass ASR, send text directly
  __haloVoice.cancel()               — abort in-flight
  __haloVoice.getStatus()            → VoiceStatus snapshot
  __haloVoice.subscribe(type, h)     — listen for events
  __haloVoice.onBinary(h)            — receive TTS audio chunks
  __haloVoice.ping()                 — round-trip liveness check

States: idle → ready → listening → thinking → speaking → ready
                                       (or error)
`);
    },
  };
}

/**
 * Voice WebSocket service — sends mic audio to /ws/voice, receives
 * TTS audio + live2d triggers + agent messages in return.
 *
 * Pattern mirrors `halo-live2d-bridge.ts`:
 *   - module-level singleton
 *   - console debug global (`window.__haloVoice`)
 *   - subscribes to its own WS (separate from the main /ws)
 *
 * Wire protocol (matches the backend `voice_ws.py`):
 *
 *   client → server
 *     { "type": "voice.begin",   "session_id": "..." }
 *     <binary PCM chunk, 16 kHz mono int16, 250 ms = 8000 bytes>
 *     { "type": "voice.end"     }
 *     { "type": "voice.text",   "text": "..." }   (bypass VAD/ASR)
 *     { "type": "voice.cancel"  }
 *     { "type": "ping"          }
 *
 *   server → client
 *     { "type": "voice.hello" }   (on connect)
 *     { "type": "vad.state", "data": { "state": "speech_start" | "speech_end" } }
 *     { "type": "asr.result", "data": { "text": "..." } }
 *     { "type": "agent.message", "data": { "text": "...", "emotion": "..." } }
 *     { "type": "tts.start", "data": { "emotion": "..." } }
 *     { "type": "tts.audio", "data": { "sentence": "..." } }  ← followed by <binary>
 *     { "type": "tts.end" }
 *     { "type": "live2d.trigger", "data": { "expression", "motion", "emotion" } }
 *     { "type": "voice.turn_ended" } / "voice.cancelled" / "voice.error"
 *     { "type": "pong" }
 */

import { API_BASE } from "@/lib/api";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type VoiceState =
  | "idle"        // not connected
  | "ready"       // connected, not capturing
  | "listening"   // mic open, streaming audio
  | "thinking"    // got ASR, waiting for agent
  | "speaking"    // agent replied, TTS playing
  | "error";

export interface VoiceStatus {
  state: VoiceState;
  /** Last thing the user said (ASR transcript). */
  lastAsr: string | null;
  /** Last thing the agent said (clean text, no emotion tags). */
  lastReply: string | null;
  /** Live emotion from the most recent live2d.trigger. */
  emotion: string | null;
  /** Server's view: voice layer enabled? */
  serverEnabled: boolean;
  /** Last error message, cleared on next state transition. */
  error: string | null;
  /** AudioContext sample rate (0 if no mic). */
  sampleRate: number;
}

export interface VoiceTranscriptEvent {
  type: "asr.result";
  data: { session_id: string; text: string; duration_ms: number };
}
export interface VoiceAgentMessageEvent {
  type: "agent.message";
  data: { session_id: string; text: string; emotion: string; is_final: boolean };
}
export interface VoiceLive2DTriggerEvent {
  type: "live2d.trigger";
  data: { session_id: string; expression: string; motion: string; emotion: string };
}
export interface VoiceTtsStartEvent {
  type: "tts.start";
  data: { session_id: string; emotion: string };
}
export interface VoiceTtsEndEvent {
  type: "tts.end";
  data: { session_id: string; chunks: number };
}
export interface VoiceVadStateEvent {
  type: "vad.state";
  data: { state: "speech_start" | "speech_end"; session_id?: string };
}
export interface VoiceHelloEvent {
  type: "voice.hello";
  data: {
    client_id: number;
    sample_rate: number;
    frame_duration_ms: number;
    vad_backend: string;
    asr_backend: string;
    asr_model: string;
    tts_enabled: boolean;
    live2d_enabled: boolean;
  };
}
export interface VoiceErrorEvent {
  type: "voice.error";
  data: { error: string };
}
export interface VoiceTurnEndedEvent {
  type: "voice.turn_ended";
  data: { session_id: string; discarded: boolean; total_duration_ms?: number };
}
export interface VoiceCancelledEvent {
  type: "voice.cancelled";
  data: { session_id: string };
}

export type VoiceWSEvent =
  | VoiceHelloEvent
  | VoiceVadStateEvent
  | VoiceTranscriptEvent
  | VoiceAgentMessageEvent
  | VoiceTtsStartEvent
  | VoiceTtsEndEvent
  | VoiceLive2DTriggerEvent
  | VoiceErrorEvent
  | VoiceTurnEndedEvent
  | VoiceCancelledEvent
  | { type: string; [key: string]: unknown };

export type VoiceEventHandler = (event: VoiceWSEvent) => void;
export type BinaryHandler = (chunk: ArrayBuffer) => void;

// ---------------------------------------------------------------------------
// Internal state
// ---------------------------------------------------------------------------

interface VoiceState_ {
  socket: WebSocket | null;
  state: VoiceState;
  lastAsr: string | null;
  lastReply: string | null;
  emotion: string | null;
  serverEnabled: boolean;
  error: string | null;
  sampleRate: number;
  currentSession: string | null;
  listeners: Map<string | "*", Set<VoiceEventHandler>>;
  binaryListeners: Set<BinaryHandler>;
  onStateChange: Set<(s: VoiceStatus) => void>;
}

const state: VoiceState_ = {
  socket: null,
  state: "idle",
  lastAsr: null,
  lastReply: null,
  emotion: null,
  serverEnabled: false,
  error: null,
  sampleRate: 0,
  currentSession: null,
  listeners: new Map(),
  binaryListeners: new Set(),
  onStateChange: new Set(),
};

function snapshot(): VoiceStatus {
  return {
    state: state.state,
    lastAsr: state.lastAsr,
    lastReply: state.lastReply,
    emotion: state.emotion,
    serverEnabled: state.serverEnabled,
    error: state.error,
    sampleRate: state.sampleRate,
  };
}

function notify() {
  const s = snapshot();
  for (const cb of state.onStateChange) {
    try { cb(s); } catch (e) { console.warn("[Voice] state cb threw:", e); }
  }
}

function setState(next: Partial<VoiceState_>) {
  Object.assign(state, next);
  notify();
}

function dispatch(event: VoiceWSEvent) {
  const specific = state.listeners.get(event.type);
  if (specific) for (const h of specific) {
    try { h(event); } catch (e) { console.warn(`[Voice] handler for ${event.type} threw:`, e); }
  }
  const wildcard = state.listeners.get("*");
  if (wildcard) for (const h of wildcard) {
    try { h(event); } catch (e) { console.warn(`[Voice] wildcard handler threw:`, e); }
  }
}

function dispatchBinary(chunk: ArrayBuffer) {
  for (const h of state.binaryListeners) {
    try { h(chunk); } catch (e) { console.warn("[Voice] binary handler threw:", e); }
  }
}

// ---------------------------------------------------------------------------
// Connection
// ---------------------------------------------------------------------------

let connectAttempted = false;

function connect() {
  if (state.socket && state.socket.readyState <= WebSocket.OPEN) return;
  if (connectAttempted) return;
  connectAttempted = true;

  const WS_URL = API_BASE.replace(/^http/, "ws") + "/ws/voice";
  console.log("[Voice] connecting to", WS_URL);
  const ws = new WebSocket(WS_URL);
  state.socket = ws;

  ws.binaryType = "arraybuffer"; // we want raw bytes for tts.audio

  ws.onopen = () => {
    console.log("[Voice] connected");
    setState({ state: "ready" });
  };

  ws.onclose = () => {
    console.log("[Voice] disconnected");
    setState({
      state: "idle",
      socket: null,
      currentSession: null,
    });
    connectAttempted = false;
  };

  ws.onerror = () => {
    setState({ error: "WebSocket error" });
  };

  ws.onmessage = (msg) => {
    if (msg.data instanceof ArrayBuffer) {
      dispatchBinary(msg.data);
      return;
    }
    try {
      const event = JSON.parse(msg.data) as VoiceWSEvent;
      handleEvent(event);
      dispatch(event);
    } catch (e) {
      console.warn("[Voice] failed to parse WS message:", e, msg.data);
    }
  };
}

function handleEvent(event: VoiceWSEvent) {
  switch (event.type) {
    case "voice.hello": {
      const d = (event as VoiceHelloEvent).data;
      setState({
        serverEnabled: true,
        sampleRate: d.sample_rate,
      });
      console.log(
        `[Voice] server hello: vad=${d.vad_backend} asr=${d.asr_backend} asr_model=${d.asr_model} tts=${d.tts_enabled} live2d=${d.live2d_enabled}`,
      );
      break;
    }
    case "vad.state": {
      const d = (event as VoiceVadStateEvent).data;
      if (d.state === "speech_start") {
        setState({ state: "listening" });
      } else {
        // speech_end — server is about to start ASR. Stay in "listening"
        // (caller will see "thinking" once we get asr.result + agent processing).
        setState({ state: "listening" });
      }
      break;
    }
    case "asr.result": {
      const d = (event as VoiceTranscriptEvent).data;
      setState({ lastAsr: d.text, state: "thinking" });
      break;
    }
    case "agent.message": {
      const d = (event as VoiceAgentMessageEvent).data;
      if (d.is_final) {
        setState({ lastReply: d.text, emotion: d.emotion });
      }
      break;
    }
    case "tts.start": {
      setState({ state: "speaking" });
      break;
    }
    case "tts.end": {
      // TTS finished, but server may still send more tts chunks for
      // multi-sentence replies. Stay in "speaking" until turn_ended.
      break;
    }
    case "live2d.trigger": {
      const d = (event as VoiceLive2DTriggerEvent).data;
      setState({ emotion: d.emotion });
      break;
    }
    case "voice.turn_ended": {
      setState({ state: "ready", currentSession: null });
      break;
    }
    case "voice.cancelled": {
      setState({ state: "ready", currentSession: null });
      break;
    }
    case "voice.error": {
      const d = (event as VoiceErrorEvent).data;
      setState({ state: "error", error: d.error });
      break;
    }
  }
}

function ensureOpen(): WebSocket {
  if (!state.socket || state.socket.readyState > WebSocket.OPEN) {
    connect();
  }
  if (!state.socket) {
    throw new Error("voice WS not connected");
  }
  return state.socket;
}

function send(payload: object | string | ArrayBuffer) {
  const ws = state.socket;
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    console.warn("[Voice] cannot send, socket not open", payload);
    return;
  }
  // Binary PCM chunks must go through raw — `JSON.stringify(new ArrayBuffer(...))`
  // collapses to `"{}"`, which the backend rejects with `unknown_type: None`
  // and spams the voice-error toast. Detect and pass through.
  if (payload instanceof ArrayBuffer) {
    ws.send(payload);
    return;
  }
  ws.send(typeof payload === "string" ? payload : JSON.stringify(payload));
}

// ---------------------------------------------------------------------------
// Public turn control
// ---------------------------------------------------------------------------

/** Start a new turn. Allocates a session id. Server resets the pipeline. */
export function voiceBegin(): string {
  if (state.state !== "ready" && state.state !== "idle") {
    console.warn(`[Voice] begin() called while in state ${state.state} — auto-resetting`);
  }
  const sid =
    `voice-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  setState({ currentSession: sid, state: "listening", error: null });
  send({ type: "voice.begin", session_id: sid });
  return sid;
}

/** Stream a PCM chunk (16 kHz mono int16, ~250 ms = 8000 bytes). */
export function voiceSendAudio(pcm: Int16Array) {
  // Int16Array.buffer is an ArrayBuffer — but WebSocket.send wants
  // either a string, Blob, or ArrayBuffer. Pass the underlying buffer.
  send(pcm.buffer);
}

/** End the turn — server runs ASR (if not already) → agent → TTS. */
export function voiceEnd() {
  send({ type: "voice.end" });
}

/** Bypass VAD/ASR — send a text turn directly. Useful for the manual
 *  input box and for tests. */
export function voiceText(text: string) {
  if (!text.trim()) return;
  const sid = state.currentSession ?? `text-${Date.now()}`;
  setState({ currentSession: sid, state: "thinking", error: null });
  send({ type: "voice.text", text, session_id: sid });
}

/** Abort the in-flight turn. */
export function voiceCancel() {
  send({ type: "voice.cancel" });
}

/** Ping the server (round-trip liveness check). */
export function voicePing() {
  send({ type: "ping" });
}

// ---------------------------------------------------------------------------
// Subscription API
// ---------------------------------------------------------------------------

export function subscribeToVoiceEvent(
  type: string | "*",
  handler: VoiceEventHandler,
): () => void {
  let set = state.listeners.get(type);
  if (!set) {
    set = new Set();
    state.listeners.set(type, set);
  }
  set.add(handler);
  return () => { set?.delete(handler); };
}

export function onVoiceBinary(handler: BinaryHandler): () => void {
  state.binaryListeners.add(handler);
  return () => { state.binaryListeners.delete(handler); };
}

export function getVoiceStatus(): VoiceStatus {
  return snapshot();
}

export function onVoiceStatusChange(cb: (s: VoiceStatus) => void): () => void {
  state.onStateChange.add(cb);
  return () => { state.onStateChange.delete(cb); };
}

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------

if (typeof window !== "undefined") {
  if (document.readyState === "complete") {
    connect();
  } else {
    window.addEventListener("load", connect, { once: true });
  }
}

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

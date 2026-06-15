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
  | "reconnecting" // socket was open, went dead, auto-reconnect in flight
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
  /**
   * Sprint 17b Track E: latest server-side audio level
   * (0.0-1.0). FALLBACK source for the cockpit HUD — the
   * primary path is the browser's AnalyserNode. Used only
   * in Tauri or other non-browser contexts where the
   * AnalyserNode isn't available.
   */
  lastAudioLevel: number;
}

export interface VoiceTranscriptEvent {
  type: "asr.result";
  data: {
    session_id: string;
    text: string;
    duration_ms: number;
    // Sprint 16: the wake phrase the backend matched (empty string
    // if none). e.g. "Unicorn" / "NTD" / "gundam" / "獨角獸" / "高達".
    wake_phrase: string;
    // Sprint 16: true when a wake phrase was matched at the start
    // of the transcript. In strict mode (Sprint 17a) the agent
    // is only invoked when this is true; otherwise the turn is
    // discarded.
    wake_triggered: boolean;
  };
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
// Sprint 17b Track E: server broadcasts a per-frame audio
// level (0.0-1.0) at 20Hz when the voice WS is active and
// the server-side dual-VAD (silero + fsmn) is wired. This is
// the FALLBACK source for the cockpit HUD — the primary
// path is the browser's AnalyserNode via `useMicAnalyser`,
// which has lower latency. The fallback fires in Tauri or
// other non-browser contexts where the AnalyserNode isn't
// available. See docs/FEATURE-SPEC-SPRINT17b.md §5.4.
export interface VoiceVadAudioLevelEvent {
  type: "vad.audio_level";
  data: { session_id: string; level: number; ts_ms: number };
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
    // Sprint 17a: strict wake-phrase mode flag. When true, the
    // cockpit should pre-emptively show the "Listening for **X**…"
    // hint so the user knows why no agent reply is happening
    // if they speak without a wake phrase.
    strict_wake_phrase: boolean;
  };
}
export interface VoiceErrorEvent {
  type: "voice.error";
  data: { error: string };
}
export interface VoiceTurnEndedEvent {
  type: "voice.turn_ended";
  data: {
    session_id: string;
    discarded: boolean;
    total_duration_ms?: number;
    // Sprint 17a: optional reason code explaining why a turn
    // was discarded (or `null` for a normal completion). The
    // frontend can use this to show a brief toast:
    //   - "no_wake_phrase": strict mode on, transcript didn't
    //      start with a wake phrase
    //   - "user_cancel": user sent a `voice.cancel` mid-stream
    //   - "no_agent": no agent callback wired (debug-only)
    //   - null: normal turn completion
    reason?: "no_wake_phrase" | "user_cancel" | "no_agent" | null;
  };
}
export interface VoiceCancelledEvent {
  type: "voice.cancelled";
  data: { session_id: string };
}

export type VoiceWSEvent =
  | VoiceHelloEvent
  | VoiceVadStateEvent
  | VoiceVadAudioLevelEvent
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
  lastAudioLevel: number;
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
  lastAudioLevel: 0,
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
    lastAudioLevel: state.lastAudioLevel,
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
// Connection — with heartbeat, auto-reconnect, and dead-socket recovery
// ---------------------------------------------------------------------------
//
// The voice WebSocket can die in several ways that we used to miss:
//   - Tab backgrounded → browser suspends the socket silently (no onclose)
//   - Network blip (WiFi roaming, sleep/wake) → half-open socket
//   - Backend restart → TCP RST may take seconds to propagate
//   - Vite HMR page reload while keeping a stale module instance
//
// Each of these used to leave the panel stuck in "Ready" while the
// socket was actually CLOSED — the user would press the mic button,
// get no reaction, and have no signal that the backend was unreachable.
//
// We now:
//   1. Heartbeat: send `{type: "ping"}` every HEARTBEAT_MS, expect a
//      `pong` reply within HEARTBEAT_TIMEOUT_MS. A missed pong flips
//      the socket to dead and tears it down (which triggers reconnect).
//   2. Auto-reconnect: `onclose` schedules a reconnect with capped
//      exponential backoff (1s → 2s → 4s … → 30s). Once we reconnect
//      successfully, the backoff resets.
//   3. Dead-socket send: if `send()` is called when the socket isn't
//      OPEN, we kick off a reconnect and drop the message with a
//      warning — instead of silently no-op'ing. The UI relies on
//      a tight feedback loop, so silent drops hurt.
//   4. State honesty: any time we observe the socket in CLOSED /
//      CLOSING state but the high-level state machine still claims
//      "ready" / "listening" / "speaking", we flip to "idle" so the
//      UI doesn't lie to the user.

const HEARTBEAT_MS = 25_000;
const HEARTBEAT_TIMEOUT_MS = 10_000;
const RECONNECT_BACKOFF_BASE_MS = 1_000;
const RECONNECT_BACKOFF_MAX_MS = 30_000;

let connectAttempted = false;
let heartbeatTimer: ReturnType<typeof setInterval> | null = null;
let pongDeadline: ReturnType<typeof setTimeout> | null = null;
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
let reconnectAttempt = 0;

/** Reset the heartbeat cycle: arm the next ping, clear any pending
 *  pong-deadline timer. Called on every received message (including
 *  pong) so a chatty connection never times out spuriously. */
function noteSocketActivity(): void {
  if (pongDeadline) {
    clearTimeout(pongDeadline);
    pongDeadline = null;
  }
}

function startHeartbeat(): void {
  stopHeartbeat();
  heartbeatTimer = setInterval(() => {
    const ws = state.socket;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      // Socket disappeared underneath us — let onclose (or the next
      // send attempt) handle the recovery.
      return;
    }
    try {
      ws.send(JSON.stringify({ type: "ping", ts: Date.now() }));
    } catch (e) {
      console.warn("[Voice] heartbeat send threw, treating as dead:", e);
      forceReconnect("heartbeat_send_failed");
      return;
    }
    // Arm the deadline. If we don't see a pong (or any other frame)
    // within the timeout, the connection is half-open.
    pongDeadline = setTimeout(() => {
      const cur = state.socket;
      if (!cur || cur.readyState !== WebSocket.OPEN) return;
      console.warn("[Voice] no pong within heartbeat timeout, reconnecting");
      forceReconnect("heartbeat_timeout");
    }, HEARTBEAT_TIMEOUT_MS);
  }, HEARTBEAT_MS);
}

function stopHeartbeat(): void {
  if (heartbeatTimer) {
    clearInterval(heartbeatTimer);
    heartbeatTimer = null;
  }
  if (pongDeadline) {
    clearTimeout(pongDeadline);
    pongDeadline = null;
  }
}

/** Force-close the current socket and schedule a reconnect. The
 *  onclose handler will set state.idle + clear the socket ref. */
function forceReconnect(reason: string): void {
  console.log(`[Voice] forceReconnect: ${reason}`);
  const ws = state.socket;
  state.socket = null;
  stopHeartbeat();
  if (ws && ws.readyState <= WebSocket.OPEN) {
    try {
      ws.close(1000, reason);
    } catch (e) {
      console.warn("[Voice] close() during forceReconnect threw:", e);
    }
  }
  scheduleReconnect();
}

function scheduleReconnect(): void {
  if (reconnectTimer) return; // already scheduled
  const delay = Math.min(
    RECONNECT_BACKOFF_BASE_MS * Math.pow(2, reconnectAttempt),
    RECONNECT_BACKOFF_MAX_MS,
  );
  reconnectAttempt += 1;
  console.log(`[Voice] reconnect scheduled in ${delay}ms (attempt ${reconnectAttempt})`);
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    connectAttempted = false; // allow connect() to actually run
    connect();
  }, delay);
  // If we're still in "reconnecting" 5 s after the schedule, drop
  // the badge to "Disconnected" so the user knows the panel is
  // waiting for them. The reconnect itself still runs in the
  // background — when it succeeds, onopen flips us back to "ready".
  setTimeout(() => {
    if (state.state === "reconnecting") {
      setState({ state: "idle" });
    }
  }, 5_000);
}

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
    reconnectAttempt = 0; // reset backoff on successful connect
    setState({ state: "ready" });
    startHeartbeat();
  };

  ws.onclose = () => {
    console.log("[Voice] disconnected");
    stopHeartbeat();
    setState({
      state: "reconnecting",
      socket: null,
      currentSession: null,
    });
    connectAttempted = false;
    // Auto-reconnect unless the page is being torn down. We can't
    // detect that perfectly, but the next send()/heartbeat tick will
    // reconnect if the user is still around.
    if (typeof document !== "undefined" && document.visibilityState !== "hidden") {
      scheduleReconnect();
    }
  };

  ws.onerror = () => {
    setState({ error: "WebSocket error" });
    // onclose will follow and trigger the reconnect — don't double up.
  };

  ws.onmessage = (msg) => {
    noteSocketActivity();
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

/** Public test-helper + dev-console API: trigger a forced reconnect
 *  with the same backoff as a normal failure. Useful when the user
 *  suspects the panel is stuck — call from the JS console. */
export function forceVoiceReconnect(reason = "manual"): void {
  forceReconnect(reason);
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
    case "vad.audio_level": {
      // Sprint 17b Track E: per-frame audio level broadcast
      // at 20Hz. We surface it via VoiceStatus.lastAudioLevel
      // (the primary path is the browser's AnalyserNode; this
      // server-broadcast value is the fallback for Tauri
      // and other non-browser contexts).
      const d = (event as VoiceVadAudioLevelEvent).data;
      setState({ lastAudioLevel: d.level });
      break;
    }
    case "asr.result": {
      const d = (event as VoiceTranscriptEvent).data;
      setState({ lastAsr: d.text, state: "thinking" });
      break;
    }
    case "agent.message": {
      const d = (event as VoiceAgentMessageEvent).data;
      // M15: agent streams sentence-by-sentence. The server
      // accumulates text across frames and re-sends the running total
      // on each `is_final: false`, then a final `is_final: true`
      // frame. Update `lastReply` on every frame so the cockpit
      // transcript grows incrementally as the agent speaks.
      setState({ lastReply: d.text, emotion: d.emotion });
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
    case "pong": {
      // Heartbeat response — already cleared the pong-deadline
      // in noteSocketActivity() before reaching handleEvent, but
      // we treat this as the canonical "alive" signal. If the
      // socket was previously thought dead, surface that recovery
      // in the console.
      if (pongDeadline === null) {
        // Heartbeat wasn't actually armed — likely an unsolicited
        // pong. Harmless.
      }
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
    // Dead-socket send — common after a tab background, network blip,
    // or backend restart. Don't silently drop the message; kick off
    // a reconnect and warn so the user can see in DevTools that
    // something went wrong.
    console.warn(
      "[Voice] cannot send, socket not open — scheduling reconnect",
      payload,
    );
    if (!reconnectTimer) {
      forceReconnect("dead_socket_send");
    }
    return;
  }
  // Binary PCM chunks must go through raw — `JSON.stringify(new ArrayBuffer(...))`
  // collapses to `"{}"`, which the backend rejects with `unknown_type: None`
  // and spams the voice-error toast. Detect and pass through.
  if (payload instanceof ArrayBuffer) {
    try {
      ws.send(payload);
    } catch (e) {
      console.warn("[Voice] ws.send(binary) threw, forcing reconnect:", e);
      forceReconnect("binary_send_threw");
    }
    return;
  }
  try {
    ws.send(typeof payload === "string" ? payload : JSON.stringify(payload));
  } catch (e) {
    console.warn("[Voice] ws.send(text) threw, forcing reconnect:", e);
    forceReconnect("text_send_threw");
  }
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

  // When the user returns to the tab after a long background, the
  // WebSocket is often half-open (browser suspended the underlying
  // socket without firing onclose). Probing the socket on visibility
  // change and forcing a reconnect if it's not actually OPEN turns
  // a silent stall into a 1-2 s recovery.
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState !== "visible") return;
    const ws = state.socket;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      console.log("[Voice] tab visible, socket not open — forcing reconnect");
      forceReconnect("tab_visible");
    } else {
      // Socket looks alive but may be half-open. Trigger a ping
      // immediately; if we don't see a pong, forceReconnect will fire
      // from the heartbeat deadline path.
      try {
        ws.send(JSON.stringify({ type: "ping", ts: Date.now() }));
      } catch (e) {
        console.warn("[Voice] visibility-ping send threw:", e);
        forceReconnect("visibility_ping_failed");
      }
    }
  });
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

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
 *
 * Sprint 32 P1.2 refactor: connect / reconnect / heartbeat / dead-socket
 * detection / binary frame handling are now in `lib/ws-base.ts::
 * BaseWebSocketClient`. This module owns:
 *   1. The voice event/state types (`VoiceWSEvent`, `VoiceStatus`).
 *   2. The `VoiceWsClient` singleton — a thin subclass that wires
 *      heartbeat, `binaryType = "arraybuffer"`, and the voice
 *      state-machine reducer.
 *   3. The voice-specific turn control helpers (`voiceBegin`,
 *      `voiceSendAudio`, `voiceEnd`, `voiceText`, `voiceCancel`,
 *      `voicePing`) that wrap the base client's `send()`.
 *   4. The voice console debug API (`window.__haloVoice`).
 */

import { BaseWebSocketClient, wsUrlFromApi } from "@/lib/ws-base";

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
  | (VoiceHelloEvent & { [key: string]: unknown })
  | (VoiceVadStateEvent & { [key: string]: unknown })
  | (VoiceVadAudioLevelEvent & { [key: string]: unknown })
  | (VoiceTranscriptEvent & { [key: string]: unknown })
  | (VoiceAgentMessageEvent & { [key: string]: unknown })
  | (VoiceTtsStartEvent & { [key: string]: unknown })
  | (VoiceTtsEndEvent & { [key: string]: unknown })
  | (VoiceLive2DTriggerEvent & { [key: string]: unknown })
  | (VoiceErrorEvent & { [key: string]: unknown })
  | (VoiceTurnEndedEvent & { [key: string]: unknown })
  | (VoiceCancelledEvent & { [key: string]: unknown })
  | { type: string; [key: string]: unknown };

export type VoiceEventHandler = (event: VoiceWSEvent) => void;
export type BinaryHandler = (chunk: ArrayBuffer) => void;

// ---------------------------------------------------------------------------
// State machine
// ---------------------------------------------------------------------------

interface VoiceState_ {
  state: VoiceState;
  lastAsr: string | null;
  lastReply: string | null;
  emotion: string | null;
  serverEnabled: boolean;
  error: string | null;
  sampleRate: number;
  lastAudioLevel: number;
  currentSession: string | null;
}

const INITIAL: VoiceState_ = {
  state: "idle",
  lastAsr: null,
  lastReply: null,
  emotion: null,
  serverEnabled: false,
  error: null,
  sampleRate: 0,
  lastAudioLevel: 0,
  currentSession: null,
};

// ---------------------------------------------------------------------------
// Singleton wrapper around BaseWebSocketClient
// ---------------------------------------------------------------------------

class VoiceWsClient extends BaseWebSocketClient<VoiceWSEvent, ArrayBuffer> {
  // State machine lives on the singleton instance so React-style
  // listeners (via `onVoiceStatusChange`) see live updates.
  protected voiceState: VoiceState_ = { ...INITIAL };
  private statusCbs = new Set<(s: VoiceStatus) => void>();

  protected override get logTag(): string {
    return "[Voice]";
  }

  protected override getUrl(): string {
    return wsUrlFromApi("/ws/voice");
  }

  // Voice WS uses heartbeat (ping/pong) to detect half-open sockets
  // caused by tab backgrounding / WiFi roaming / backend restarts.
  protected override get heartbeatEnabled(): boolean {
    return true;
  }

  protected override get usesBinary(): boolean {
    return true;
  }

  protected override onConnected(): void {
    this.voiceState.state = "ready";
    this.notifyStatus();
  }

  protected override onDisconnected(): void {
    // The base class schedules a reconnect; the state machine
    // claims "reconnecting" so the UI shows the spinner. If we're
    // still claiming it 5 s later (handled by base class via the
    // 5s stale-reconnect fallback), the user sees "idle".
    this.voiceState.state = "reconnecting";
    this.voiceState.currentSession = null;
    this.notifyStatus();
  }

  protected override onError(): void {
    this.setVoiceState({ error: "WebSocket error" });
  }

  /** Heartbeat reply detection — the server sends `{ type: "pong" }`. */
  protected override isHeartbeatPong(event: VoiceWSEvent): boolean {
    return event.type === "pong";
  }

  /** Per-event state machine. Fires BEFORE pub/sub fanout. */
  protected override handleEvent(event: VoiceWSEvent): void {
    switch (event.type) {
      case "voice.hello": {
        const d = (event as VoiceHelloEvent).data;
        this.setVoiceState({
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
          this.setVoiceState({ state: "listening" });
        } else {
          // speech_end — server is about to start ASR. Stay in
          // "listening" (caller will see "thinking" once we get
          // asr.result + agent processing).
          this.setVoiceState({ state: "listening" });
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
        this.setVoiceState({ lastAudioLevel: d.level });
        break;
      }
      case "asr.result": {
        const d = (event as VoiceTranscriptEvent).data;
        this.setVoiceState({ lastAsr: d.text, state: "thinking" });
        break;
      }
      case "agent.message": {
        const d = (event as VoiceAgentMessageEvent).data;
        // M15: agent streams sentence-by-sentence. The server
        // accumulates text across frames and re-sends the running total
        // on each `is_final: false`, then a final `is_final: true`
        // frame. Update `lastReply` on every frame so the cockpit
        // transcript grows incrementally as the agent speaks.
        this.setVoiceState({ lastReply: d.text, emotion: d.emotion });
        break;
      }
      case "tts.start": {
        this.setVoiceState({ state: "speaking" });
        break;
      }
      case "tts.end": {
        // TTS finished, but server may still send more tts chunks for
        // multi-sentence replies. Stay in "speaking" until turn_ended.
        break;
      }
      case "live2d.trigger": {
        const d = (event as VoiceLive2DTriggerEvent).data;
        this.setVoiceState({ emotion: d.emotion });
        break;
      }
      case "voice.turn_ended": {
        this.setVoiceState({ state: "ready", currentSession: null });
        break;
      }
      case "voice.cancelled": {
        this.setVoiceState({ state: "ready", currentSession: null });
        break;
      }
      case "voice.error": {
        const d = (event as VoiceErrorEvent).data;
        this.setVoiceState({ state: "error", error: d.error });
        break;
      }
      case "pong": {
        // Heartbeat response — base class already cleared the
        // pong-deadline in noteSocketActivity() before reaching
        // handleEvent. Nothing else to do here.
        break;
      }
    }
  }

  private setVoiceState(patch: Partial<VoiceState_>): void {
    this.voiceState = { ...this.voiceState, ...patch };
    this.notifyStatus();
  }

  private notifyStatus(): void {
    const snap = this.snapshot();
    for (const cb of this.statusCbs) {
      try {
        cb(snap);
      } catch (e) {
        console.warn("[Voice] state cb threw:", e);
      }
    }
  }

  snapshot(): VoiceStatus {
    return {
      state: this.voiceState.state,
      lastAsr: this.voiceState.lastAsr,
      lastReply: this.voiceState.lastReply,
      emotion: this.voiceState.emotion,
      serverEnabled: this.voiceState.serverEnabled,
      error: this.voiceState.error,
      sampleRate: this.voiceState.sampleRate,
      lastAudioLevel: this.voiceState.lastAudioLevel,
    };
  }

  /** Allow the public `voiceBegin` helper to write the session id
   *  onto the singleton. Other callers should use the public API. */
  setCurrentSession(sid: string | null): void {
    this.voiceState.currentSession = sid;
  }

  /** Allow the public `voiceText` helper to read the current session
   *  id (or null if none). */
  getCurrentSession(): string | null {
    return this.voiceState.currentSession;
  }

  /** Reset to the initial state (used by `voiceBegin`'s auto-reset
   *  path when called while not in ready/idle). */
  resetToListening(): void {
    this.setVoiceState({ state: "listening", error: null });
  }

  resetToThinking(): void {
    this.setVoiceState({ state: "thinking", error: null });
  }

  /** Subscribe to status changes — the React bridge hook. */
  subscribeStatus(cb: (s: VoiceStatus) => void): () => void {
    this.statusCbs.add(cb);
    return () => {
      this.statusCbs.delete(cb);
    };
  }
}

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
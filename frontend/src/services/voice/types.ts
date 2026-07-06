/**
 * Voice WebSocket service — types.
 *
 * Sprint 56 R7: extracted from `services/halo-voice-ws.ts` (532
 * LoC monolith). This module owns the 11 voice event + state
 * type definitions. No runtime code — pure TS types + the
 * `VoiceState` string-union and `VoiceWSEvent` discriminated
 * union.
 */

// ---------------------------------------------------------------------------
// State machine types
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

// ---------------------------------------------------------------------------
// Wire-protocol event types
// ---------------------------------------------------------------------------

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

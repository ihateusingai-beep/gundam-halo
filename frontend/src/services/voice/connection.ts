/**
 * Voice WebSocket — connection + state machine.
 *
 * Sprint 56 R7: extracted from `services/halo-voice-ws.ts` (532
 * LoC monolith). This module owns the `VoiceWsClient` class —
 * a thin subclass of `BaseWebSocketClient` that adds:
 *   1. The voice state-machine reducer (idle → ready →
 *      listening → thinking → speaking → ready).
 *   2. Per-event handlers (the 11-case switch on
 *      `VoiceWSEvent.type`).
 *   3. Heartbeat reply detection (`pong` event).
 *   4. The status-snapshot pub/sub for React bridges.
 *
 * The actual socket lifecycle (connect / reconnect / heartbeat
 * deadline / dead-socket detection) lives in `BaseWebSocketClient`
 * (Sprint 32 P1.2) — see `lib/ws-base.ts`.
 *
 * No public API lives here — `voice/api.ts` exposes the
 * `voiceBegin` / `voiceSendAudio` / etc. helpers and the
 * singleton.
 */

import { BaseWebSocketClient, wsUrlFromApi } from "@/lib/ws-base";

import type {
  VoiceAgentMessageEvent,
  VoiceCancelledEvent,
  VoiceErrorEvent,
  VoiceEventHandler,
  VoiceHelloEvent,
  VoiceLive2DTriggerEvent,
  BinaryHandler,
  VoiceState,
  VoiceStatus,
  VoiceTranscriptEvent,
  VoiceTurnEndedEvent,
  VoiceTtsEndEvent,
  VoiceTtsStartEvent,
  VoiceVadAudioLevelEvent,
  VoiceVadStateEvent,
  VoiceWSEvent,
} from "./types";

// ---------------------------------------------------------------------------
// Internal state shape (extends VoiceStatus with the in-flight
// session id, which isn't surfaced to React)
// ---------------------------------------------------------------------------

interface VoiceState_ extends VoiceStatus {
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
// VoiceWsClient class
// ---------------------------------------------------------------------------

export class VoiceWsClient extends BaseWebSocketClient<VoiceWSEvent, ArrayBuffer> {
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

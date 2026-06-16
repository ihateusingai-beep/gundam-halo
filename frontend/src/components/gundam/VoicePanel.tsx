/**
 * VoicePanel — push-to-talk control + status, lives in the cockpit
 * right panel above the avatar.
 *
 * Flow:
 *   idle ──[press & hold]──> requesting ──> capturing
 *   capturing ──[release]──> sends PCM chunks to /ws/voice
 *   server runs VAD → ASR → agent → TTS
 *   agent.message updates the panel reply text
 *   tts.start / tts.audio plays the reply through a <audio> element
 */

import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import type { UseVoiceInputResult } from "@/hooks/use-voice-input";
import { api } from "@/lib/api";
import { WakePhraseHint } from "@/components/gundam/WakePhraseHint";
import {
  getVoiceStatus,
  onVoiceBinary,
  onVoiceStatusChange,
  subscribeToVoiceEvent,
  voiceCancel,
  voiceText as sendTextTurn,
  type VoiceStatus,
} from "@/services/halo-voice-ws";

const STATE_LABEL: Record<VoiceStatus["state"], string> = {
  idle: "Disconnected",
  ready: "Ready — hold to talk",
  listening: "Listening…",
  thinking: "Thinking…",
  speaking: "Speaking…",
  reconnecting: "Reconnecting…",
  error: "Error",
};

const STATE_COLOR: Record<VoiceStatus["state"], string> = {
  idle: "var(--text-muted)",
  ready: "var(--success)",
  listening: "var(--accent)",
  thinking: "var(--warning)",
  speaking: "var(--accent-secondary)",
  reconnecting: "var(--warning)",
  error: "var(--danger)",
};

const STATE_GLYPH: Record<VoiceStatus["state"], string> = {
  idle: "○",
  ready: "●",
  listening: "◉",
  thinking: "⌛",
  speaking: "▶",
  reconnecting: "↻",
  error: "✕",
};

export interface VoicePanelProps {
  /**
   * Sprint 18 Track A: the mic hook is hoisted to CockpitLayout
   * so the right column can share the stream with the audio-reactive
   * CyberWaveform above. VoicePanel receives the `mic` object
   * (state / error / start / stop / stream) as a prop and uses it
   * for the push-to-talk button. The contract of `useVoiceInput`
   * is unchanged — we just moved ownership up one level.
   */
  mic: UseVoiceInputResult;
  /**
   * Sprint 19c: when true, the cockpit is in always-on
   * mic mode. The big push-to-talk button is replaced
   * with a ⏸ / ▶ toggle. The mic capture lifecycle is
   * owned by the parent (CockpitLayout mounts
   * useVadStateAutoFire); the button only flips the
   * pause flag.
   */
  alwaysOn?: boolean;
  /**
   * Sprint 19c: the current pause state. Read by
   * useVadStateAutoFire to ignore VAD events when the
   * user has muted the mic. Paired with onPausedChange.
   */
  paused?: boolean;
  /**
   * Sprint 19c: setter for the pause state. The ⏸
   * button in this component calls this with !paused.
   */
  onPausedChange?: (paused: boolean) => void;
}

export function VoicePanel({
  mic,
  alwaysOn = false,
  paused = false,
  onPausedChange,
}: VoicePanelProps) {
  const [status, setStatus] = useState<VoiceStatus>(() => getVoiceStatus());
  const [textInput, setTextInput] = useState("");
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const audioQueueRef = useRef<ArrayBuffer[]>([]);
  // M10-A Plan A4: sequenceId bumps on every enqueue so stale in-flight
  // frames abort their onended chain instead of triggering the next chunk.
  // (Previously two simultaneous frames would race on isPlayingRef and
  // could overlap or play a frame past the queue head.)
  const playSeqRef = useRef(0);
  const drainingRef = useRef(false);

  // Subscribe to state changes
  useEffect(() => {
    return onVoiceStatusChange(setStatus);
  }, []);

  // M10-A Plan A4: when the turn ends (state goes back to ready/idle/error
  // from speaking), bump the play seq so any in-flight drain chain aborts
  // and clear the queue. This prevents stale frames from playing after
  // the user pressed ✕ or after a new turn boundary.
  useEffect(() => {
    if (status.state === "ready" || status.state === "idle" || status.state === "error") {
      playSeqRef.current += 1;
      audioQueueRef.current = [];
      drainingRef.current = false;
    }
  }, [status.state]);

  // Subscribe to all events for toast notifications + state debug
  useEffect(() => {
    const unsub = subscribeToVoiceEvent("*", (e) => {
      if (e.type === "voice.error") {
        toast.error("Voice error", {
          description: (e as { data: { error: string } }).data.error,
        });
      }
    });
    return unsub;
  }, []);

  // TTS audio playback: enqueue binary frames, drain sequentially.
  useEffect(() => {
    return onVoiceBinary((chunk) => {
      audioQueueRef.current.push(chunk);
      void drainAudioQueue();
    });
  }, []);

  async function drainAudioQueue(): Promise<void> {
    // Sequential drain: only one drain chain runs at a time. Stale chains
    // exit early if playSeqRef moved past the version they were started
    // with (e.g. user pressed ✕ Cancel, or new turn superseded).
    if (drainingRef.current) return;
    drainingRef.current = true;
    const mySeq = playSeqRef.current;

    try {
      while (audioQueueRef.current.length > 0) {
        if (mySeq !== playSeqRef.current) return; // superseded
        const next = audioQueueRef.current.shift();
        if (!next) return;
        try {
          await playChunk(next);
        } catch (err) {
          // Swallow per-chunk errors so one bad frame doesn't kill the queue.
          console.warn("[VoicePanel] TTS chunk play failed:", err);
        }
        if (mySeq !== playSeqRef.current) return;
      }
    } finally {
      drainingRef.current = false;
    }
  }

  function playChunk(chunk: ArrayBuffer): Promise<void> {
    return new Promise((resolve) => {
      // Wrap MP3 bytes in a Blob URL. edge-tts output (see `voice_ws.py`
      // + `tts_factory`) is already encoded as MP3.
      const blob = new Blob([chunk], { type: "audio/mpeg" });
      const url = URL.createObjectURL(blob);
      const audio = audioRef.current ?? new Audio();
      audioRef.current = audio;

      const cleanup = () => {
        URL.revokeObjectURL(url);
        audio.onended = null;
        audio.onerror = null;
        resolve();
      };
      audio.onended = cleanup;
      audio.onerror = cleanup;
      audio.src = url;
      audio.play().catch((err) => {
        console.warn("[VoicePanel] audio.play() rejected:", err);
        cleanup();
      });
    });
  }

  // Sprint 16: fetch the active wake phrases on mount so the
  // WakePhraseHint can render the "Listening for **X**" affordance.
  // We refetch when the page gains focus (Settings → Voice tab
  // edits) so the hint updates without a full reload.
  const [wakePhrases, setWakePhrases] = useState<string[]>([]);
  useEffect(() => {
    let alive = true;
    const fetchPhrases = () => {
      api
        .getVoiceConfig()
        .then((d) => {
          if (alive) setWakePhrases(d.wake_phrases ?? []);
        })
        .catch(() => {
          /* non-fatal — the hint just stays hidden */
        });
    };
    fetchPhrases();
    const onVis = () => {
      if (document.visibilityState === "visible") fetchPhrases();
    };
    document.addEventListener("visibilitychange", onVis);
    window.addEventListener("focus", fetchPhrases);
    return () => {
      alive = false;
      document.removeEventListener("visibilitychange", onVis);
      window.removeEventListener("focus", fetchPhrases);
    };
  }, []);

  // Sprint 18 Track A: `mic` is now provided as a prop from
  // CockpitLayout (see VoicePanelProps). The hook used to live
  // here; ownership moved up so the right column's CyberWaveform
  // can subscribe to the same `mic.stream` without opening a
  // second getUserMedia. The contract of `useVoiceInput` is
  // unchanged — we still expose {state, error, start, stop, stream}.
  // The voiceBegin/voiceEnd/voiceSendAudio callbacks are wired
  // inside the parent so the lifecycle of the WS turn is
  // co-located with the lifecycle of the mic stream.

  // Pressable in any state where the mic system can accept a new
  // press. `reconnecting` covers the case where the voice WS died
  // but the user is still trying to talk — `send()` will kick the
  // socket back into life and start the turn once it reconnects.
  const isPressable =
    mic.state === "ready" ||
    mic.state === "idle" ||
    status.state === "reconnecting";
  const isHolding = mic.state === "capturing";

  function handleTextSubmit() {
    if (!textInput.trim()) return;
    sendTextTurn(textInput);
    setTextInput("");
  }

  return (
    <div className="space-y-2">
      {/* State badge */}
      <div className="flex items-center justify-between">
        <span className="text-xs font-[Orbitron] text-[var(--accent)] uppercase tracking-widest">
          Voice
        </span>
        <span
          className="text-[10px] font-mono flex items-center gap-1.5"
          style={{ color: STATE_COLOR[status.state] }}
        >
          <span style={{ fontSize: "11px" }}>{STATE_GLYPH[status.state]}</span>
          {STATE_LABEL[status.state]}
        </span>
      </div>

      {/* Mic control — push-to-talk button OR always-on
          pause toggle, depending on `alwaysOn` */}
      <div className="flex flex-col items-center gap-1.5 py-2">
        {alwaysOn ? (
          // Sprint 19c: always-on mode. The mic is
          // always live; this button just flips the
          // pause flag. The agent fires automatically
          // on the backend's VAD speech_start events
          // (useVadStateAutoFire in CockpitLayout).
          <>
            <button
              onClick={() => onPausedChange?.(!paused)}
              disabled={mic.state === "unsupported" || mic.state === "denied"}
              data-testid="voice-panel-always-on-toggle"
              className={[
                "relative w-20 h-20 rounded-full border-2 flex items-center justify-center text-3xl",
                "transition-all select-none cursor-pointer",
                "voice-mic",
                !paused && mic.state === "capturing" && "border-[var(--success)] bg-[var(--success)]/20 text-[var(--success)] scale-105",
                !paused && mic.state !== "capturing" && "border-[var(--accent)] bg-[var(--bg-elevated)] text-[var(--accent)]",
                paused && "border-[var(--warning)] bg-[var(--warning)]/20 text-[var(--warning)]",
                mic.state === "denied" && "border-[var(--danger)] text-[var(--danger)] cursor-not-allowed",
                mic.state === "unsupported" && "border-[var(--text-muted)] text-[var(--text-muted)] cursor-not-allowed",
                mic.state === "error" && "border-[var(--danger)] text-[var(--danger)]",
              ]
                .filter(Boolean)
                .join(" ")}
              title={
                mic.state === "denied"
                  ? "Microphone permission denied"
                  : mic.state === "unsupported"
                  ? "Browser doesn't support microphone"
                  : paused
                  ? "Tap to resume listening"
                  : "Tap to pause listening"
              }
            >
              {paused ? "▶" : "⏸"}
            </button>
            <span className="text-[9px] text-[var(--text-muted)] font-mono uppercase tracking-wider">
              {mic.state === "denied"
                ? "Mic denied"
                : mic.state === "unsupported"
                ? "Not supported"
                : paused
                ? "Paused — tap to resume"
                : mic.state === "capturing"
                ? "Listening…"
                : "Always-on"}
            </span>
          </>
        ) : (
          // Default: Sprint 16 push-to-talk. The user
          // presses and holds the big 🎤 button to
          // talk.
          <>
            <button
              onMouseDown={() => isPressable && mic.start()}
              onMouseUp={() => isHolding && mic.stop()}
              onMouseLeave={() => isHolding && mic.stop()}
              onTouchStart={(e) => {
                e.preventDefault();
                isPressable && mic.start();
              }}
              onTouchEnd={() => isHolding && mic.stop()}
              disabled={mic.state === "unsupported" || mic.state === "denied"}
              className={[
                "relative w-20 h-20 rounded-full border-2 flex items-center justify-center text-3xl",
                "transition-all select-none touch-none",
                "voice-mic",
                isPressable && "border-[var(--accent)] bg-[var(--bg-elevated)] text-[var(--accent)] hover:scale-105 cursor-pointer",
                isHolding && "voice-mic--listening border-[var(--accent-secondary)] bg-[var(--accent-secondary)]/20 text-[var(--accent-secondary)] scale-110",
                status.state === "thinking" && "voice-mic--thinking border-[var(--warning)] text-[var(--warning)]",
                status.state === "speaking" && "voice-mic--speaking border-[var(--accent-secondary)] text-[var(--accent-secondary)]",
                mic.state === "denied" && "border-[var(--danger)] text-[var(--danger)] cursor-not-allowed",
                mic.state === "unsupported" && "border-[var(--text-muted)] text-[var(--text-muted)] cursor-not-allowed",
                mic.state === "error" && "border-[var(--danger)] text-[var(--danger)]",
              ]
                .filter(Boolean)
                .join(" ")}
              title={
                mic.state === "denied"
                  ? "Microphone permission denied"
                  : mic.state === "unsupported"
                  ? "Browser doesn't support microphone"
                  : "Hold to talk"
              }
            >
              🎤
              {isHolding && (
                <span className="absolute inset-0 rounded-full border-2 border-[var(--accent-secondary)] animate-ping pointer-events-none" />
              )}
            </button>
            <span className="text-[9px] text-[var(--text-muted)] font-mono uppercase tracking-wider">
              {mic.state === "denied"
                ? "Mic denied"
                : mic.state === "unsupported"
                ? "Not supported"
                : isHolding
                ? "Release to send"
                : "Hold to talk"}
            </span>
          </>
        )}
        {/* Sprint 16: wake-phrase hint. Hidden when the mic is
            unavailable or the user has cleared the phrase list. */}
        <WakePhraseHint
          phrases={wakePhrases}
          hidden={
            mic.state === "denied" ||
            mic.state === "unsupported" ||
            mic.state === "error"
          }
        />
      </div>

      {mic.error && (
        <div className="space-y-1.5 pt-1.5 border-t border-[var(--border-color)]/50">
          <p className="text-[10px] text-[var(--danger)] font-mono leading-tight">
            ⚠ {mic.error}
          </p>
          {/* When mic permission was denied, surface a recovery
              affordance: a one-click retry that re-asks Chrome
              (Chrome only re-prompts on a user gesture), and a
              link to the full setup guide. The retry button is
              hidden for non-permission errors (NotFoundError,
              OverconstrainedError, etc.) because re-clicking won't
              help there. */}
          {mic.state === "denied" && (
            <div className="flex items-center gap-1.5 flex-wrap">
              <button
                onClick={() => void mic.start()}
                className="px-2 py-0.5 text-[9px] uppercase tracking-wider font-[Rajdhani] border border-[var(--accent)] text-[var(--accent)] hover:bg-[var(--accent)] hover:text-[var(--bg-primary)] transition-colors"
                title="Chrome re-prompts for mic permission on user gesture"
              >
                Retry
              </button>
              <a
                href="/docs/MICROPHONE-PERMISSION.md"
                target="_blank"
                rel="noreferrer"
                className="px-2 py-0.5 text-[9px] uppercase tracking-wider font-[Rajdhani] border border-[var(--border-color)] text-[var(--text-muted)] hover:border-[var(--accent)] hover:text-[var(--accent)] transition-colors"
              >
                Setup guide ↗
              </a>
              <button
                onClick={async () => {
                  try {
                    await navigator.clipboard.writeText(
                      "chrome://settings/content/microphone"
                    );
                    toast.success("URL copied", {
                      description: "Paste into Chrome to open mic settings.",
                    });
                  } catch {
                    /* ignore */
                  }
                }}
                className="px-2 py-0.5 text-[9px] uppercase tracking-wider font-[Rajdhani] border border-[var(--border-color)] text-[var(--text-muted)] hover:border-[var(--accent)] hover:text-[var(--accent)] transition-colors"
                title="Copy the Chrome mic settings URL"
              >
                Copy settings URL
              </button>
            </div>
          )}
        </div>
      )}

      {/* Last exchange (ASR ↔ reply) */}
      {(status.lastAsr || status.lastReply) && (
        <div className="space-y-1.5 pt-2 border-t border-[var(--border-color)]">
          {status.lastAsr && (
            <div>
              <div className="text-[9px] text-[var(--text-muted)] uppercase tracking-wider font-mono">
                You
              </div>
              <p className="text-[11px] text-[var(--text-primary)] font-mono leading-tight">
                {status.lastAsr}
              </p>
            </div>
          )}
          {status.lastReply && (
            <div>
              <div className="text-[9px] text-[var(--text-muted)] uppercase tracking-wider font-mono">
                Gundam
              </div>
              <p className="text-[11px] text-[var(--accent)] font-mono leading-tight">
                {status.lastReply}
              </p>
            </div>
          )}
        </div>
      )}

      {/* Text bypass — for when you'd rather type */}
      <div className="pt-2 border-t border-[var(--border-color)]">
        <div className="text-[9px] text-[var(--text-muted)] uppercase tracking-wider font-mono mb-1">
          Or type (bypasses ASR)
        </div>
        <div className="flex gap-1">
          <input
            type="text"
            value={textInput}
            onChange={(e) => setTextInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleTextSubmit()}
            placeholder="summarize my todo.md"
            className="flex-1 bg-[var(--bg-input)] border border-[var(--border-color)] rounded px-2 py-1 text-[10px] font-mono text-[var(--text-primary)] focus:outline-none focus:border-[var(--accent)] placeholder:text-[var(--text-muted)]/50"
          />
          <button
            onClick={handleTextSubmit}
            disabled={!textInput.trim()}
            className="px-2 py-1 text-[9px] uppercase tracking-wider font-[Rajdhani] border border-[var(--accent)] text-[var(--accent)] hover:bg-[var(--accent)] hover:text-[var(--bg-primary)] transition-colors disabled:opacity-40"
          >
            Send
          </button>
          {status.state === "thinking" || status.state === "speaking" ? (
            <button
              onClick={() => voiceCancel()}
              title="Cancel in-flight turn"
              className="px-2 py-1 text-[9px] uppercase tracking-wider font-[Rajdhani] border border-[var(--danger)] text-[var(--danger)] hover:bg-[var(--danger)] hover:text-[var(--bg-primary)] transition-colors"
            >
              ✕
            </button>
          ) : null}
        </div>
      </div>

      {/* Hidden audio element for TTS playback */}
      <audio ref={audioRef} hidden />
    </div>
  );
}

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

import { useVoiceInput } from "@/hooks/use-voice-input";
import {
  getVoiceStatus,
  onVoiceBinary,
  onVoiceStatusChange,
  subscribeToVoiceEvent,
  voiceBegin,
  voiceCancel,
  voiceEnd,
  voiceText as sendTextTurn,
  type VoiceStatus,
  type VoiceWSEvent,
} from "@/services/halo-voice-ws";

const STATE_LABEL: Record<VoiceStatus["state"], string> = {
  idle: "Disconnected",
  ready: "Ready — hold to talk",
  listening: "Listening…",
  thinking: "Thinking…",
  speaking: "Speaking…",
  error: "Error",
};

const STATE_COLOR: Record<VoiceStatus["state"], string> = {
  idle: "var(--text-muted)",
  ready: "var(--success)",
  listening: "var(--accent)",
  thinking: "var(--warning)",
  speaking: "var(--accent-secondary)",
  error: "var(--danger)",
};

const STATE_GLYPH: Record<VoiceStatus["state"], string> = {
  idle: "○",
  ready: "●",
  listening: "◉",
  thinking: "⌛",
  speaking: "▶",
  error: "✕",
};

export function VoicePanel() {
  const [status, setStatus] = useState<VoiceStatus>(() => getVoiceStatus());
  const [textInput, setTextInput] = useState("");
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const audioQueueRef = useRef<ArrayBuffer[]>([]);
  const isPlayingRef = useRef(false);

  // Subscribe to state changes
  useEffect(() => {
    return onVoiceStatusChange(setStatus);
  }, []);

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

  // TTS audio playback: enqueue binary frames, drain via <audio> element
  useEffect(() => {
    return onVoiceBinary((chunk) => {
      audioQueueRef.current.push(chunk);
      drainAudioQueue();
    });
  }, []);

  function drainAudioQueue() {
    if (isPlayingRef.current) return;
    const next = audioQueueRef.current.shift();
    if (!next) return;
    isPlayingRef.current = true;
    // Wrap the PCM in a Blob with an audio MIME that the browser can
    // play. edge-tts outputs MP3 by default — the server already encodes
    // it (see `voice_ws.py` — it uses the `tts_factory` to produce MP3).
    // So we just feed the bytes to <audio src=blob:...>.
    const blob = new Blob([next], { type: "audio/mpeg" });
    const url = URL.createObjectURL(blob);
    const audio = audioRef.current ?? new Audio();
    audioRef.current = audio;
    audio.src = url;
    audio.onended = () => {
      URL.revokeObjectURL(url);
      isPlayingRef.current = false;
      drainAudioQueue();
    };
    audio.onerror = () => {
      URL.revokeObjectURL(url);
      isPlayingRef.current = false;
      drainAudioQueue();
    };
    audio.play().catch(() => {
      isPlayingRef.current = false;
    });
  }

  const mic = useVoiceInput({
    onFrame: (pcm) => {
      // Lazily lazy-import to avoid a circular dep at module load
      import("@/services/halo-voice-ws").then((m) => m.voiceSendAudio(pcm));
    },
    onStart: () => {
      try {
        voiceBegin();
      } catch (e) {
        toast.error("Voice WS not connected", { description: String(e) });
      }
    },
    onStop: () => {
      try {
        voiceEnd();
      } catch (e) {
        toast.error("Voice WS send failed", { description: String(e) });
      }
    },
  });

  const isPressable = mic.state === "ready" || mic.state === "idle";
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

      {/* Push-to-talk button (big, central) */}
      <div className="flex flex-col items-center gap-1.5 py-2">
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
      </div>

      {mic.error && (
        <p className="text-[10px] text-[var(--danger)] font-mono leading-tight">
          ⚠ {mic.error}
        </p>
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

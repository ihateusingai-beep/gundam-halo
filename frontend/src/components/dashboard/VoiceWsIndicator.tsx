/**
 * VoiceWsIndicator — Sprint 39 cockpit card.
 *
 * Surfaces the live `/ws/voice` connection state on the home
 * page so the pilot can see at a glance whether the voice
 * link is up, in a transition, or reconnecting. Without this
 * card the only place to see WS state is the Settings →
 * Voice tab, which is two clicks away.
 *
 * Data source: `services/halo-voice-ws.ts::getVoiceStatus()`
 * — the singleton accessor the cockpit already polls in
 * `routes/settings/VoiceTab.tsx`. We poll the same singleton
 * on a 2 s interval so the pill stays current with the
 * BaseWebSocketClient's auto-reconnect logic (Sprint 32 P1.2).
 *
 * State → colour mapping:
 *   - idle           → grey   (not connected — no action)
 *   - ready          → cyan   (connected, idle, ready to listen)
 *   - listening      → blue   (mic open, streaming audio)
 *   - thinking       → magenta (ASR done, waiting for agent)
 *   - speaking       → orange (TTS playing)
 *   - reconnecting   → pink   (auto-reconnect in flight)
 *   - error          → red    (last attempt failed; check error msg)
 *
 * The card surfaces `voiceStatus.lastAsr` (the most recent
 * transcript) so the pilot sees the last thing they said —
 * useful when debugging "why didn't the agent respond?".
 *
 * Graceful: if `window.__haloVoice` isn't registered (Tauri
 * boot race), the card renders "unavailable" instead of
 * crashing. The cockpit stays usable.
 */

import { useEffect, useState } from "react";

import { HudCard } from "@/components/gundam/HudCard";
import type { VoiceState } from "@/services/halo-voice-ws";
import { getVoiceStatus } from "@/services/halo-voice-ws";

const POLL_INTERVAL_MS = 2_000;

const STATE_COLORS: Record<VoiceState, string> = {
  idle: "bg-[var(--text-muted)]",
  ready: "bg-[var(--accent)]",
  listening: "bg-[#5db4ff]",
  thinking: "bg-[#ff5dd8]",
  speaking: "bg-[#ffa040]",
  reconnecting: "bg-[#ff5d8a]",
  error: "bg-[var(--danger)]",
};

const STATE_LABELS: Record<VoiceState, string> = {
  idle: "IDLE",
  ready: "READY",
  listening: "LISTENING",
  thinking: "THINKING",
  speaking: "SPEAKING",
  reconnecting: "RECONNECTING",
  error: "ERROR",
};

interface VoiceSnapshot {
  state: VoiceState;
  lastAsr: string | null;
  serverEnabled: boolean;
  error: string | null;
}

export function VoiceWsIndicator() {
  const [snap, setSnap] = useState<VoiceSnapshot | null>(null);

  useEffect(() => {
    let cancelled = false;

    function poll() {
      try {
        const status = getVoiceStatus();
        if (cancelled) return;
        setSnap({
          state: status.state,
          lastAsr: status.lastAsr,
          serverEnabled: status.serverEnabled,
          error: status.error,
        });
      } catch {
        // Service not registered yet (Tauri boot race). Render
        // null snapshot — the render branch below shows the
        // unavailable state.
        if (!cancelled) setSnap(null);
      }
    }

    poll();
    const id = setInterval(poll, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  if (!snap) {
    return (
      <HudCard>
        <div data-testid="voice-ws-indicator" data-state="unavailable">
          <span className="text-[10px] font-[Orbitron] text-[var(--text-muted)] uppercase tracking-widest">
            Voice Link
          </span>
          <p className="text-xs text-[var(--text-muted)] mt-1">
            Voice service not initialised.
          </p>
        </div>
      </HudCard>
    );
  }

  return (
    <HudCard>
      <div
        data-testid="voice-ws-indicator"
        data-state={snap.state}
        data-server-enabled={snap.serverEnabled ? "true" : "false"}
      >
        <div className="flex items-center justify-between">
          <span className="text-[10px] font-[Orbitron] text-[var(--text-muted)] uppercase tracking-widest">
            Voice Link
          </span>
          <span
            className={`inline-block h-2 w-2 rounded-full ${STATE_COLORS[snap.state]}`}
            role="status"
            aria-label={`voice state: ${snap.state}`}
          />
        </div>
        <h3 className="text-lg font-[Rajdhani] text-[var(--text-primary)] mt-1">
          {STATE_LABELS[snap.state]}
        </h3>
        {snap.serverEnabled ? (
          snap.lastAsr ? (
            <p className="text-[10px] text-[var(--text-muted)] font-mono mt-1 truncate" title={snap.lastAsr}>
              Last: "{snap.lastAsr}"
            </p>
          ) : (
            <p className="text-[10px] text-[var(--text-muted)] font-mono mt-1">
              No transcript yet.
            </p>
          )
        ) : (
          <p className="text-[10px] text-[var(--warning)] font-mono mt-1">
            Voice layer disabled in config.toml.
          </p>
        )}
        {snap.error && snap.state === "error" && (
          <p
            className="text-[10px] text-[var(--danger)] font-mono mt-1 truncate"
            title={snap.error}
          >
            {snap.error}
          </p>
        )}
      </div>
    </HudCard>
  );
}

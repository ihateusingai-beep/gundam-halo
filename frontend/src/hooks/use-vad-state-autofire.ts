/**
 * useVadStateAutoFire — Sprint 19c always-on mic support.
 *
 * Subscribes to the backend's `vad.state` WS frames and
 * auto-fires `voice.begin` / `voice.end` so the user just
 * talks without holding the push-to-talk button.
 *
 * The backend's silero VAD emits `speech_start` when it
 * detects the start of an utterance and `speech_end` when
 * the user stops talking (after the configured
 * `min_silence_ms` threshold). The voice WS handler
 * (Sprint 19c Phase 1) forwards these as `vad.state`
 * frames; this hook translates them into the
 * voice.begin / voice.end lifecycle the pipeline
 * expects.
 *
 * Pause support: when `paused` is true, the hook ignores
 * `vad.state` events so the user can take a phone call
 * without the agent firing on TV audio. The VoicePanel
 * surfaces a ⏸ / ▶ toggle that flips the `paused` state.
 *
 * Usage: mount in CockpitLayout next to the existing
 * `useVoiceInput` call. Both hooks share the same mic
 * lifecycle (Sprint 18 hoisted useVoiceInput to the
 * cockpit). The `enabled` flag is the user's
 * `always_on_mic` config (read from `useVoiceConfig`).
 */
import { useEffect, useRef } from "react";

import { voiceBegin, voiceEnd } from "@/services/halo-voice-ws";
import { subscribeToVoiceEvent } from "@/services/halo-voice-ws";

export interface UseVadStateAutoFireOptions {
  /** Whether the auto-fire is active. The caller passes
   *  the user's `always_on_mic` config value. When false,
   *  the hook is a no-op and push-to-talk is the active
   *  mode. */
  enabled: boolean;
  /** When true, ignore `vad.state` events. The
   *  VoicePanel's ⏸ toggle sets this. */
  paused: boolean;
}

export function useVadStateAutoFire(
  opts: UseVadStateAutoFireOptions,
): void {
  const { enabled, paused } = opts;
  // Refs keep the latest flag values without re-creating
  // the subscription on every render (subscribeToVoiceEvent
  // would otherwise leak the old listener).
  const pausedRef = useRef(paused);
  pausedRef.current = paused;
  const enabledRef = useRef(enabled);
  enabledRef.current = enabled;

  useEffect(() => {
    if (!enabled) return;
    const unsub = subscribeToVoiceEvent("vad.state", (event) => {
      if (pausedRef.current) return;
      if (!enabledRef.current) return;
      // Narrow the event type. The server emits
      // vad.state with data.state = "speech_start" or
      // "speech_end" (see VoiceVadStateEvent).
      const data = (event as { data?: { state?: string } }).data;
      if (!data || !data.state) return;
      try {
        if (data.state === "speech_start") {
          voiceBegin();
        } else if (data.state === "speech_end") {
          voiceEnd();
        }
      } catch (e) {
        // The WS may be reconnecting. Drop the event —
        // the next turn boundary will be picked up
        // naturally.
        console.warn("[VadStateAutoFire] voiceBegin/End failed:", e);
      }
    });
    return () => {
      unsub();
    };
  }, [enabled]);
}

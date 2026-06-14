/**
 * WakePhraseHint — small inline hint under the mic button showing
 * the active wake phrase. Sprint 16 — Unicorn voice control.
 *
 * Two states:
 *  - Default: shows the first configured phrase ("Listening for
 *    **Unicorn** …"). When the user holds the mic, they know what
 *    to say.
 *  - Matched: when the backend reports a `wake_phrase` in the
 *    `agent.message` / `asr.result` frame, the hint briefly pulses
 *    to confirm the trigger was caught.
 *
 * The component is a pure presentational layer — the actual match
 * detection lives in `app/voice/wake_phrase.py` (backend). Here
 * we just render the most recent match from the voice WS state.
 */
import { useEffect, useState } from "react";

import { getVoiceStatus, type VoiceStatus } from "@/services/halo-voice-ws";

export interface WakePhraseHintProps {
  /**
   * The active wake phrase list. Typically fetched from the
   * backend's `/voice/config` endpoint on mount. If empty, the
   * hint renders nothing.
   */
  phrases: string[];
  /**
   * When true, the hint is hidden (e.g. when the mic is denied
   * or unsupported — the cockpit's existing error hint takes
   * over the visual real estate).
   */
  hidden?: boolean;
}

export function WakePhraseHint({ phrases, hidden = false }: WakePhraseHintProps) {
  const [status, setStatus] = useState<VoiceStatus>(() => getVoiceStatus());
  // We need a per-turn "last seen wake phrase" string so the hint
  // can pulse on a match. The VoiceStatus doesn't carry a
  // `lastWakePhrase` field yet (the server's wake_phrase flag is
  // ephemeral per frame). For now we rely on the most recent
  // agent.message.wake_phrase string surfaced via the
  // `lastReply` round-trip — but since we don't currently store
  // that, we approximate with a small JS-side buffer updated by
  // the VoicePanel (which receives the full event).
  // For the hint to be reactive without that wiring, we listen
  // to all events and pluck out the wake_phrase when it appears.
  const [lastMatch, setLastMatch] = useState<string>("");

  useEffect(() => {
    // We only need to re-render when status changes; the actual
    // wake_phrase flow is handled by a separate hook below.
    const id = setInterval(() => setStatus(getVoiceStatus()), 1000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    // Subscribe to the wildcard event stream and pluck wake_phrase
    // out of the relevant frames. This is a side-channel; the
    // main status update comes from the interval above.
    let cleanup = () => {};
    (async () => {
      const mod = await import("@/services/halo-voice-ws");
      const off = mod.subscribeToVoiceEvent("*", (e) => {
        if (e.type === "asr.result") {
          const d = (e as { data?: { wake_phrase?: string } }).data;
          const wp = d?.wake_phrase;
          if (wp) setLastMatch(wp);
        } else if (e.type === "agent.message") {
          const d = (e as { data?: { wake_phrase?: string } }).data;
          const wp = d?.wake_phrase;
          if (wp) setLastMatch(wp);
        }
      });
      cleanup = off;
    })();
    return () => cleanup();
  }, []);

  if (hidden) return null;
  if (!phrases || phrases.length === 0) return null;

  const first = phrases[0];
  const matched = lastMatch && phrases.includes(lastMatch) ? lastMatch : "";

  return (
    <div
      className={[
        "text-[9px] font-mono uppercase tracking-wider text-center",
        matched
          ? "text-[var(--accent)] animate-pulse"
          : "text-[var(--text-muted)]",
      ].join(" ")}
      title={
        phrases.length > 1
          ? `Wake phrases: ${phrases.join(", ")}`
          : `Wake phrase: ${first}`
      }
    >
      {matched
        ? `⚡ "${matched}" triggered`
        : `Listening for " ${first} "…`}
    </div>
  );
}

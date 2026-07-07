/**
 * DiagnosticsSection — Voice WebSocket lifecycle indicator.
 *
 * Extracted from VoiceTab.tsx (Sprint 56.7). This is the
 * smallest section (~25 LoC) and is read-only: it surfaces
 * the current `voiceStatus` (state machine from
 * `services/voice/`) so the user can confirm the WS
 * connection is alive BEFORE they touch the wake-phrase /
 * ASR-engine / corrector fields.
 *
 * The `accent={voiceStatus.state === "ready"}` highlighting
 * is intentional: it gives the user the same green-tinted
 * "ready" affordance the cockpit's VoiceWsIndicator card
 * uses, so the same colour means the same thing across both
 * surfaces.
 */
import { KV, Section } from "../../../shared";

import type { VoiceSectionsStore } from "../types";

export function DiagnosticsSection({
  store,
}: {
  store: VoiceSectionsStore;
}) {
  const { voiceStatus } = store;
  return (
    <Section title="Voice WebSocket">
      <KV
        label="State"
        value={voiceStatus.state}
        accent={voiceStatus.state === "ready"}
      />
      <KV
        label="Server enabled"
        value={voiceStatus.serverEnabled ? "yes" : "no"}
      />
      {voiceStatus.error && (
        <KV label="Last error" value={voiceStatus.error} danger />
      )}
    </Section>
  );
}

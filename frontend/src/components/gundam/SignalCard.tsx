/**
 * SignalCard — audio-reactive CyberWaveform card for the cockpit
 * right column. Sprint 18 Track A.
 *
 * Lives above the Avatar and shows a layered sine-wave oscilloscope
 * driven by the user's mic stream. When the mic is idle (state !==
 * "capturing"), the wave drifts deterministically via
 * useSharedAmplitude's "idle" branch. When the user holds the
 * push-to-talk button, the source flips to "mic" and the wave
 * pulses to the live RMS of their voice.
 *
 * Extracted from CockpitLayout so it can be unit-tested without
 * pulling in the full cockpit (WS store, projects store, gauges,
 * live2d bridge, etc.). The parent owns the mic hook; we receive
 * the same `mic` object VoicePanel consumes.
 */

import { CyberWaveform } from "@/components/gundam/CyberWaveform";
import type { UseVoiceInputResult } from "@/hooks/use-voice-input";

export interface SignalCardProps {
  /** The mic hook result from `useVoiceInput`. */
  mic: UseVoiceInputResult;
  /** Optional override for the canvas height. Default 80px. */
  height?: number;
  /** Optional override for the number of layered traces. Default 4. */
  layers?: number;
  /** Optional override for the amplitude scale. Default 1.2. */
  amplitudeScale?: number;
  /** Optional className for the inner canvas. */
  className?: string;
}

export function SignalCard({
  mic,
  height = 80,
  layers = 4,
  amplitudeScale = 1.2,
  className,
}: SignalCardProps) {
  // When the user holds the mic button, mic.state === "capturing"
  // and the source flips to "mic", which subscribes useSharedAmplitude
  // to useMicAnalyser(stream). On release, we fall back to the
  // deterministic idle drift so the wave still breathes.
  const isLive = mic.state === "capturing";
  return (
    <div
      data-testid="cockpit-signal-card"
      data-source={isLive ? "mic" : "idle"}
      className="flex-shrink-0"
    >
      <CyberWaveform
        source={isLive ? "mic" : "idle"}
        stream={mic.stream}
        height={height}
        layers={layers}
        amplitudeScale={amplitudeScale}
        className={className}
      />
    </div>
  );
}

export default SignalCard;

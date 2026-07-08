/**
 * CockpitEqCard — right-rail EQ card for the cockpit.
 *
 * Sprint 57 NEW. Wraps `<EqVisualizer>` with the TtsAudioGraph
 * lifecycle so the right rail can mount the visualizer without
 * caring about Web Audio plumbing. VoicePanel ALSO owns a
 * TtsAudioGraph (for the actual playback routing) — but the
 * graph here is a SEPARATE instance for visual purposes:
 *
 *   - VoicePanel's graph routes the <audio> element through the
 *     EQ chain (real-time audio processing).
 *   - CockpitEqCard's graph only owns the live BiquadFilterNode
 *     values for the visualizer to read. It doesn't connect to
 *     any audio source.
 *
 * Why two graphs? Because the visualizer is mounted in a
 * sibling panel from VoicePanel (both live in the right rail,
 * but as separate `<HudCard>`s). Sharing one graph would require
 * lifting state up to CockpitLayout + a context — overkill for
 * the small UX win. Two graphs cost: 1 AudioContext + 5
 * BiquadFilters extra (the browsers handle this trivially).
 *
 * The two graphs stay in sync via `useThemeStore` (both call
 * `setTheme` on the same store, both `getPreset` reads the same
 * preset table). The visualizer is read-only.
 */
import { useEffect, useState } from "react";

import { TtsAudioGraph } from "@/lib/audio-graph";
import { type EqPreset } from "@/lib/audio-eq";
import { useThemeStore } from "@/stores/theme";
import { EqVisualizer } from "./EqVisualizer";
import { HudCard } from "./HudCard";

export function CockpitEqCard({ live = false }: { live?: boolean }) {
  const theme = useThemeStore((s) => s.theme);
  // One graph per card instance. Disposed on unmount.
  const [graph] = useState<TtsAudioGraph>(() => new TtsAudioGraph());
  // Re-render when the theme changes (the visualizer reads the
  // preset, which depends on the theme).
  const [preset, setPreset] = useState<EqPreset>(() => graph.getPreset());

  useEffect(() => {
    graph.setTheme(theme);
    setPreset(graph.getPreset());
  }, [graph, theme]);

  useEffect(() => {
    return () => {
      void graph.dispose();
    };
  }, [graph]);

  return (
    <div data-testid="cockpit-eq-card">
      <HudCard>
        <EqVisualizer preset={preset} live={live} />
      </HudCard>
    </div>
  );
}

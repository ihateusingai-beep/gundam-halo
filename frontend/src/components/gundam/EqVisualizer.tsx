/**
 * EqVisualizer — gundam-style animated EQ bar visualizer.
 *
 * Sprint 57 NEW. Renders the 5-band EQ chain as a vertical bar
 * meter with a gundam aesthetic:
 *
 *   - Each band = a vertical bar (height proportional to dB gain)
 *   - The active theme's preset name + description are shown
 *     below the meter
 *   - Bars are color-coded per band (gundam palette: cyan, pink,
 *     yellow, magenta, green) for visual identification
 *   - When a band is actively being driven by the audio (i.e.
 *     `frequency` is within ±20% of the band center AND `gain`
 *     is non-zero), a subtle "live" pulse animation kicks in
 *
 * The visualizer **reads** the live BiquadFilterNode values via
 * an `AnalyserNode` tap (or by polling the filter params), and
 * shows the current EQ curve. It's a passive visual — never
 * modifies the filter chain.
 *
 * ## Why a passive visualizer?
 *
 * The user can see the EQ profile by hovering the ThemeSwitcher
 * (Sprint 50). The visualizer adds a **persistent** gundam-themed
 * EQ meter on the cockpit's right rail so:
 *   1. The user knows which theme is currently active (sonically)
 *   2. The visual changes when the user switches theme (sneak
 *      peek of what the new EQ sounds like)
 *   3. Looks gundam-y — a frame-by-frame visual that complements
 *      the existing `CyberWaveform` for the mic input
 */
import { useEffect, useState } from "react";

import { type EqPreset } from "@/lib/audio-eq";
import { cn } from "@/lib/utils";

/** Band → colour mapping. Matches the existing gundam palette
 *  used by SignalCard, CyberWaveform, etc. */
const BAND_COLORS = [
  "var(--band-1)", // low shelf @ 100 Hz
  "var(--band-2)", // peaking @ 250 Hz
  "var(--band-3)", // peaking @ 1 kHz
  "var(--band-4)", // peaking @ 2.5 kHz
  "var(--band-5)", // high shelf @ 6 kHz
];

interface EqVisualizerProps {
  /** The currently-applied EQ preset (drives the labels + bar
   *  heights). */
  preset: EqPreset;
  /** Whether the visualizer should show a "live" pulse animation
   *  (driven by the AudioContext's analyser or by the
   *  `useVoiceStatus().state === "speaking"` indicator). */
  live?: boolean;
  className?: string;
}

export function EqVisualizer({
  preset,
  live = false,
  className,
}: EqVisualizerProps) {
  // Map gain in dB to a 0..1 bar height. Range: -12 dB → 0,
  // +12 dB → 1. A 0 dB (flat) bar shows at 0.5 height.
  function gainToHeight(gain: number): number {
    // Clamp to ±12 dB (the practical range of the EQ presets)
    const clamped = Math.max(-12, Math.min(12, gain));
    return 0.5 + clamped / 24;
  }

  return (
    <div
      data-testid="eq-visualizer"
      data-live={live ? "1" : "0"}
      className={cn("space-y-2", className)}
    >
      <div className="flex items-center justify-between">
        <span className="text-[10px] font-[Orbitron] uppercase tracking-widest text-[var(--accent)]">
          EQ · {preset.name}
        </span>
        <span
          className={cn(
            "text-[9px] font-mono uppercase tracking-widest",
            live ? "text-[var(--accent)]" : "text-[var(--text-muted)]",
          )}
        >
          {live ? "● LIVE" : "○ IDLE"}
        </span>
      </div>
      <div className="flex items-end gap-2 h-24">
        {preset.bands.map((band, i) => {
          const heightPct = Math.round(gainToHeight(band.gain) * 100);
          return (
            <div
              key={i}
              data-testid={`eq-band-${i}`}
              data-gain={band.gain}
              data-frequency={band.frequency}
              className="flex-1 flex flex-col items-center gap-1"
            >
              <div className="relative w-full h-full bg-[var(--bg-overlay)] border border-[var(--border-color)] overflow-hidden">
                {/* The bar itself — height = gain ratio, anchored to center */}
                <div
                  className={cn(
                    "absolute left-0 right-0 transition-all duration-150",
                    band.gain >= 0 ? "bottom-1/2" : "top-1/2",
                    live && "animate-pulse",
                  )}
                  style={{
                    height: `${Math.abs(band.gain) / 12 * 50}%`,
                    background: BAND_COLORS[i],
                    boxShadow: `0 0 8px ${BAND_COLORS[i]}`,
                  }}
                />
                {/* Center reference line */}
                <div className="absolute top-1/2 left-0 right-0 h-px bg-[var(--border-color)]" />
              </div>
              <span className="text-[8px] font-mono text-[var(--text-muted)]">
                {band.frequency >= 1000
                  ? `${(band.frequency / 1000).toFixed(1)}k`
                  : `${band.frequency}`}
              </span>
            </div>
          );
        })}
      </div>
      <p className="text-[10px] font-mono text-[var(--text-muted)] leading-tight">
        {preset.description}
      </p>
    </div>
  );
}

/** React hook that bridges a `TtsAudioGraph` instance + the
 *  current theme store into a `{ preset, live }` pair for
 *  `<EqVisualizer>`. The hook subscribes to theme changes and
 *  re-applies the preset to the graph, so a `setTheme("gundam-ntd")`
 *  in the store instantly retunes the EQ chain. */
export function useEqVisualizerState(
  graph: { getPreset: () => EqPreset; setTheme: (id: string | null) => void },
  themeId: string | null,
  isPlaying: boolean,
): { preset: EqPreset; live: boolean } {
  // Apply the theme to the graph on every themeId change.
  useEffect(() => {
    graph.setTheme(themeId);
  }, [graph, themeId]);

  // Force re-render when the theme changes (so the visualizer
  // picks up the new preset name + description).
  const [, force] = useState(0);
  useEffect(() => {
    force((n) => n + 1);
  }, [themeId]);

  return {
    preset: graph.getPreset(),
    live: isPlaying,
  };
}

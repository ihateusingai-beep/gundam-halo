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
 * Sprint 62 A-A2: both graphs now derive the active preset
 * from `useEqStore.getActivePreset(theme)` instead of directly
 * from the theme. The user can override the EQ preset
 * independently of the theme. The override is session-only
 * (no localStorage); reset to revert.
 */
import { useEffect, useState } from "react";

import { TtsAudioGraph } from "@/lib/audio-graph";
import { getEqPreset, type EqPreset } from "@/lib/audio-eq";
import { useEqStore } from "@/stores/eq";
import { useThemeStore } from "@/stores/theme";
import { EqVisualizer } from "./EqVisualizer";
import { HudCard } from "./HudCard";

/** Duration of an A/B compare (ms). The user picks a theme,
 *  we apply its preset for 10s, then revert. */
const COMPARE_DURATION_MS = 10_000;

/** Sprint 63 A-A4: EQ editor band metadata. The 5 bands
 *  match the BiquadFilterNode layout in `audio-eq.ts`
 *  (low shelf at 100Hz, 3 peaking bands, high shelf at 6kHz). */
const BAND_LABELS = [
  { freq: "100 Hz", shape: "low shelf" },
  { freq: "250 Hz", shape: "peaking" },
  { freq: "1 kHz", shape: "peaking" },
  { freq: "2.5 kHz", shape: "peaking" },
  { freq: "6 kHz", shape: "high shelf" },
] as const;

export function CockpitEqCard({ live = false }: { live?: boolean }) {
  const theme = useThemeStore((s) => s.theme);
  const eqOverride = useEqStore((s) => s.override);
  const setEqPreset = useEqStore((s) => s.setPreset);
  const resetEq = useEqStore((s) => s.resetToThemePreset);
  // One graph per card instance. Disposed on unmount.
  const [graph] = useState<TtsAudioGraph>(() => new TtsAudioGraph());
  // Re-render when the theme OR the EQ override changes.
  const [preset, setPreset] = useState<EqPreset>(() => graph.getPreset());

  // Sprint 62 A-A3: A/B compare state. When non-null, we
  // temporarily apply the named theme's preset for
  // COMPARE_DURATION_MS, then revert.
  const [compareThemeId, setCompareThemeId] = useState<string | null>(null);
  const [compareSecondsLeft, setCompareSecondsLeft] = useState<number>(0);

  // Sprint 63 A-A4: EQ editor (UI skeleton, no audio change).
  // `editMode` toggles between the read-only visualizer and
  // the per-band slider grid. `localGains` is local-only
  // state — NOT wired to the audio graph in Sprint 63
  // (the wiring is Sprint 64's job).
  const [editMode, setEditMode] = useState(false);
  const [localGains, setLocalGains] = useState<
    [number, number, number, number, number]
  >(() => preset.bands.map((b) => b.gain) as [number, number, number, number, number]);

  useEffect(() => {
    // Sprint 62 A-A2: if the user has overridden the EQ preset,
    // use that; otherwise resolve from the theme. The graph
    // gets the resolved preset; the visualizer reads from
    // the graph (so both stay in sync).
    if (eqOverride) {
      graph.setPreset(eqOverride);
    } else {
      graph.setTheme(theme);
    }
    setPreset(graph.getPreset());
  }, [graph, theme, eqOverride]);

  useEffect(() => {
    return () => {
      void graph.dispose();
    };
  }, [graph]);

  // A/B compare timer. Decrement the visible countdown every
  // second. At T-0, clear the compare state. The cleanup
  // clears the interval AND the timeout (defense in depth:
  // unmount during a compare must not leave a setTimeout
  // pending that would call setCompareThemeId on a dead
  // component).
  useEffect(() => {
    if (!compareThemeId) return;
    const tickInterval = window.setInterval(() => {
      setCompareSecondsLeft((s) => Math.max(0, s - 1));
    }, 1000);
    const finishTimeout = window.setTimeout(() => {
      setCompareThemeId(null);
    }, COMPARE_DURATION_MS);
    return () => {
      window.clearInterval(tickInterval);
      window.clearTimeout(finishTimeout);
    };
  }, [compareThemeId]);

  // Apply the compare preset. The graph re-derives from the
  // override; the visualizer re-renders. NOTE: this is
  // LOCAL state — we DON'T write to `useEqStore.override`,
  // so when the timer fires the override stays null and
  // the graph reverts to the theme's preset.
  useEffect(() => {
    if (!compareThemeId) return;
    const tempPreset = getEqPreset(compareThemeId);
    graph.setPreset(tempPreset);
    setPreset(graph.getPreset());
  }, [graph, compareThemeId]);

  const startCompare = (themeId: string) => {
    if (themeId === theme) return; // same as current — no-op
    setCompareSecondsLeft(COMPARE_DURATION_MS / 1000);
    setCompareThemeId(themeId);
  };

  const pinCompare = () => {
    // Promote the current compare to a permanent override.
    if (!compareThemeId) return;
    setEqPreset(getEqPreset(compareThemeId));
    setCompareThemeId(null);
  };

  return (
    <div data-testid="cockpit-eq-card">
      <HudCard>
        <EqVisualizer preset={preset} live={live} />
        {/* Sprint 62 A-A3: A/B compare affordance. The
            user can preview another theme's EQ preset for
            10s, or pin it as a permanent override. */}
        <div
          className="mt-2 flex flex-wrap items-center gap-1"
          data-testid="eq-compare-row"
        >
          <span className="text-[9px] font-mono uppercase tracking-widest text-[var(--text-muted)] mr-1">
            {compareThemeId ? "A/B" : "Compare"}:
          </span>
          {compareThemeId ? (
            <>
              <span
                className="text-[9px] font-mono text-[var(--accent)]"
                data-testid="eq-compare-countdown"
              >
                {compareThemeId} · {compareSecondsLeft}s
              </span>
              <button
                type="button"
                onClick={pinCompare}
                data-testid="eq-compare-pin"
                className="text-[9px] font-mono px-1.5 py-0.5 border border-[var(--accent)] text-[var(--accent)] hover:bg-[var(--accent)] hover:text-[var(--bg-primary)] transition-colors"
              >
                Pin
              </button>
              <button
                type="button"
                onClick={() => setCompareThemeId(null)}
                data-testid="eq-compare-cancel"
                className="text-[9px] font-mono text-[var(--text-muted)] hover:text-[var(--danger)]"
              >
                ✕
              </button>
            </>
          ) : (
            <>
              {(
                [
                  "gundam-ntd",
                  "gundam-seed",
                  "gundam-crossbone",
                  "gundam-ntd-green",
                  "gundam-00",
                  "gundam-destiny",
                  "gundam-god",
                  "gundam-cartoon",
                ] as const
              )
                .filter((t) => t !== theme)
                .map((t) => (
                  <button
                    key={t}
                    type="button"
                    onClick={() => startCompare(t)}
                    data-testid={`eq-compare-${t}`}
                    className="text-[9px] font-mono px-1.5 py-0.5 border border-[var(--border-color)] text-[var(--text-muted)] hover:border-[var(--accent)] hover:text-[var(--accent)] transition-colors"
                  >
                    {t.replace("gundam-", "")}
                  </button>
                ))}
              {eqOverride && (
                <button
                  type="button"
                  onClick={resetEq}
                  data-testid="eq-compare-reset-override"
                  className="text-[9px] font-mono text-[var(--danger)] hover:underline ml-auto"
                >
                  Reset override
                </button>
              )}
            </>
          )}
          {/* Sprint 63 A-A4: Edit-mode toggle. Sits inside the
              compare row so the existing layout doesn't grow. */}
          <button
            type="button"
            onClick={() => setEditMode((v) => !v)}
            data-testid="eq-edit-toggle"
            className="text-[9px] font-mono px-1.5 py-0.5 border border-[var(--border-color)] text-[var(--text-muted)] hover:border-[var(--accent)] hover:text-[var(--accent)] transition-colors ml-auto"
          >
            {editMode ? "Done" : "Edit"}
          </button>
        </div>
        {/* Sprint 63 A-A4: per-band slider grid (UI skeleton).
            Local-only state; NOT wired to the audio graph.
            Sprint 64 will route the gains to
            TtsAudioGraph.setBandGain(band, gainDb). */}
        {editMode && (
          <div
            className="mt-2 grid grid-cols-5 gap-2"
            data-testid="eq-editor-grid"
          >
            {BAND_LABELS.map((band, i) => (
              <div key={i} className="flex flex-col items-center gap-1">
                <span className="text-[8px] font-mono text-[var(--text-muted)]">
                  {band.freq}
                </span>
                <input
                  type="range"
                  min={-12}
                  max={12}
                  step={0.5}
                  value={localGains[i]}
                  onChange={(e) => {
                    const next = [...localGains] as typeof localGains;
                    const newGain = Number(e.target.value);
                    next[i] = newGain;
                    setLocalGains(next);
                    // Sprint 64 A-A4 (audio): wire the slider
                    // to the BiquadFilterNode. The user hears
                    // the change immediately. The graph
                    // also updates its currentPreset so
                    // getPreset() reports the new value.
                    graph.setBandGain(i as 0 | 1 | 2 | 3 | 4, newGain);
                  }}
                  aria-label={`${band.freq} ${band.shape} gain in dB`}
                  data-testid={`eq-editor-band-${i}`}
                  className="w-full accent-[var(--accent)]"
                />
                <span
                  className="text-[8px] font-mono text-[var(--accent)]"
                  data-testid={`eq-editor-band-${i}-readout`}
                >
                  {localGains[i] >= 0 ? "+" : ""}
                  {localGains[i].toFixed(1)} dB
                </span>
              </div>
            ))}
          </div>
        )}
        {/* Sprint 64 A-A4 (audio): Apply + Reset buttons.
            Apply promotes the per-band edits to a
            permanent override (writes to useEqStore). Reset
            restores the preset's default gains and clears
            editMode. */}
        {editMode && (
          <div
            className="mt-2 flex items-center gap-1"
            data-testid="eq-editor-actions"
          >
            <button
              type="button"
              data-testid="eq-editor-apply"
              onClick={() => {
                // Build a new EqPreset from the local gains
                // and the current preset's band metadata
                // (frequency, Q, type).
                const newPreset: EqPreset = {
                  ...preset,
                  name: `${preset.name} (custom)`,
                  bands: preset.bands.map((b, i) => ({
                    ...b,
                    gain: localGains[i] ?? b.gain,
                  })) as EqPreset["bands"],
                };
                setEqPreset(newPreset);
                setEditMode(false);
              }}
              className="text-[9px] font-mono px-1.5 py-0.5 border border-[var(--accent)] text-[var(--accent)] hover:bg-[var(--accent)] hover:text-[var(--bg-primary)] transition-colors"
            >
              Apply
            </button>
            <button
              type="button"
              data-testid="eq-editor-reset"
              onClick={() => {
                // Restore the preset's default gains.
                setLocalGains(
                  preset.bands.map((b) => b.gain) as [
                    number,
                    number,
                    number,
                    number,
                    number,
                  ],
                );
                // Re-apply the preset to the graph.
                graph.setPreset(preset);
                setEditMode(false);
              }}
              className="text-[9px] font-mono text-[var(--text-muted)] hover:text-[var(--danger)]"
            >
              Reset
            </button>
          </div>
        )}
      </HudCard>
    </div>
  );
}

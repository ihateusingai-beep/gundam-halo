/**
 * Audio EQ presets — Gundam-themed 5-band BiquadFilterNode maps.
 *
 * Sprint 57 NEW. Per-theme equalizer profiles that match the
 * aesthetic of each Gundam universe:
 *
 *   - **NT-D (Unicorn psychoframe)**: sharp + crystalline. High-shelf
 *     boost + low-cut. Reflects the "psycho-frame" resonance.
 *   - **SEED (Freedom prismatic)**: bright + airy. Presence boost
 *     around 2 kHz, slight high-shelf. The "prismatic" light
 *     dispersion metaphor.
 *   - **CROSS (X-1 skull)**: dark + bassy. Low-shelf boost + high-cut.
 *     The "pirate" aesthetic.
 *   - **GREEN (Green Frame)**: balanced + organic. Near-flat with
 *     a 1 dB lift in the upper bass. The peaceful forest mood.
 *   - **00 (Qubit Trans-Am)**: metallic + mid-forward. Mid boost
 *     around 1 kHz. Quantum-computation feeling.
 *   - **DESTINY (Beam blade)**: sharp + cutting. Treble boost
 *     around 5 kHz. The Wing Zero's beam sword.
 *   - **GOD (Flame of God)**: deep + warm. Low-shelf boost + slight
 *     mid-cut. Solar-burner resonance.
 *   - **KAWAII (Cartoon chibi)**: cute + treble-only. High-pass at
 *     300 Hz + treble boost. Toon-shader quirkiness.
 *
 * Each preset is a list of 5 BiquadFilter configurations (one per
 * band). The bands are fixed:
 *   1. Low shelf  @ 100 Hz
 *   2. Peaking    @ 250 Hz
 *   3. Peaking    @ 1 kHz
 *   4. Peaking    @ 2.5 kHz
 *   5. High shelf @ 6 kHz
 *
 * The framework is `Web Audio API` BiquadFilterNode. Frequencies
 * are in Hz; gain is in dB; Q is dimensionless (filter width).
 *
 * ## Why 5 bands?
 *
 * 5 bands is the sweet spot for "perceived character" — 3 bands
 * is too coarse (all themes sound similar), 10 bands is too
 * fiddly (the user can't tell the difference). 5 is what most
 * hardware EQs ship with.
 *
 * ## Why per-theme and not per-user?
 *
 * The user picks a theme for visual reasons. The audio profile
 * is the natural extension: if you like the NT-D look, you'll
 * likely also like the NT-D sound. Per-user EQ can come later
 * (M11 follow-up) if requested.
 *
 * ## Toggling
 *
 * The `null` preset (returned by `getEqPreset("null")`) is the
 * "no EQ" fallback — used when the theme store has no theme set
 * (system default) or when Web Audio API is unavailable
 * (audioCtx === null in jsdom tests).
 */
export type EqBand = {
  type: BiquadFilterType;
  frequency: number;
  /** Gain in dB. For "lowpass" / "highpass" / "bandpass" types
   *  this is unused (the audio param is hidden). */
  gain: number;
  Q: number;
};

export interface EqPreset {
  /** Display name (e.g. "NT-D Sharp"). */
  name: string;
  /** 1-line description shown in the visualizer tooltip. */
  description: string;
  /** 5-band BiquadFilterNode configuration. */
  bands: [EqBand, EqBand, EqBand, EqBand, EqBand];
}

const BAND_SHAPE: [BiquadFilterType, number, number][] = [
  ["lowshelf", 100, 0.7], // band 1: 100 Hz low shelf, Q 0.7
  ["peaking", 250, 1.0], // band 2: 250 Hz peaking, Q 1.0
  ["peaking", 1000, 1.0], // band 3: 1 kHz peaking, Q 1.0
  ["peaking", 2500, 1.0], // band 4: 2.5 kHz peaking, Q 1.0
  ["highshelf", 6000, 0.7], // band 5: 6 kHz high shelf, Q 0.7
];

function preset(
  name: string,
  description: string,
  gains: [number, number, number, number, number],
): EqPreset {
  return {
    name,
    description,
    bands: BAND_SHAPE.map(([type, frequency, Q], i) => ({
      type,
      frequency,
      gain: gains[i],
      Q,
    })) as EqPreset["bands"],
  };
}

const PRESETS: Record<string, EqPreset> = {
  "gundam-ntd": preset(
    "NT-D Sharp",
    "Psycho-frame resonance: crystalline highs, low-cut bass.",
    [+1, 0, 0, +1, +4],
  ),
  "gundam-seed": preset(
    "SEED Prismatic",
    "Prismatic light: airy presence, slight high-shelf lift.",
    [-1, 0, +1, +3, +2],
  ),
  "gundam-crossbone": preset(
    "CROSS Dark",
    "Pirate skull: deep bass, rolled-off highs.",
    [+4, +2, 0, -1, -3],
  ),
  "gundam-ntd-green": preset(
    "GREEN Organic",
    "Forest frame: balanced, gentle upper-bass lift.",
    [+1, +1, 0, 0, 0],
  ),
  "gundam-00": preset(
    "00 Quantum",
    "Qubit Trans-Am: metallic mid-forward, thin bass.",
    [-2, -1, +4, +2, +1],
  ),
  "gundam-destiny": preset(
    "DESTINY Blade",
    "Wing-Zero beam sword: cutting treble, tight bass.",
    [-1, 0, 0, +2, +5],
  ),
  "gundam-god": preset(
    "GOD Solar",
    "Flame of God: deep burn, mid cut for warmth.",
    [+3, +2, -1, -1, 0],
  ),
  "gundam-cartoon": preset(
    "KAWAII Chibi",
    "Toon-shader cuteness: high-pass + treble emphasis.",
    [-4, -2, 0, +2, +4],
  ),
  // Neutral fallback — "no theme" or "system default".
  null: preset("Flat", "No equalization. Direct PCM path.", [0, 0, 0, 0, 0]),
};

/** Look up the EQ preset for a theme id. Returns the flat
 *  fallback if the theme id is unknown or the key is "null"
 *  (system default). */
export function getEqPreset(themeId: string | null): EqPreset {
  if (themeId && themeId in PRESETS) {
    return PRESETS[themeId];
  }
  return PRESETS.null;
}

/** Apply an EQ preset to a list of 5 BiquadFilterNode instances.
 *  Mutates each filter's `frequency` / `gain` / `Q` / `type`
 *  audio params in place. Per-band `setValueAtTime` (no ramp) so
 *  the EQ snaps instantly when the user switches theme — matches
 *  the visual theme switch which is also instant.
 *
 *  Pass exactly 5 BiquadFilterNodes. Throws on count mismatch so
 *  a misconfigured chain fails loud at preset-apply time, not
 *  silent-no-effect at playChunk time. */
export function applyEqPreset(
  filters: BiquadFilterNode[],
  preset: EqPreset,
): void {
  if (filters.length !== 5) {
    throw new Error(
      `applyEqPreset requires exactly 5 BiquadFilters, got ${filters.length}`,
    );
  }
  const ctx = filters[0].context;
  const now = ctx.currentTime;
  for (let i = 0; i < 5; i++) {
    const filter = filters[i];
    const band = preset.bands[i];
    // setValueAtTime (no ramp) for instant snap.
    filter.type = band.type;
    filter.frequency.setValueAtTime(band.frequency, now);
    filter.gain.setValueAtTime(band.gain, now);
    filter.Q.setValueAtTime(band.Q, now);
  }
}

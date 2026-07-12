/**
 * eq.schema.ts — Sprint 67 C-A1.
 *
 * Zod schema for the persisted EQ override. The schema
 * mirrors the `EqPreset` + `EqBand` interfaces in
 * `@/lib/audio-eq` and is used to validate the value
 * read from localStorage on mount. The schema-version
 * suffix in the localStorage key (`*.v1`) follows the
 * Sprint 49 pattern: when the shape changes, bump to
 * `v2` and add a migration; the `v1` reader stays
 * additive.
 *
 * ## Why Zod (not just `JSON.parse`)
 *
 * The localStorage value is untrusted by definition —
 * a stale value from a previous version of the app
 * (e.g. from Sprint 62's session-only store that
 * somehow got persisted) would crash the EQ pipeline
 * if we assume the shape. Zod's parse-and-default
 * pattern gives us:
 *   1. Shape validation (5 bands, valid types, etc.)
 *   2. Sensible defaults for missing optional fields
 *   3. A clear error path when the schema is wrong
 *
 * On parse failure, the store falls back to the
 * "no override" state and logs a warning. The user
 * keeps working with the theme's default preset.
 */
import { z } from "zod";

/** A single BiquadFilterNode band. */
const eqBandSchema = z.object({
  type: z.enum([
    "lowshelf",
    "highshelf",
    "peaking",
    "lowpass",
    "highpass",
    "bandpass",
    "notch",
    "allpass",
  ]),
  frequency: z.number().min(20).max(20000),
  gain: z.number().min(-24).max(24),
  Q: z.number().min(0.1).max(10),
});

/** The 5-band EqPreset. */
export const eqPresetSchema = z.object({
  name: z.string().min(1),
  description: z.string(),
  // Tuple: exactly 5 bands. Sprint 67 EQ is 5-band; if a future
  // sprint adds a 6th band, bump the schema to `v2` + an array.
  bands: z.tuple([
    eqBandSchema,
    eqBandSchema,
    eqBandSchema,
    eqBandSchema,
    eqBandSchema,
  ]),
});

/** The persisted shape (just the preset; the store wraps it). */
export const persistedEqOverrideSchema = eqPresetSchema;

/** The localStorage key. Schema-versioned per Sprint 49. */
export const EQ_OVERRIDE_LS_KEY = "halo.eq.override.v1";

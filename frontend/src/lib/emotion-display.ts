/**
 * Emotion display tokens for the activity ticker + future HUD overlays.
 *
 * Mirrors the 8-emotion DSL the avatar speaks (see
 * `backend/app/voice/halo_responder.py::EMOTION_MAP`). Used wherever
 * we need to surface an emotion to the user as a colored chip / icon
 * / label — currently the ActivityTicker, but the same table could
 * drive a tool-trace tooltip, a per-event border color, etc.
 *
 * Kept dependency-free so it can be imported from server-rendered
 * code, tests, or non-React utilities without pulling in the
 * WebSocket bridge.
 */

export interface EmotionDisplay {
  /** Single-glyph icon (Unicode shape, not emoji — monospace safe). */
  icon: string;
  /** CSS var() reference, e.g. "var(--accent)". */
  color: string;
  /** Short lowercase label, e.g. "calm". */
  label: string;
}

export const EMOTION_DISPLAY: Record<string, EmotionDisplay> = {
  calm:      { icon: "○",  color: "var(--text-muted)",       label: "calm" },
  focused:   { icon: "◉",  color: "var(--accent)",           label: "focused" },
  awakening: { icon: "⚡", color: "var(--accent-secondary)", label: "awakening" },
  alert:     { icon: "△",  color: "var(--warning)",          label: "alert" },
  damage:    { icon: "✕",  color: "var(--danger)",           label: "damage" },
  resolve:   { icon: "◣",  color: "var(--success)",          label: "resolve" },
  jubilant:  { icon: "✦",  color: "var(--success)",          label: "jubilant" },
  stealth:   { icon: "·",  color: "var(--text-secondary)",   label: "stealth" },
};

/** Phase glyph for a `live2d_tool_trigger` chip. */
export const PHASE_ICON: Record<string, string> = {
  start: "→",
  end: "✓",
};

/** Resolve an emotion key to a display token, falling back to "calm". */
export function getEmotionDisplay(emotion: string | undefined | null): EmotionDisplay {
  if (!emotion) return EMOTION_DISPLAY.calm;
  return EMOTION_DISPLAY[emotion] ?? EMOTION_DISPLAY.calm;
}

/** Resolve a phase key to a glyph, falling back to "·". */
export function getPhaseIcon(phase: string | undefined | null): string {
  if (!phase) return "·";
  return PHASE_ICON[phase] ?? "·";
}

import { useEffect, useRef } from "react";
import { subscribeToVoice } from "@/services/halo-live2d-bridge";
import { useSharedAmplitude } from "@/hooks/use-shared-amplitude";

/**
 * CSSAvatar → UnicornAvatar
 *
 * Replaces the previous pure-CSS/SVG NT-D placeholder with the
 * 88-frame Unicorn Gundam sprite sheet. Subscribes to the same
 * `live2d.trigger` WS events as before, so emotion transitions
 * still work (the sprite animation speed + visual style change
 * per emotion).
 *
 * The sprite is driven by the shared amplitude source so the
 * avatar's scale + halo glow pulse together with the surrounding
 * CyberWaveform animation.
 *
 * Emotion → visual mod mapping:
 *   calm       → slow (1.0x), green halo, scale 1.0→1.12
 *   focused    → medium (1.5x), green halo, scale 1.0→1.14
 *   awakening  → fast (2.0x), GREEN tint (psychoframe active), scale 1.0→1.20
 *   alert      → fastest (2.5x), RED halo, scale 1.0→1.25
 *   damage     → chaotic (3.0x), RED + jitter, scale 1.0→1.30
 *   resolve    → slow fade (0.7x), cyan halo, scale 1.0→1.10
 *   jubilant   → bouncy (1.8x), magenta halo, scale 1.0→1.18
 *   stealth    → dim (0.6x), cyan, scale 1.0→1.05
 */

interface AvatarProps {
  emotion?: string;
  /** Show scan line overlay (for active/speaking state) */
  active?: boolean;
}

const FRAME_COUNT = 88;
// Map emotion → animation speed multiplier. Base loop is 11s
// (88 frames @ 8fps); emotion multiplier scales that. 8fps gives
// a slow, deliberate "breathing" cadence; the per-frame hold is
// 125ms which reads as a single beat rather than a flicker.
const BASE_FPS = 8;
const EMOTION_SPEED: Record<string, number> = {
  calm: 0.5,
  focused: 0.7,
  awakening: 1.0,
  alert: 1.2,
  damage: 1.4,
  resolve: 0.3,
  jubilant: 0.8,
  stealth: 0.25,
};
const EMOTION_CLASS: Record<string, string> = {
  calm: "avatar--calm",
  focused: "avatar--focused",
  awakening: "avatar--psychoframe",
  alert: "avatar--alert",
  damage: "avatar--damage",
  resolve: "avatar--resolve",
  jubilant: "avatar--jubilant",
  stealth: "avatar--stealth",
};

// Per-emotion visual mod. Each entry drives the drop-shadow hue,
// scale boost factor, and whether the avatar should jitter (damage).
// hue is in CSS hsl(h, s%, l%) space; r=0 g=b=140 cy=185 mg=300.
type EmotionVisual = {
  hue: number;
  sat: number;
  light: number;
  scaleBoost: number;   // additional scale on top of amp-driven base
  jitter: boolean;      // chaotic micro-shake (damage)
  glowMin: number;      // min drop-shadow blur (px) at amp=0
  glowMax: number;      // max drop-shadow blur (px) at amp=1
};
const EMOTION_VISUAL: Record<string, EmotionVisual> = {
  calm:      { hue: 165, sat: 100, light: 50, scaleBoost: 0.0,  jitter: false, glowMin: 8,  glowMax: 28 },
  focused:   { hue: 175, sat: 100, light: 55, scaleBoost: 0.02, jitter: false, glowMin: 10, glowMax: 32 },
  awakening: { hue: 145, sat: 100, light: 50, scaleBoost: 0.05, jitter: false, glowMin: 12, glowMax: 42 },
  alert:     { hue:   0, sat: 100, light: 55, scaleBoost: 0.08, jitter: false, glowMin: 14, glowMax: 50 },
  damage:    { hue:   0, sat: 100, light: 50, scaleBoost: 0.10, jitter: true,  glowMin: 16, glowMax: 60 },
  resolve:   { hue: 195, sat: 100, light: 60, scaleBoost: 0.0,  jitter: false, glowMin: 6,  glowMax: 24 },
  jubilant:  { hue: 305, sat: 100, light: 60, scaleBoost: 0.04, jitter: false, glowMin: 12, glowMax: 44 },
  stealth:   { hue: 200, sat:  60, light: 45, scaleBoost: 0.0,  jitter: false, glowMin: 4,  glowMax: 14 },
};

export function CSSAvatar({ emotion, active }: AvatarProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const spriteRef = useRef<HTMLDivElement>(null);
  const amp = useSharedAmplitude();

  // Subscribe to live2d.trigger WS events for emotion class swap
  useEffect(() => {
    const unsubscribe = subscribeToVoice("live2d.trigger", (event) => {
      if (!containerRef.current) return;
      const emo = (event as any).data?.emotion as string;
      const allClasses = Object.values(EMOTION_CLASS);
      containerRef.current.classList.remove(...allClasses);
      const cls = EMOTION_CLASS[emo] || EMOTION_CLASS.calm;
      containerRef.current.classList.add(cls);
    });
    return unsubscribe;
  }, []);

  useEffect(() => {
    if (!containerRef.current || !emotion) return;
    const allClasses = Object.values(EMOTION_CLASS);
    containerRef.current.classList.remove(...allClasses);
    const cls = EMOTION_CLASS[emotion] || EMOTION_CLASS.calm;
    containerRef.current.classList.add(cls);
  }, [emotion]);

  // Compute animation duration from emotion. Base loop is 88 frames
  // at 8fps = 11s; emotion speed multiplier scales that.
  const speed = EMOTION_SPEED[emotion || "calm"] || 1.0;
  const animDuration = `${(88 / BASE_FPS) / speed}s`;

  // Per-emotion visual mod (hue, scale boost, glow range). Falls
  // back to calm if emotion is unset or unknown.
  const emo = (EMOTION_VISUAL[emotion || "calm"] || EMOTION_VISUAL.calm);

  // Amplitude-driven scale + glow, per-emotion modulated.
  const scale =
    1.0 + amp * (0.18 + emo.scaleBoost);
  const glowBlur = emo.glowMin + amp * (emo.glowMax - emo.glowMin);
  const glowAlpha = 0.4 + amp * 0.5;
  const glowColor = `hsla(${emo.hue}, ${emo.sat}%, ${emo.light}%, ${glowAlpha.toFixed(2)})`;
  const dropShadow =
    `drop-shadow(0 0 ${glowBlur.toFixed(0)}px ${glowColor})` +
    // damage adds a second red core shadow for that "warning" feel
    (emo.jitter
      ? ` drop-shadow(0 0 ${(glowBlur * 0.4).toFixed(0)}px hsla(0, 100%, 35%, ${(glowAlpha * 0.8).toFixed(2)}))`
      : "");

  // Damage jitter: ~6Hz micro-shake on translate, magnitude scales
  // with amp. Slower than the original 12Hz so it reads as a beat
  // rather than a buzz.
  useEffect(() => {
    if (!emo.jitter) return;
    let timer: number | null = null;
    let mounted = true;
    const tick = () => {
      if (!mounted || !spriteRef.current) {
        timer = window.setTimeout(tick, 80) as unknown as number;
        return;
      }
      const jx = (Math.random() - 0.5) * 6 * amp;
      const jy = (Math.random() - 0.5) * 6 * amp;
      spriteRef.current.style.transform = `scale(${scale.toFixed(3)}) translate(${jx.toFixed(2)}px, ${jy.toFixed(2)}px)`;
      timer = window.setTimeout(tick, 80) as unknown as number;
    };
    timer = window.setTimeout(tick, 80) as unknown as number;
    return () => {
      mounted = false;
      if (timer !== null) clearTimeout(timer);
    };
  }, [emo.jitter, amp, scale]);

  return (
    <div
      ref={containerRef}
      className={`avatar avatar--calm${active ? " avatar--active" : ""}`}
      aria-label={`Unicorn Avatar — ${emotion ?? "calm"}`}
    >
      {/* Hex frame */}
      <div className="avatar__frame">
        <span className="avatar__bracket avatar__bracket--tl" />
        <span className="avatar__bracket avatar__bracket--tr" />
        <span className="avatar__bracket avatar__bracket--bl" />
        <span className="avatar__bracket avatar__bracket--br" />

        {active && <div className="avatar__scan" />}

        {/* Sprite face (replaces avatar__head + visor + mouth) */}
        <div className="avatar__face">
          <div
            ref={spriteRef}
            className="unicorn-sprite-anim"
            style={{
              transform: emo.jitter
                ? undefined  // jitter effect owns transform during damage
                : `scale(${scale.toFixed(3)})`,
              filter: `${dropShadow} hue-rotate(0deg)`,
              transition: emo.jitter
                ? "filter 60ms linear"
                : "transform 60ms linear, filter 60ms linear",
            }}
          />
        </div>

        <div className="avatar__glow" />
        <div className="avatar__status">RX-0</div>
      </div>

      {/* Local CSS for the sprite animation. step(N, end) gives
          crisp frame-by-frame playback at 8fps (each frame holds
          125ms) — slow enough to read as breath, not flicker. */}
      <style>{`
        .unicorn-sprite-anim {
          width: 100%;
          height: 100%;
          background-image: url("/gundam-assets/avatars/unicorn-spritesheet.png");
          background-size: ${FRAME_COUNT * 100}% 100%;
          background-position: 0 0;
          background-repeat: no-repeat;
          animation: unicornSpriteLoop ${animDuration} steps(${FRAME_COUNT}, end) infinite;
          will-change: transform, filter;
        }
        @keyframes unicornSpriteLoop {
          0%   { background-position: 0% 0; }
          100% { background-position: -${((FRAME_COUNT - 1) / FRAME_COUNT) * 100}% 0; }
        }
      `}</style>
    </div>
  );
}

export default CSSAvatar;

import { useSharedAmplitude } from "@/hooks/use-shared-amplitude";
import { useMemo } from "react";

/**
 * GundamAvatar — animated Unicorn Gundam sprite whose scale + glow
 * track the shared amplitude pulse. Reads from the same amplitude
 * source as CyberWaveform so the robot and the oscilloscope
 * behind it pulse together.
 *
 * Uses a horizontal sprite sheet at /gundam-assets/avatars/unicorn-spritesheet.png
 * (88 frames @ 256x256, 30fps loop). The container scales 1.0 → 1.18
 * and the drop-shadow glow intensifies as amplitude rises.
 */
export interface GundamAvatarProps {
  /** Display size in CSS px. Default 256. */
  size?: number;
  /** How strongly amplitude drives the scale. 0..1. Default 1. */
  amplitudeScale?: number;
  /** 0 = static, 1 = full sprite animation. Default 1. */
  animationSpeed?: number;
  className?: string;
  /** Caption / label drawn under the avatar (optional). */
  caption?: string;
}

export function GundamAvatar({
  size = 256,
  amplitudeScale = 1.0,
  animationSpeed = 1.0,
  className = "",
  caption,
}: GundamAvatarProps) {
  const amp = useSharedAmplitude();

  // Background-position step per frame: 88 frames stretched across
  // the sheet width. Background position is in percent of the sheet
  // width; one step = 100/88 ≈ 1.1364%.
  const frameCount = 88;
  const stepPct = 100 / frameCount;

  // CSS keyframes string: 88 stops, one per frame, last one snaps
  // back to start so the loop is seamless.
  const keyframes = useMemo(() => {
    let css = "";
    for (let i = 0; i <= frameCount; i++) {
      const pct = (i / frameCount) * 100;
      const offset = -((i % frameCount) * stepPct);
      css += `${pct.toFixed(3)}% { background-position: ${offset.toFixed(3)}% 0; }\n`;
    }
    return css;
  }, [frameCount, stepPct]);

  // Map amplitude 0..1 → scale 1.0..1.18
  const scale = 1.0 + amp * amplitudeScale * 0.18;
  // Glow intensity
  const glowBlur = 12 + amp * 28;
  const glowAlpha = 0.4 + amp * 0.5;

  return (
    <div
      className={`relative inline-block ${className}`}
      style={{ width: size, height: size }}
    >
      <style>{`
        @keyframes gundamSpriteLoop {
          ${keyframes}
        }
        .gundam-sprite-anim {
          width: 100%;
          height: 100%;
          background-image: url("/gundam-assets/avatars/unicorn-spritesheet.png");
          background-size: ${frameCount * 100}% 100%;
          background-position: 0 0;
          background-repeat: no-repeat;
          animation: gundamSpriteLoop ${(88 / 30) / animationSpeed}s steps(${frameCount}, end) infinite;
          filter: drop-shadow(0 0 ${glowBlur}px rgba(0, 229, 180, ${glowAlpha}));
          transition: filter 60ms linear;
        }
      `}</style>
      <div
        className="gundam-sprite-anim"
        style={{
          transform: `scale(${scale.toFixed(3)})`,
          transformOrigin: "center center",
          transition: "transform 60ms linear",
        }}
      />
      {caption && (
        <div
          className="absolute left-0 right-0 text-center font-mono text-xs tracking-widest"
          style={{
            bottom: -22,
            color: "rgba(0, 229, 255, 0.7)",
            textShadow: "0 0 6px rgba(0, 229, 255, 0.5)",
          }}
        >
          {caption}
        </div>
      )}
    </div>
  );
}

export default GundamAvatar;

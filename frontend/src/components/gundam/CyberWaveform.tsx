import { useSharedAmplitude } from "@/hooks/use-shared-amplitude";
import { useEffect, useRef } from "react";

/**
 * CyberWaveform — layered sine-wave oscilloscope driven by a shared
 * amplitude. Multiple CyberWaveform + GundamAvatar instances on the
 * same page all subscribe to the same amplitude source so they pulse
 * together ("talking gundam robot" feel).
 */
export interface CyberWaveformProps {
  layers?: number;
  height?: number;
  speed?: number;
  gridSize?: number;
  resolution?: number;
  className?: string;
  /** How much the amplitude drives the trace's vertical scale. 0..1. Default 1. */
  amplitudeScale?: number;
}

export function CyberWaveform({
  layers = 6,
  height = 160,
  speed = 0.08,
  gridSize = 5,
  resolution = 200,
  className = "",
  amplitudeScale = 1.0,
}: CyberWaveformProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const rafRef = useRef<number | null>(null);
  const amp = useSharedAmplitude();

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const cssWidth = canvas.clientWidth;
    canvas.width = cssWidth * dpr;
    canvas.height = height * dpr;
    ctx.scale(dpr, dpr);

    const traceState = Array.from({ length: layers }, (_, i) => ({
      targetAmp: 0.3 + Math.random() * 0.5,
      targetFreq: 1.5 + Math.random() * 4,
      amp: 0.3 + Math.random() * 0.5,
      freq: 1.5 + Math.random() * 4,
      phaseOffset: (i / layers) * Math.PI * 2,
      hue: 185 + i * 8,
    }));

    let t = 0;
    let lastAmp = 0.45;
    let lastFrameMs = Date.now();

    const draw = () => {
      // Use wall-clock time so the visual drift is consistent across
      // refresh rates. Browser rAF can fire anywhere from 30Hz to
      // 144Hz; a fixed tick would either stutter on high-refresh
      // displays or skip ahead on low-refresh ones.
      const now = Date.now();
      const realDt = (now - lastFrameMs) / 1000;
      lastFrameMs = now;

      ctx.fillStyle = "rgba(5, 11, 26, 0.18)";
      ctx.fillRect(0, 0, cssWidth, height);

      ctx.strokeStyle = "rgba(120, 200, 255, 0.05)";
      ctx.lineWidth = 1;
      ctx.beginPath();
      for (let x = 0; x <= cssWidth; x += gridSize) {
        ctx.moveTo(x + 0.5, 0);
        ctx.lineTo(x + 0.5, height);
      }
      for (let y = 0; y <= height; y += gridSize) {
        ctx.moveTo(0, y + 0.5);
        ctx.lineTo(cssWidth, y + 0.5);
      }
      ctx.stroke();

      ctx.strokeStyle = "rgba(180, 230, 255, 0.12)";
      ctx.beginPath();
      ctx.moveTo(0, height / 2);
      ctx.lineTo(cssWidth, height / 2);
      ctx.stroke();

      const cy = height / 2;
      const maxAmp = height * 0.42;
      // Smooth amplitude envelope so the visual pulse doesn't jitter.
      // Lerp factor scales with frame time so the smoothing speed
      // is constant in seconds, not in frames.
      const smoothing = 1 - Math.exp(-realDt * 6); // 6 = smoothing rate
      const smoothedAmp = lastAmp + (amp - lastAmp) * smoothing;
      lastAmp = smoothedAmp;
      // Modulate: at amp=0 → quiet (0.15 baseline), at amp=1 → full swing
      const envScale = 0.15 + smoothedAmp * amplitudeScale * 0.85;

      for (let layerIdx = 0; layerIdx < layers; layerIdx++) {
        const layer = traceState[layerIdx];
        if (Math.random() < 0.025) layer.targetAmp = 0.2 + Math.random() * 0.7;
        if (Math.random() < 0.012) layer.targetFreq = 1.0 + Math.random() * 5.0;
        layer.amp += (layer.targetAmp - layer.amp) * speed;
        layer.freq += (layer.targetFreq - layer.freq) * speed * 0.5;

        ctx.beginPath();
        const phase = t * layer.freq * 0.5 + layer.phaseOffset;
        for (let i = 0; i <= resolution; i++) {
          const x = (i / resolution) * cssWidth;
          const theta = (i / resolution) * Math.PI * 2 * layer.freq + phase;
          const y =
            cy +
            (Math.sin(theta) * maxAmp * layer.amp +
              Math.sin(theta * 2.3 + phase * 0.7) * maxAmp * layer.amp * 0.25) *
              envScale;
          if (i === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }

        const hue = layer.hue;
        ctx.strokeStyle = `hsla(${hue}, 100%, 70%, ${0.45 + smoothedAmp * 0.3})`;
        ctx.lineWidth = 1.2 + smoothedAmp * 0.6;
        ctx.lineJoin = "round";
        ctx.lineCap = "round";
        ctx.save();
        ctx.shadowColor = `hsla(${hue}, 100%, 60%, ${0.5 + smoothedAmp * 0.4})`;
        ctx.shadowBlur = 6 + smoothedAmp * 10;
        ctx.stroke();
        ctx.restore();
      }

      t += realDt;
      rafRef.current = requestAnimationFrame(draw);
    };

    rafRef.current = requestAnimationFrame(draw);
    return () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    };
  }, [layers, height, speed, gridSize, resolution, amplitudeScale, amp]);

  return (
    <canvas
      ref={canvasRef}
      style={{ width: "100%", height: `${height}px`, display: "block" }}
      className={className}
      aria-hidden
    />
  );
}

export default CyberWaveform;

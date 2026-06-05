import { cn } from "@/lib/utils";

interface RingProgressProps {
  label: string;
  /** 0-100 */
  value: number;
  size?: number;
  className?: string;
}

const STROKE = 6;
const RADIUS = 42;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

/** `.gundam-ring-progress` — circular SVG progress (boost / ammo / completion). */
export function RingProgress({
  label,
  value,
  size = 100,
  className,
}: RingProgressProps) {
  const clamped = Math.max(0, Math.min(100, value));
  const offset = CIRCUMFERENCE * (1 - clamped / 100);

  return (
    <div
      className={cn("gundam-ring-progress", className)}
      style={{ width: size, height: size, position: "relative" }}
      role="img"
      aria-label={`${label} ${clamped.toFixed(0)}%`}
    >
      <svg viewBox="0 0 100 100" width={size} height={size}>
        <circle
          cx="50"
          cy="50"
          r={RADIUS}
          fill="none"
          stroke="var(--bg-input)"
          strokeWidth={STROKE}
        />
        <circle
          cx="50"
          cy="50"
          r={RADIUS}
          fill="none"
          stroke="var(--accent)"
          strokeWidth={STROKE}
          strokeLinecap="round"
          strokeDasharray={CIRCUMFERENCE}
          strokeDashoffset={offset}
          transform="rotate(-90 50 50)"
          style={{
            filter: "drop-shadow(0 0 4px var(--accent))",
            transition: "stroke-dashoffset 0.5s ease-out",
          }}
        />
      </svg>
      <span
        style={{
          position: "absolute",
          top: "50%",
          left: "50%",
          transform: "translate(-50%, -50%)",
          fontSize: 10,
          color: "var(--text-muted)",
          fontFamily: "'Rajdhani', sans-serif",
          letterSpacing: 1,
          textTransform: "uppercase",
        }}
      >
        {label}
      </span>
      <span
        style={{
          position: "absolute",
          top: "50%",
          left: "50%",
          transform: "translate(-50%, calc(-50% + 14px))",
          fontSize: 14,
          color: "var(--accent)",
          fontFamily: "'Orbitron', sans-serif",
          fontWeight: 700,
        }}
      >
        {clamped.toFixed(0)}%
      </span>
    </div>
  );
}

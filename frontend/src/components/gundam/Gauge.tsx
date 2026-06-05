import { cn } from "@/lib/utils";

interface GaugeProps {
  label: string;
  /** 0-100 */
  value: number;
  className?: string;
}

/** `.gundam-gauge-v` — vertical gauge bar (CPU / RAM / disk). */
export function Gauge({ label, value, className }: GaugeProps) {
  const clamped = Math.max(0, Math.min(100, value));
  return (
    <div className={cn("gundam-gauge-v", className)}>
      <span className="gundam-gauge-label">{label}</span>
      <div className="gundam-gauge-track">
        <div
          className="gundam-gauge-fill"
          style={{ height: `${clamped}%` }}
          aria-label={`${label} ${clamped.toFixed(0)}%`}
        />
      </div>
      <span className="gundam-gauge-value">{clamped.toFixed(0)}</span>
    </div>
  );
}

import { cn } from "@/lib/utils";

interface EnergyBarProps {
  /** 0-100 */
  value: number;
  className?: string;
  label?: string;
}

/** `.gundam-energy-bar` — horizontal energy bar. */
export function EnergyBar({ value, className, label }: EnergyBarProps) {
  const clamped = Math.max(0, Math.min(100, value));
  return (
    <div className={cn("w-full", className)}>
      {label && (
        <div className="text-xs text-[var(--text-muted)] uppercase tracking-wider mb-1 font-[Rajdhani]">
          {label}
        </div>
      )}
      <div className="gundam-energy-bar">
        <div
          className="gundam-energy-bar-fill"
          style={{ width: `${clamped}%` }}
          aria-label={`${label || "Energy"} ${clamped.toFixed(0)}%`}
        />
      </div>
    </div>
  );
}

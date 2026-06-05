import { cn } from "@/lib/utils";

interface RadarProps {
  size?: number;
  className?: string;
}

/** `.gundam-radar` — CSS-only radar sweep. */
export function Radar({ size = 60, className }: RadarProps) {
  return (
    <div
      className={cn("gundam-radar", className)}
      style={{ width: size, height: size }}
      role="img"
      aria-label="Radar sweep"
    />
  );
}

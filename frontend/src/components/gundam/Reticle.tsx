import { type ReactNode } from "react";
import { cn } from "@/lib/utils";

interface ReticleProps {
  children: ReactNode;
  className?: string;
}

/** `.gundam-target` — concentric target lock (used in the center focus area). */
export function Reticle({ children, className }: ReticleProps) {
  return (
    <div className={cn("gundam-target p-8", className)}>
      <div className="text-center">{children}</div>
    </div>
  );
}

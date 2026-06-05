import { type ReactNode } from "react";
import { cn } from "@/lib/utils";

interface HudCardProps {
  children: ReactNode;
  className?: string;
  pulse?: boolean;
  onClick?: () => void;
}

/** `.gundam-hud-card` — base cockpit panel with corner brackets. */
export function HudCard({ children, className, pulse, onClick }: HudCardProps) {
  return (
    <div
      className={cn(
        "gundam-hud-card",
        pulse && "gundam-pulse",
        onClick && "cursor-pointer transition-all hover:gundam-pulse",
        className,
      )}
      onClick={onClick}
    >
      {children}
    </div>
  );
}

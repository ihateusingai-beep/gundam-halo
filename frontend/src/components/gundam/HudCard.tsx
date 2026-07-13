import { type HTMLAttributes, type ReactNode } from "react";
import { cn } from "@/lib/utils";

// Sprint 70 X-A1e.1: extend HudCardProps with the full set of
// native div attributes (excluding the ones HudCard overrides:
// className + onClick). This lets callers pass `data-testid`,
// `aria-*`, `role`, etc. without losing the HudCard styling.
// Previously, `data-testid` was silently dropped, leaving the
// testids in PersonalisedFineTuneSection's Card + other call
// sites as dead code.
type HudCardProps = Omit<HTMLAttributes<HTMLDivElement>, "className" | "onClick"> & {
  children: ReactNode;
  className?: string;
  pulse?: boolean;
  onClick?: () => void;
};

/** `.gundam-hud-card` — base cockpit panel with corner brackets. */
export function HudCard({
  children,
  className,
  pulse,
  onClick,
  ...rest
}: HudCardProps) {
  return (
    <div
      {...rest}
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

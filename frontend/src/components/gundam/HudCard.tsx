import { type HTMLAttributes, type ReactNode } from "react";
import { cn } from "@/lib/utils";

// Sprint 70 X-A1e.1: extend HudCardProps with the full set of
// native div attributes (excluding the ones HudCard overrides:
// className + onClick). This lets callers pass `data-testid`,
// `aria-*`, `role`, etc. without losing the HudCard styling.
// Previously, `data-testid` was silently dropped, leaving the
// testids in PersonalisedFineTuneSection's Card + other call
// sites as dead code.

/** Classes applied when `onClick` is provided (clickable
 *  panel): pointer cursor + smooth transition + the
 *  `hover:gundam-pulse` highlight (a soft border pulse on
 *  hover, distinct from the permanent `pulse` prop). */
const HOVER_PULSE_CLASSES = "cursor-pointer transition-all hover:gundam-pulse";

type HudCardProps = Omit<HTMLAttributes<HTMLDivElement>, "className" | "onClick"> & {
  children: ReactNode;
  className?: string;
  /** When true, applies the permanent `gundam-pulse` border
   *  animation (independent of the hover-pulse from `onClick`). */
  pulse?: boolean;
  /** Re-declared from HTMLAttributes so the call site can pass
   *  an onClick handler; HudCard adds the hover-pulse classes
   *  automatically when this is set. */
  onClick?: () => void;
};

/** `.gundam-hud-card` — base cockpit panel with corner brackets.
 *
 * Behavior matrix:
 *   - `pulse={true}`           → permanent `gundam-pulse` animation
 *   - `onClick` provided       → cursor-pointer + hover-pulse
 *   - both                     → clickable card with permanent pulse
 *   - neither                  → static panel
 *
 * All other native `<div>` attributes (`data-*`, `aria-*`,
 * `role`, `tabIndex`, etc.) are forwarded via `...rest` to the
 * underlying element. `className` is merged via `cn()` (caller's
 * classes win on conflict; HudCard's base classes are applied
 * first so they can be overridden).
 */
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
        onClick && HOVER_PULSE_CLASSES,
        className,
      )}
      onClick={onClick}
    >
      {children}
    </div>
  );
}

HudCard.displayName = "HudCard";

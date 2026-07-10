/**
 * Card — generic card primitive for non-cockpit routes.
 *
 * Sprint 62 U-A2. Sprint 50+ extracted the gundam-specific
 * chrome (frame corners, scan lines) into the cockpit shell.
 * Non-cockpit routes (`/audit`, `/setup`, future `/docs`)
 * need a card primitive that doesn't pull in the gundam
 * accent + per-card theming. This is the foundation.
 *
 * ## What this is
 *
 *   - A neutral card with consistent padding, border, and
 *     rounded corners.
 *   - 7 sub-components: `Card`, `CardHeader`, `CardTitle`,
 *     `CardDescription`, `CardAction`, `CardContent`,
 *     `CardFooter`.
 *   - `data-slot` attribute on every sub-component for
 *     downstream introspection.
 *
 * ## What this is NOT
 *
 *   - The gundam-specific card (`HudCard` in
 *     `components/gundam/HudCard.tsx`) — that one has the
 *     gundam accent border + the per-card iconography.
 *     The audit page and wizard use this generic card so
 *     they don't leak the cockpit's accent into non-cockpit
 *     routes.
 *   - A themeable component. Card inherits the surrounding
 *     theme (no override). Use CSS variables (e.g.
 *     `border-[var(--border-color)]`) for per-instance
 *     themeing.
 */
import * as React from "react";

import { cn } from "@/lib/utils";

/** Root: the card itself. */
function Card({
  className,
  ...props
}: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card"
      className={cn(
        "rounded-lg border border-[var(--border-color)] bg-[var(--bg-card)] text-[var(--text-primary)] shadow-sm",
        className,
      )}
      {...props}
    />
  );
}

/** Top section: title + description + optional action. */
function CardHeader({
  className,
  ...props
}: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-header"
      className={cn("flex flex-col space-y-1.5 p-4", className)}
      {...props}
    />
  );
}

/** Title text. Renders as a `<h3>` for semantic markup. */
function CardTitle({
  className,
  ...props
}: React.ComponentProps<"h3">) {
  return (
    <h3
      data-slot="card-title"
      className={cn(
        "text-lg font-semibold leading-none tracking-tight",
        className,
      )}
      {...props}
    />
  );
}

/** Subtitle / helper text. Renders as a `<p>`. */
function CardDescription({
  className,
  ...props
}: React.ComponentProps<"p">) {
  return (
    <p
      data-slot="card-description"
      className={cn("text-sm text-[var(--text-muted)]", className)}
      {...props}
    />
  );
}

/** Top-right action (e.g. a Refresh button). */
function CardAction({
  className,
  ...props
}: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-action"
      className={cn("flex items-center", className)}
      {...props}
    />
  );
}

/** Body. The bulk of the card. */
function CardContent({
  className,
  ...props
}: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-content"
      className={cn("p-4 pt-0", className)}
      {...props}
    />
  );
}

/** Bottom section (e.g. submit button row). */
function CardFooter({
  className,
  ...props
}: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-footer"
      className={cn(
        "flex items-center p-4 pt-0 border-t border-[var(--border-color)]",
        className,
      )}
      {...props}
    />
  );
}

export {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
};
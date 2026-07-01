/**
 * HoverPreviewSwatch — Sprint 50.
 *
 * One tile in the ThemeHoverCard's 2x4 grid. On `onMouseEnter`
 * the parent card sets the live-preview theme (DOM data-theme
 * attribute); on click the parent commits + closes the card.
 *
 * Visual states:
 * - default: muted border, neutral bg.
 * - hovered: accent border, bg-elevated bg (set by parent card
 *   via `[data-hovering=true]` attribute so the highlight follows
 *   the hovered swatch).
 * - committed: cyan border + glow + checkmark overlay.
 * - keyboard-focus: same ring as `:focus-visible` (a11y).
 */
import { cn } from "@/lib/utils";
import type { ThemeInfo } from "@/types/api";

interface HoverPreviewSwatchProps {
  theme: ThemeInfo;
  isCommitted: boolean;
  isHovered: boolean;
  onHover: () => void;
  onCommit: () => void;
}

export function HoverPreviewSwatch({
  theme,
  isCommitted,
  isHovered,
  onHover,
  onCommit,
}: HoverPreviewSwatchProps) {
  return (
    <button
      type="button"
      onMouseEnter={onHover}
      onFocus={onHover}
      onClick={onCommit}
      data-testid="theme-swatch"
      data-theme-id={theme.id}
      data-committed={isCommitted ? "true" : "false"}
      data-hovered={isHovered ? "true" : "false"}
      aria-label={`Preview and commit theme ${theme.name}`}
      aria-pressed={isCommitted}
      className={cn(
        "group relative w-20 h-20 flex flex-col items-center justify-center",
        "border bg-[var(--bg-elevated)] transition-all",
        "hover:bg-[var(--bg-overlay)]",
        isCommitted
          ? "border-[var(--accent)] shadow-[0_0_8px_var(--accent)]"
          : "border-[var(--border-color)]",
        isHovered && !isCommitted && "border-[var(--accent)]",
      )}
    >
      <span className="text-2xl" aria-hidden="true">
        {theme.emoji}
      </span>
      <span className="text-[10px] font-[Rajdhani] uppercase tracking-wider text-[var(--text-muted)] mt-1">
        {theme.name}
      </span>
      {isCommitted && (
        <span
          data-testid="theme-swatch-checkmark"
          className="absolute top-1 right-1 text-[var(--accent)] text-xs"
          aria-hidden="true"
        >
          ✓
        </span>
      )}
    </button>
  );
}
/**
 * ThemeHoverCard — Sprint 50.
 *
 * The hover-to-preview card that appears when the user hovers or
 * focuses the ThemeSwitcher floating button. Shows all 8 themes
 * in a 2-row × 4-column grid; mousing over a swatch updates the
 * cockpit's `[data-theme]` attribute for a live preview (NOT
 * persisted). Click commits + closes the card. Escape closes
 * without committing.
 *
 * State machine (driven by `useThemeStore`):
 *   - `theme`       — committed (localStorage).
 *   - `hoverTheme`  — live preview (DOM only, not persisted).
 *
 * Animation:
 *   - `onMouseEnter` of a swatch: sets hoverTheme after a 100ms
 *     delay (debounce).
 *   - `onMouseLeave` of the entire card: clears hoverTheme
 *     after a 200ms delay (gives the cursor time to move from
 *     one swatch to another without flicker).
 *
 * Keyboard:
 *   - Arrow keys navigate the grid.
 *   - Enter commits the focused swatch.
 *   - Escape closes the card without committing.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { useThemeStore } from "@/stores/theme";
import { cn } from "@/lib/utils";
import type { GundamTheme, ThemeInfo } from "@/types/api";

import { THEMES } from "./ThemeSwitcher";
import { HoverPreviewSwatch } from "./HoverPreviewSwatch";

interface ThemeHoverCardProps {
  /** When true, the card renders (parent controls open/close). */
  open: boolean;
  /** Called when the card should close (Escape, outside-click, after commit). */
  onClose: () => void;
  /** Custom className for the card frame (parent positions it). */
  className?: string;
}

const HOVER_DEBOUNCE_MS = 100;
const LEAVE_DEBOUNCE_MS = 200;

export function ThemeHoverCard({ open, onClose, className }: ThemeHoverCardProps) {
  const theme = useThemeStore((s) => s.theme);
  const setTheme = useThemeStore((s) => s.setTheme);
  const hoverTheme = useThemeStore((s) => s.hoverTheme);
  const setHoverTheme = useThemeStore((s) => s.setHoverTheme);
  const [focusIndex, setFocusIndex] = useState(0);
  const enterTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const leaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const cardRef = useRef<HTMLDivElement | null>(null);

  const clearTimers = useCallback(() => {
    if (enterTimer.current) {
      clearTimeout(enterTimer.current);
      enterTimer.current = null;
    }
    if (leaveTimer.current) {
      clearTimeout(leaveTimer.current);
      leaveTimer.current = null;
    }
  }, []);

  // Reset focus index + clear timers when the card opens.
  useEffect(() => {
    if (open) {
      clearTimers();
      setFocusIndex(THEMES.findIndex((t) => t.id === theme) >= 0 ? THEMES.findIndex((t) => t.id === theme) : 0);
    } else {
      clearTimers();
      // When the card closes, clear any lingering hover (the
      // store's `setHoverTheme(null)` will revert the DOM).
      setHoverTheme(null);
    }
  }, [open, theme, setHoverTheme, clearTimers]);

  // Escape to close.
  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  // Cleanup on unmount.
  useEffect(() => {
    return () => clearTimers();
  }, [clearTimers]);

  const handleEnter = useCallback(
    (t: ThemeInfo) => {
      // Clear pending leave (in case the cursor moved from one
      // swatch directly to another within the card).
      if (leaveTimer.current) {
        clearTimeout(leaveTimer.current);
        leaveTimer.current = null;
      }
      enterTimer.current = setTimeout(() => {
        setHoverTheme(t.id as GundamTheme);
      }, HOVER_DEBOUNCE_MS);
    },
    [setHoverTheme],
  );

  const handleLeave = useCallback(() => {
    // Debounce the revert so cursor movement between swatches
    // doesn't flicker the cockpit.
    if (enterTimer.current) {
      clearTimeout(enterTimer.current);
      enterTimer.current = null;
    }
    leaveTimer.current = setTimeout(() => {
      setHoverTheme(null);
    }, LEAVE_DEBOUNCE_MS);
  }, [setHoverTheme]);

  const handleCommit = useCallback(
    (t: ThemeInfo) => {
      setTheme(t.id as GundamTheme);
      toast.success(`Theme: ${t.name}`);
      onClose();
    },
    [setTheme, onClose],
  );

  const handleReset = useCallback(() => {
    setTheme(null as unknown as GundamTheme);
    toast("Theme: System default");
    onClose();
  }, [setTheme, onClose]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      const cols = 4;
      if (e.key === "ArrowRight") {
        e.preventDefault();
        setFocusIndex((i) => Math.min(THEMES.length - 1, i + 1));
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        setFocusIndex((i) => Math.max(0, i - 1));
      } else if (e.key === "ArrowDown") {
        e.preventDefault();
        setFocusIndex((i) => Math.min(THEMES.length - 1, i + cols));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setFocusIndex((i) => Math.max(0, i - cols));
      } else if (e.key === "Enter") {
        e.preventDefault();
        const t = THEMES[focusIndex];
        if (t) handleCommit(t);
      } else if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      }
    },
    [focusIndex, handleCommit, onClose],
  );

  if (!open) return null;

  // The theme that's currently being previewed (hoverTheme takes
  // precedence; falling back to the committed theme for the
  // header label).
  const previewed = hoverTheme ?? theme;
  const previewedInfo = THEMES.find((t) => t.id === previewed);

  return (
    <div
      ref={cardRef}
      role="dialog"
      aria-label="Theme hover preview"
      data-testid="theme-hover-card"
      onMouseLeave={handleLeave}
      onKeyDown={handleKeyDown}
      className={cn(
        "absolute bottom-full right-0 mb-2 w-[360px] p-3",
        "bg-[var(--bg-elevated)] border border-[var(--accent)]",
        "shadow-[0_0_24px_var(--accent)]",
        "z-[10000]",
        className,
      )}
    >
      <div className="flex items-center justify-between mb-2">
        <span
          data-testid="theme-hover-card-header"
          className="text-xs font-[Rajdhani] uppercase tracking-wider text-[var(--accent)]"
        >
          Preview: {previewedInfo?.name ?? "—"}
        </span>
        <button
          type="button"
          data-testid="theme-hover-card-close"
          onClick={onClose}
          className="text-xs font-mono text-[var(--text-muted)] hover:text-[var(--accent)]"
          aria-label="Close theme preview"
        >
          ✕ close
        </button>
      </div>
      <div
        className="grid grid-cols-4 gap-2"
        data-testid="theme-hover-grid"
      >
        {THEMES.map((t, i) => (
          <HoverPreviewSwatch
            key={t.id}
            theme={t}
            isCommitted={theme === t.id}
            isHovered={focusIndex === i || hoverTheme === t.id}
            onHover={() => {
              setFocusIndex(i);
              handleEnter(t);
            }}
            onCommit={() => handleCommit(t)}
          />
        ))}
      </div>
      <div className="mt-3 flex items-center justify-between text-[10px] font-mono text-[var(--text-muted)]">
        <span>
          ↑↓←→ navigate · Enter to commit
        </span>
        <button
          type="button"
          data-testid="theme-hover-card-reset"
          onClick={handleReset}
          className="hover:text-[var(--accent)]"
        >
          ✗ System default
        </button>
      </div>
    </div>
  );
}
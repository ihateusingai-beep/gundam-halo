/**
 * SettingsDrawer — Sprint 51.
 *
 * Bottom-sheet settings nav for mobile (<768px) viewports. Mirrors
 * the desktop SettingsSidebar's 8-tab / 2-group structure but in a
 * vertical 2×2 grid optimized for touch (64×64px tiles). Slides up
 * from the bottom; closes via backdrop click, Escape key, or the
 * × button.
 *
 * Why this exists: Sprint 50's MobileLayout used a flat 3-tab bottom
 * nav (Cockpit / + New / Settings) where tapping Settings just
 * navigated to /settings. Users on phones get a full settings page
 * that's narrow and scroll-heavy. The drawer pattern lets users jump
 * directly to a specific settings tab (matching the desktop sidebar's
 * quick-jump affordance).
 *
 * Body scroll lock: while open, document.body.style.overflow is set
 * to "hidden" so iOS Safari doesn't allow background scrolling under
 * the modal. Restored on close.
 *
 * Escape priority: we register a window keydown listener for Escape
 * when open. If CommandPalette is also open (unlikely on mobile but
 * possible on tablet), both handlers fire — CommandPalette's Escape
 * closes the palette first (it uses stopPropagation via preventDefault
 * on its input keydown).
 */
import { useEffect, type KeyboardEvent as ReactKeyboardEvent } from "react";

import { SIDEBAR_ENTRIES, type SidebarEntry, type SettingsTab } from "../../routes/settings/constants";

interface SettingsDrawerProps {
  open: boolean;
  onClose: () => void;
  onSelect: (tab: SettingsTab) => void;
  activeTab: SettingsTab;
}

const GROUP_LABELS: Record<SidebarEntry["group"], string> = {
  personalisation: "Personalisation",
  system: "System",
};

const GROUPS: SidebarEntry["group"][] = ["personalisation", "system"];

/** Bottom-sheet settings nav for mobile (<768px) viewports.
 *
 *  Sprint 51. Mirrors the desktop `SettingsSidebar`'s 8-tab /
 *  2-group structure but renders as a 2×2 grid of 64-px tiles
 *  optimised for touch. Slides up from the bottom edge.
 *
 *  Why this exists: Sprint 50's `MobileLayout` had a flat 3-tab
 *  bottom nav (Cockpit / + New / Settings) where tapping Settings
 *  just navigated to `/settings` — the full settings page was
 *  narrow and scroll-heavy on phones. The drawer pattern lets
 *  users jump directly to a specific tab, matching the desktop
 *  sidebar's quick-jump affordance.
 *
 *  Props:
 *    - `open: boolean` — controls visibility. The component
 *      itself is a no-op when closed (returns null + clears
 *      its effects).
 *    - `onClose: () => void` — fired when the user dismisses
 *      via Escape, backdrop click, backdrop keyboard (Enter /
 *      Space), or the ✕ button.
 *    - `onSelect: (tab: SettingsTab) => void` — fired when a
 *      tile is tapped. Always immediately followed by `onClose()`
 *      (a tap both selects and dismisses — the user is now on
 *      the settings tab they wanted).
 *    - `activeTab: SettingsTab` — currently-active tab from
 *      the parent (so the matching tile can be highlighted
 *      with `aria-current="page"`).
 *
 *  Behaviour:
 *    - **Escape key** closes the drawer (window keydown
 *      listener; cleaned up on unmount or close).
 *    - **Body scroll lock** while open (iOS Safari fix — sets
 *      `document.body.style.overflow = "hidden"`, restores the
 *      original on close).
 *    - **Backdrop click + keyboard** both dismiss. The backdrop
 *      is `role="button"` + `tabIndex={-1}` so keyboard users
 *      can focus and press Enter/Space.
 *    - **Safe-area** padding (`pb-[env(safe-area-inset-bottom)]`)
 *      so the drawer doesn't get cut off on iPhones with a
 *      home-indicator.
 *
 *  Tested by: `SettingsDrawer.test.tsx` — covers open/close,
 *  tile selection, Escape key, backdrop click.
 *
 *  Mounted by: `MobileLayout` (mobile-only).
 */
export function SettingsDrawer({ open, onClose, onSelect, activeTab }: SettingsDrawerProps) {
  // Escape key handler — closes drawer when open.
  useEffect(() => {
    if (!open) return;
    const handler = (e: globalThis.KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose]);

  // Body scroll lock — keep iOS Safari from scrolling the page under
  // the modal sheet.
  useEffect(() => {
    if (!open) return;
    const original = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = original;
    };
  }, [open]);

  if (!open) return null;

  /** Tap a tile → propagate selection up to parent, then
   *  close the drawer. The user lands on /settings/<tab>
   *  with the drawer dismissed. */
  const handleTabClick = (tab: SettingsTab) => {
    onSelect(tab);
    onClose();
  };

  /** Keyboard handler on the backdrop. The backdrop is
   *  `role="button"` + `tabIndex={-1}` so keyboard users can
   *  focus it; Enter or Space activates the close action. */
  const handleBackdropKeyDown = (e: ReactKeyboardEvent<HTMLDivElement>) => {
    // Enter / Space on backdrop also closes (a11y).
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      onClose();
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Settings sections"
      data-testid="settings-drawer"
      data-open="true"
      className="fixed inset-0 z-50 flex items-end"
    >
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm animate-fade-in"
        onClick={onClose}
        onKeyDown={handleBackdropKeyDown}
        role="button"
        aria-label="Close settings drawer"
        tabIndex={-1}
        data-testid="settings-drawer-backdrop"
      />
      <div
        className="relative w-full bg-[var(--bg-card)] rounded-t-2xl shadow-2xl
                   h-[80vh] flex flex-col animate-slide-up
                   pb-[env(safe-area-inset-bottom)]"
      >
        <div className="flex justify-center pt-2 pb-1" aria-hidden="true">
          <div className="w-12 h-1.5 bg-[var(--text-muted)]/30 rounded-full" />
        </div>
        <div className="flex items-center justify-between px-4 pb-2 border-b border-[var(--border-color)]">
          <h2 className="font-[Orbitron] text-lg text-[var(--accent)] uppercase tracking-widest">
            Settings
          </h2>
          <button
            type="button"
            data-testid="settings-drawer-close"
            onClick={onClose}
            aria-label="Close settings drawer"
            className="w-10 h-10 flex items-center justify-center rounded-full
                       text-[var(--text-muted)] hover:text-[var(--accent)] hover:bg-[var(--bg-overlay)]"
          >
            ✕
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-4 py-4">
          {GROUPS.map((group) => (
            <div key={group} className="mb-4">
              <h3
                data-testid={`settings-drawer-group-${group}`}
                className="text-xs font-[Rajdhani] uppercase tracking-widest text-[var(--text-muted)] mb-2"
              >
                {GROUP_LABELS[group]}
              </h3>
              <div className="grid grid-cols-2 gap-2">
                {SIDEBAR_ENTRIES.filter((e) => e.group === group).map((entry) => {
                  const isActive = activeTab === entry.id;
                  return (
                    <button
                      key={entry.id}
                      type="button"
                      data-testid={`settings-drawer-item-${entry.id}`}
                      data-active={isActive ? "true" : "false"}
                      onClick={() => handleTabClick(entry.id)}
                      aria-current={isActive ? "page" : undefined}
                      className={`h-16 px-3 flex items-center gap-2 rounded-lg text-left
                                  transition-colors border-l-[3px]
                                  ${isActive
                                    ? "bg-[var(--bg-overlay)] border-[var(--accent)] text-[var(--accent)]"
                                    : "bg-[var(--bg-elevated)] border-transparent text-[var(--text-secondary)] hover:bg-[var(--bg-overlay)] hover:text-[var(--accent)]"
                                  }`}
                    >
                      <span className="text-2xl" aria-hidden="true">
                        {entry.icon}
                      </span>
                      <span className="font-[Rajdhani] text-sm uppercase tracking-wider">
                        {entry.label}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
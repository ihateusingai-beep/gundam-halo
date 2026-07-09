import { useEffect, useState, type ReactNode } from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router";

import { SettingsDrawer } from "./SettingsDrawer";
import { isValidSettingsTab, type SettingsTab } from "../../routes/settings/constants";

interface MobileLayoutProps {
  children: ReactNode;
}

/**
 * Vertical-stack layout for mobile (<768px). See DASHBOARD.md §3.5.
 *
 * Sprint 51: bottom-nav "Settings" tap now opens the SettingsDrawer
 * instead of navigating directly to /settings. The drawer lets users
 * jump to a specific tab (matching the desktop sidebar's quick-jump
 * affordance) without first landing on the "general" tab and tapping
 * through. Auto-closes on route change so the drawer doesn't linger
 * after navigation.
 */
/** Vertical-stack layout for mobile (<768px).
 *
 *  Three regions:
 *    1. **Header** — title + a settings cog button (top-right).
 *       The cog opens the SettingsDrawer (no direct navigation).
 *    2. **Main** — page content (`children`).
 *    3. **Bottom nav** — three tap targets:
 *       Cockpit (→ `/`), + New (→ `/projects/new`), Settings
 *       (opens the drawer). The "Settings" entry is highlighted
 *       when either the drawer is open OR the user is on
 *       `/settings`.
 *
 *  Props:
 *    - `children: ReactNode` — the route content.
 *
 *  URL-driven state:
 *    - Reads `?tab=` from the search params (via
 *      `useSearchParams`) and validates with
 *      `isValidSettingsTab`. Unknown / missing values fall
 *      back to `"general"`.
 *    - `handleSelect(tab)` writes `?tab=<tab>` to the URL via
 *      `navigate()`, replacing history if the user is already
 *      on `/settings` (so the back button doesn't accumulate
 *      redundant entries).
 *
 *  Drawer lifecycle:
 *    - Auto-closes on `location.pathname` change so the drawer
 *      doesn't linger after the user navigates via Cockpit /
 *      + New links.
 *    - Selecting a tile inside the drawer also closes it
 *      (handled by SettingsDrawer — `onSelect` immediately
 *      calls `onClose`).
 *
 *  Mounted by: `App.tsx` route guard based on viewport
 *  breakpoint (<768px). The desktop `CockpitLayout` owns
 *  the larger viewports.
 *
 *  Tested by: `MobileLayout.test.tsx`.
 */
export function MobileLayout({ children }: MobileLayoutProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  const [drawerOpen, setDrawerOpen] = useState(false);

  const tabFromUrl = searchParams.get("tab");
  const activeTab: SettingsTab = isValidSettingsTab(tabFromUrl) ? tabFromUrl : "general";

  // Auto-close drawer on route change so it doesn't linger when the
  // user navigates away via the bottom nav (Cockpit / + New).
  useEffect(() => {
    setDrawerOpen(false);
  }, [location.pathname]);

  /** Open the settings drawer (called by both the header
   *  cog and the bottom-nav "Settings" button). */
  const openDrawer = () => setDrawerOpen(true);
  /** Close the settings drawer (called on Escape, backdrop
   *  click, tile select, route change). */
  const closeDrawer = () => setDrawerOpen(false);

  /** Handle a tile selection from inside the drawer.
   *
   *  Closes the drawer, then navigates to `/settings?tab=<tab>`.
   *  If we're already on `/settings`, use `replace: true` so
   *  the back button doesn't accumulate duplicate entries.
   *  Otherwise push normally (the back button returns to
   *  wherever the user was before). */
  const handleSelect = (tab: SettingsTab) => {
    closeDrawer();
    // Use replace if already on /settings, push otherwise — keeps
    // history clean.
    if (location.pathname === "/settings") {
      navigate(`/settings?tab=${tab}`, { replace: true });
    } else {
      navigate(`/settings?tab=${tab}`);
    }
  };

  return (
    <div className="gundam-hex-bg gundam-scanlines min-h-screen flex flex-col">
      {/* Top: project switcher (full width) */}
      <header className="border-b border-[var(--border-color)] bg-[var(--bg-card)]/80 backdrop-blur-md px-4 py-3 flex items-center justify-between">
        <h1 className="text-lg font-[Orbitron] text-[var(--accent)] tracking-widest uppercase">
          Gundam Halo
        </h1>
        <button
          type="button"
          data-testid="mobile-header-settings-button"
          onClick={openDrawer}
          aria-label="Open settings drawer"
          className="text-xs text-[var(--text-secondary)] hover:text-[var(--accent)] w-8 h-8 flex items-center justify-center"
        >
          ⚙
        </button>
      </header>

      {/* Center: main content (large) */}
      <main className="flex-1 overflow-y-auto p-3 min-h-0">{children}</main>

      {/* Bottom: tab bar — Cockpit / + New / Settings (drawer trigger) */}
      <nav className="border-t border-[var(--border-color)] bg-[var(--bg-card)]/80 backdrop-blur-md flex justify-around py-2 text-xs font-[Rajdhani] uppercase tracking-wider">
        <Link
          to="/"
          className={`px-3 py-1 ${
            location.pathname === "/"
              ? "text-[var(--accent)]"
              : "text-[var(--text-secondary)]"
          }`}
        >
          Cockpit
        </Link>
        <Link
          to="/projects/new"
          className={`px-3 py-1 ${
            location.pathname === "/projects/new"
              ? "text-[var(--accent)]"
              : "text-[var(--text-secondary)]"
          }`}
        >
          + New
        </Link>
        <button
          type="button"
          data-testid="mobile-settings-button"
          onClick={openDrawer}
          aria-label="Open settings drawer"
          aria-current={drawerOpen ? "true" : undefined}
          className={`px-3 py-1 ${
            drawerOpen || location.pathname === "/settings"
              ? "text-[var(--accent)]"
              : "text-[var(--text-secondary)]"
          }`}
        >
          Settings
        </button>
      </nav>

      <SettingsDrawer
        open={drawerOpen}
        onClose={closeDrawer}
        onSelect={handleSelect}
        activeTab={activeTab}
      />
    </div>
  );
}

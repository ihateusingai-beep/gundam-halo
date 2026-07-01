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

  const openDrawer = () => setDrawerOpen(true);
  const closeDrawer = () => setDrawerOpen(false);

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

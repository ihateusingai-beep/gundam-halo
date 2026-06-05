import { type ReactNode } from "react";
import { Link, useLocation } from "react-router";

interface MobileLayoutProps {
  children: ReactNode;
}

/** Vertical-stack layout for mobile (<768px). See DASHBOARD.md §3.5. */
export function MobileLayout({ children }: MobileLayoutProps) {
  const location = useLocation();

  return (
    <div className="gundam-hex-bg gundam-scanlines min-h-screen flex flex-col">
      {/* Top: project switcher (full width) */}
      <header className="border-b border-[var(--border-color)] bg-[var(--bg-card)]/80 backdrop-blur-md px-4 py-3 flex items-center justify-between">
        <h1 className="text-lg font-[Orbitron] text-[var(--accent)] tracking-widest uppercase">
          Gundam Halo
        </h1>
        <Link
          to="/settings"
          className="text-xs text-[var(--text-secondary)] hover:text-[var(--accent)]"
        >
          ⚙
        </Link>
      </header>

      {/* Center: main content (large) */}
      <main className="flex-1 overflow-y-auto p-3 min-h-0">{children}</main>

      {/* Bottom: tab bar for System / Tools / Channels */}
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
        <Link
          to="/settings"
          className={`px-3 py-1 ${
            location.pathname === "/settings"
              ? "text-[var(--accent)]"
              : "text-[var(--text-secondary)]"
          }`}
        >
          Settings
        </Link>
      </nav>
    </div>
  );
}

import { type ReactNode } from "react";
import { HudCard } from "@/components/gundam/HudCard";
import { useProjectsStore } from "@/stores/projects";
import { useSystemStore } from "@/stores/system";
import { useEffect } from "react";
import { Link, useLocation } from "react-router";

interface CockpitLayoutProps {
  children: ReactNode;
}

/** First-person cockpit layout for desktop (≥768px).
 *
 *  ┌─────────────────────────────────────────┐
 *  │ TopBar (project nav)                    │
 *  ├──────────┬─────────────────┬───────────┤
 *  │ Left     │  Center         │  Right    │
 *  │ (Tools)  │  (children)     │  (Gauges) │
 *  ├──────────┴─────────────────┴───────────┤
 *  │ Bottom (audit log / activity)           │
 *  └─────────────────────────────────────────┘
 */
export function CockpitLayout({ children }: CockpitLayoutProps) {
  const { projects, fetchProjects } = useProjectsStore();
  const { gauges, startPolling } = useSystemStore();
  const location = useLocation();

  useEffect(() => {
    fetchProjects();
    const stop = startPolling();
    return stop;
  }, [fetchProjects, startPolling]);

  return (
    <div className="gundam-hex-bg gundam-scanlines min-h-screen flex flex-col">
      {/* Top bar — project nav */}
      <header className="border-b border-[var(--border-color)] bg-[var(--bg-card)]/80 backdrop-blur-md px-4 py-3 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-3">
          <h1 className="text-xl font-[Orbitron] text-[var(--accent)] tracking-widest uppercase">
            Gundam Halo
          </h1>
          <span className="text-xs text-[var(--text-muted)] font-mono">// COCKPIT</span>
        </Link>
        <nav className="flex items-center gap-2 text-sm">
          <Link
            to="/"
            className="px-2 py-1 hover:text-[var(--accent)] text-[var(--text-secondary)]"
          >
            Overview
          </Link>
          <Link
            to="/projects/new"
            className="px-2 py-1 hover:text-[var(--accent)] text-[var(--text-secondary)]"
          >
            + New
          </Link>
          <Link
            to="/settings"
            className="px-2 py-1 hover:text-[var(--accent)] text-[var(--text-secondary)]"
          >
            Settings
          </Link>
        </nav>
      </header>

      <div className="flex-1 grid grid-cols-[200px_1fr_220px] gap-3 p-3 min-h-0">
        {/* Left panel — projects / tools */}
        <aside className="overflow-y-auto space-y-3">
          <HudCard>
            <h2 className="text-xs font-[Orbitron] text-[var(--accent)] uppercase tracking-widest mb-3">
              Projects
            </h2>
            <ul className="space-y-2 text-sm">
              {projects.length === 0 && (
                <li className="text-[var(--text-muted)] text-xs">No projects yet</li>
              )}
              {projects.map((p) => (
                <li key={p.name}>
                  <Link
                    to={`/projects/${p.name}`}
                    className={`block px-2 py-1 rounded hover:bg-[var(--bg-elevated)] ${
                      location.pathname === `/projects/${p.name}`
                        ? "text-[var(--accent)]"
                        : "text-[var(--text-secondary)]"
                    }`}
                  >
                    {p.name}
                  </Link>
                </li>
              ))}
            </ul>
          </HudCard>
        </aside>

        {/* Center — main content */}
        <main className="overflow-y-auto min-w-0">{children}</main>

        {/* Right panel — Mac system gauges */}
        <aside className="overflow-y-auto space-y-3">
          <HudCard>
            <h2 className="text-xs font-[Orbitron] text-[var(--accent)] uppercase tracking-widest mb-3">
              System
            </h2>
            <div className="flex justify-around">
              <div className="text-center">
                <div className="text-xs text-[var(--text-muted)] uppercase font-[Rajdhani]">CPU</div>
                <div className="text-2xl font-[Orbitron] text-[var(--accent)]">
                  {gauges?.cpu_percent.toFixed(0) ?? "—"}
                </div>
                <div className="text-[10px] text-[var(--text-muted)]">%</div>
              </div>
              <div className="text-center">
                <div className="text-xs text-[var(--text-muted)] uppercase font-[Rajdhani]">RAM</div>
                <div className="text-2xl font-[Orbitron] text-[var(--accent)]">
                  {gauges?.memory_percent.toFixed(0) ?? "—"}
                </div>
                <div className="text-[10px] text-[var(--text-muted)]">%</div>
              </div>
              <div className="text-center">
                <div className="text-xs text-[var(--text-muted)] uppercase font-[Rajdhani]">DISK</div>
                <div className="text-2xl font-[Orbitron] text-[var(--accent)]">
                  {gauges?.disk_percent.toFixed(0) ?? "—"}
                </div>
                <div className="text-[10px] text-[var(--text-muted)]">%</div>
              </div>
            </div>
          </HudCard>
        </aside>
      </div>

      {/* Bottom bar — status / activity */}
      <footer className="border-t border-[var(--border-color)] bg-[var(--bg-card)]/80 backdrop-blur-md px-4 py-2 text-xs text-[var(--text-muted)] font-mono flex items-center justify-between">
        <span>GUNDAM HALO v0.1.0 · COCKPIT ONLINE</span>
        <span>{location.pathname}</span>
      </footer>
    </div>
  );
}

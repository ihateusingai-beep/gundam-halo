import { type ReactNode } from "react";
import { Link, useLocation } from "react-router";
import { Toaster } from "sonner";

import { HudCard } from "@/components/gundam/HudCard";
import { Gauge } from "@/components/gundam/Gauge";
import { useProjectsStore } from "@/stores/projects";
import { useSystemStore } from "@/stores/system";
import { useEffect } from "react";

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
      {/* Toaster (Sonner) — global */}
      <Toaster
        theme="dark"
        position="top-right"
        richColors
        toastOptions={{
          classNames: {
            toast:
              "!bg-[var(--bg-card)] !border !border-[var(--accent)] !text-[var(--text-primary)]",
            title: "!text-[var(--accent)] !font-[Orbitron] !tracking-wider",
            description: "!text-[var(--text-secondary)]",
          },
        }}
      />

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

      <div className="flex-1 grid grid-cols-[200px_1fr_240px] gap-3 p-3 min-h-0">
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
                    className={`flex items-center justify-between px-2 py-1 rounded hover:bg-[var(--bg-elevated)] ${
                      location.pathname === `/projects/${p.name}`
                        ? "text-[var(--accent)]"
                        : "text-[var(--text-secondary)]"
                    }`}
                  >
                    <span>{p.name}</span>
                    <span
                      className={`text-[10px] uppercase ${
                        p.status === "active"
                          ? "text-[var(--success)]"
                          : p.status === "archived"
                          ? "text-[var(--text-muted)]"
                          : "text-[var(--warning)]"
                      }`}
                    >
                      {p.status === "active" ? "●" : p.status}
                    </span>
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
            <div className="flex justify-around items-end h-32">
              <Gauge label="CPU" value={gauges?.cpu_percent ?? 0} />
              <Gauge label="RAM" value={gauges?.memory_percent ?? 0} />
              <Gauge label="DSK" value={gauges?.disk_percent ?? 0} />
            </div>
            <div className="mt-3 grid grid-cols-2 gap-1 text-[10px] font-mono text-[var(--text-muted)]">
              <div>↑ {(gauges?.network_sent_mb ?? 0).toFixed(1)} MB</div>
              <div>↓ {(gauges?.network_recv_mb ?? 0).toFixed(1)} MB</div>
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

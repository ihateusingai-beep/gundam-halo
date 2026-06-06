import { type ReactNode } from "react";
import { Link, useLocation } from "react-router";
import { Toaster } from "sonner";

import { HudCard } from "@/components/gundam/HudCard";
import { Gauge } from "@/components/gundam/Gauge";
import { ConnectionStatus } from "@/components/gundam/ConnectionStatus";
import { MissionLog } from "@/components/gundam/MissionLog";
import { ProjectCard } from "@/components/gundam/ProjectCard";
import { useProjectsStore } from "@/stores/projects";
import { useSystemStore } from "@/stores/system";
import { useWsEvent, useWsStatus } from "@/lib/ws";
import { useEffect } from "react";

interface CockpitLayoutProps {
  children: ReactNode;
}

/** First-person cockpit layout for desktop (≥768px).
 *
 *  Frame layers (z-index, bottom → top):
 *   0  background image (optional, [data-bg="core-XX"])
 *   1  hex grid overlay
 *   1  content
 *   5  CRT vignette (fixed, pointer-events: none)
 *   9996 corner brackets + brand/status (fixed)
 *   9997 top scan line (fixed)
 *
 *   ┌──⌐  ◢ GUNDAM HALO                              SYSTEMS ●  ⌐──┐
 *   │                                                          │
 *   │  [TopBar — project nav]                                  │
 *   │  ┌──────────┬─────────────────┬───────────┐             │
 *   │  │ Left     │  Center         │  Right    │             │
 *   │  │ (Tools)  │  (children)     │  (Gauges) │             │
 *   │  ├──────────┴─────────────────┴───────────┤             │
 *   │  │ Bottom — ticker / status                │             │
 *   │  └──────────────────────────────────────────┘             │
 *   └──⌐                                                  ¬──┘
 */
export function CockpitLayout({ children }: CockpitLayoutProps) {
  const { projects, fetchProjects } = useProjectsStore();
  const { gauges, setGauges, startPolling } = useSystemStore();
  const { connected } = useWsStatus();
  const location = useLocation();

  useEffect(() => {
    fetchProjects();
  }, [fetchProjects]);

  // Push live gauges from WS into the store.
  useWsEvent("system_gauges", (event) => {
    setGauges(event.data);
  });

  // Fallback to REST polling if WS isn't connected (e.g. server restart).
  useEffect(() => {
    if (connected) return; // WS will handle it
    const stop = startPolling();
    return stop;
  }, [connected, startPolling]);

  return (
    <div className="gundam-cockpit-frame gundam-cockpit-vignette gundam-hex-bg min-h-screen flex flex-col">
      {/* Background image layer (visible only when [data-bg] is set on <html>) */}
      <div className="gundam-cockpit-bg" aria-hidden="true" />

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

      {/* Frame chrome (fixed) — corner brackets, brand, status */}
      <div className="gundam-frame-corner gundam-frame-corner-tl" aria-hidden="true" />
      <div className="gundam-frame-corner gundam-frame-corner-tr" aria-hidden="true" />
      <div className="gundam-frame-corner gundam-frame-corner-bl" aria-hidden="true" />
      <div className="gundam-frame-corner gundam-frame-corner-br" aria-hidden="true" />
      <div className="gundam-frame-brand" aria-hidden="true">GUNDAM HALO // COCKPIT</div>
      <div className="gundam-frame-status" aria-hidden="true">SYSTEMS ONLINE · v0.1.0</div>
      <div className="gundam-scan" aria-hidden="true" />

      {/* Top bar — project nav */}
      <header className="border-b border-[var(--border-color)] bg-[var(--bg-card)]/80 backdrop-blur-md px-4 py-3 mt-2 flex items-center justify-between">
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
        {/* Left panel — projects + mission log */}
        <aside className="overflow-y-auto space-y-3">
          <HudCard>
            <h2 className="text-xs font-[Orbitron] text-[var(--accent)] uppercase tracking-widest mb-3">
              Projects
            </h2>
            <div className="space-y-2">
              {projects.length === 0 && (
                <div className="text-[var(--text-muted)] text-xs text-center py-3">
                  No projects yet
                </div>
              )}
              {projects.map((p) => (
                <ProjectCard key={p.name} project={p} />
              ))}
            </div>
          </HudCard>

          <HudCard>
            <div className="flex items-center justify-between mb-2">
              <h2 className="text-xs font-[Orbitron] text-[var(--accent)] uppercase tracking-widest">
                Mission Log
              </h2>
              <span className="text-[9px] text-[var(--text-muted)] font-mono">
                LIVE FEED
              </span>
            </div>
            <MissionLog maxEntries={30} />
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
            <div className="mt-2 pt-2 border-t border-[var(--border-color)]">
              <ConnectionStatus />
            </div>
          </HudCard>
        </aside>
      </div>

      {/* Bottom bar — status */}
      <footer className="border-t border-[var(--border-color)] bg-[var(--bg-card)]/80 backdrop-blur-md px-4 py-2 mb-2 mx-2 text-xs text-[var(--text-muted)] font-mono flex items-center justify-between gap-4">
        <span>RX-0 // UNICORN</span>
        <span className="shrink-0">{location.pathname}</span>
      </footer>
    </div>
  );
}

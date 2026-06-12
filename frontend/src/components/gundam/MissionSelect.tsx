import { useEffect } from "react";
import { Link } from "react-router";

import { HudCard } from "@/components/gundam/HudCard";
import { Radar } from "@/components/gundam/Radar";
import { MissionCard } from "@/components/gundam/MissionCard";
import { useProjectsStore } from "@/stores/projects";
import { formatRelative } from "@/lib/time";

/** Mission Select — the cockpit's standby view shown on `/`.
 *
 *  Layout:
 *    ┌────────────────────────────────────────────┐
 *    │ Header HudCard                             │
 *    ├────────────────────────────────────────────┤
 *    │           BIG RETICLE                      │
 *    │           SELECT MISSION                    │
 *    │           (word-reveal + glitch)            │
 *    │           [ + NEW MISSION ] [ ARCHIVE ]    │
 *    ├────────────────────────────────────────────┤
 *    │ Mission Roster (2-3 wide grid)              │
 *    │   mission mission mission                  │
 *    │   mission mission mission                  │
 *    └────────────────────────────────────────────┘
 *
 *  This is the first impression — when no project is active, the pilot
 *  sees a clear "awaiting orders" prompt and the recent mission roster.
 */
export function MissionSelect() {
  const { projects, loading, fetchProjects } = useProjectsStore();

  useEffect(() => {
    fetchProjects();
  }, [fetchProjects]);

  const totalMessages = projects.reduce((sum, p) => sum + p.message_count, 0);
  const lastActivity = projects
    .map((p) => p.last_activity_at)
    .filter(Boolean)
    .sort()
    .pop() || null;

  return (
    <div className="space-y-4">
      {/* Top status bar */}
      <HudCard pulse>
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div>
            <div className="text-[10px] font-[Orbitron] text-[var(--text-muted)] uppercase tracking-widest">
              Cockpit Status
            </div>
            <div className="text-lg font-[Orbitron] text-[var(--accent)] tracking-widest uppercase mt-1">
              <span className="gundam-reveal-mission-title">Awaiting Orders</span>
            </div>
          </div>
          <div className="flex items-center gap-6 text-[10px] font-mono">
            <Stat label="Missions" value={String(projects.length)} />
            <Stat label="Messages" value={String(totalMessages)} />
            <Stat
              label="Last Activity"
              value={lastActivity ? formatRelative(lastActivity) : "—"}
            />
          </div>
        </div>
      </HudCard>

      {/* Big reticle — SELECT MISSION prompt */}
      <HudCard className="!py-10 md:!py-16">
        <div className="flex flex-col items-center text-center space-y-4">
          <div className="gundam-target">
            <div className="text-center px-8 py-4">
              <div className="text-[10px] font-[Orbitron] text-[var(--text-muted)] uppercase tracking-[0.4em] mb-2 gundam-glitch-text">
                ▸ Cockpit Online ◂
              </div>
              <h2 className="text-3xl md:text-5xl font-[Orbitron] text-[var(--accent)] tracking-[0.2em] uppercase gundam-reveal gundam-reveal-1">
                Select Mission
              </h2>
              <p className="text-sm text-[var(--text-secondary)] mt-3 max-w-md mx-auto gundam-reveal gundam-reveal-2">
                Engage an existing project or initialize a new one to begin operations.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3 pt-2 gundam-reveal gundam-reveal-3">
            <Link
              to="/projects/new"
              className="px-6 py-2.5 border border-[var(--accent)] bg-[var(--bg-elevated)] text-[var(--accent)] rounded font-[Orbitron] uppercase tracking-widest text-sm hover:bg-[var(--accent)] hover:text-[var(--bg-primary)] transition-colors"
            >
              + New Mission
            </Link>
            {projects.length > 0 && (
              <span
                className="text-[10px] text-[var(--text-muted)] font-mono uppercase tracking-widest"
              >
                or engage below ▾
              </span>
            )}
          </div>
        </div>
      </HudCard>

      {/* Mission roster */}
      {loading ? (
        <HudCard>
          <div className="flex items-center gap-3">
            <Radar size={40} />
            <p className="text-[var(--text-muted)] font-mono text-sm">Scanning missions…</p>
          </div>
        </HudCard>
      ) : projects.length === 0 ? (
        <HudCard>
          <div className="text-center py-8 space-y-3">
            <Radar size={60} className="mx-auto" />
            <p className="text-[var(--text-secondary)] text-sm">
              No missions logged yet.
            </p>
            <p className="text-[10px] text-[var(--text-muted)] font-mono uppercase tracking-widest">
              Initialize your first project to get started
            </p>
          </div>
        </HudCard>
      ) : (
        <HudCard>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-[Orbitron] text-[var(--accent)] uppercase tracking-widest">
              Recent Missions
            </h2>
            <span className="text-[10px] text-[var(--text-muted)] font-mono">
              {projects.length} total
            </span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {projects.map((p) => (
              <MissionCard key={p.name} project={p} />
            ))}
          </div>
        </HudCard>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col items-end">
      <span className="text-[var(--text-muted)] uppercase tracking-wider text-[9px]">
        {label}
      </span>
      <span className="text-[var(--accent)] font-[Orbitron] text-sm mt-0.5">
        {value}
      </span>
    </div>
  );
}

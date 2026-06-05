import { HudCard } from "@/components/gundam/HudCard";
import { StatusDot } from "@/components/gundam/StatusDot";
import { Radar } from "@/components/gundam/Radar";
import { useProjectsStore } from "@/stores/projects";
import { useEffect } from "react";
import { Link } from "react-router";
import { toast } from "sonner";

/** Cockpit overview — landing page. */
export function OverviewPage() {
  const { projects, loading, fetchProjects } = useProjectsStore();

  useEffect(() => {
    fetchProjects();
  }, [fetchProjects]);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <HudCard pulse>
        <h2 className="text-2xl font-[Orbitron] text-[var(--accent)] tracking-widest uppercase gundam-text-neon mb-3">
          GUNDAM HALO
        </h2>
        <p className="text-sm text-[var(--text-secondary)] font-[Exo_2]">
          Personal AI agent on Mac. Hermes-like feel, MiniMax brain, deep Mac control, per-project isolation.
        </p>
        <div className="mt-4 flex items-center gap-4">
          <StatusDot status="ok" label="ONLINE" />
          <span className="text-xs text-[var(--text-muted)] font-mono">v0.1.0</span>
        </div>
      </HudCard>

      <HudCard>
        <h2 className="text-sm font-[Orbitron] text-[var(--accent)] uppercase tracking-widest mb-3">
          Recent Projects
        </h2>
        {loading && (
          <div className="flex items-center gap-2 text-xs text-[var(--text-muted)]">
            <div className="gundam-radar w-4 h-4" />
            <span>Loading...</span>
          </div>
        )}
        {!loading && projects.length === 0 && (
          <div className="text-center py-8">
            <Radar size={80} className="mx-auto mb-3" />
            <p className="text-sm text-[var(--text-secondary)] mb-3">No projects yet</p>
            <Link
              to="/projects/new"
              onClick={() => toast("Let's start a new project", { icon: "🚀" })}
              className="inline-block px-4 py-2 border border-[var(--accent)] text-[var(--accent)] rounded hover:bg-[var(--accent)] hover:text-[var(--bg-primary)] transition-colors text-sm font-[Rajdhani] uppercase tracking-wider"
            >
              + New Project
            </Link>
          </div>
        )}
        {!loading && projects.length > 0 && (
          <ul className="space-y-1 text-sm">
            {projects.slice(0, 5).map((p) => (
              <li key={p.name}>
                <Link
                  to={`/projects/${p.name}`}
                  className="block px-2 py-1.5 rounded hover:bg-[var(--bg-elevated)] text-[var(--text-secondary)]"
                >
                  <span className="text-[var(--accent)]">{p.name}</span>
                  <span className="text-xs text-[var(--text-muted)] ml-2">
                    ({p.status})
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </HudCard>
    </div>
  );
}

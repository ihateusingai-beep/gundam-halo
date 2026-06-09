import { Link } from "react-router";

import type { ProjectSummary } from "@/types/api";
import { cn } from "@/lib/utils";

interface MissionCardProps {
  project: ProjectSummary;
  className?: string;
}

/** Larger "mission roster" version of ProjectCard, used in the MissionSelect mode.
 *
 *  Same data as ProjectCard but with bigger padding, stronger corner
 *  brackets, and a hover-revealed "ENGAGE ▸" hint.
 */
export function MissionCard({ project, className = "" }: MissionCardProps) {
  const isArchived = project.status === "archived";

  const statusColor = isArchived
    ? "var(--text-muted)"
    : "var(--success)";

  const statusLabel = isArchived ? "ARCHIVED" : "ACTIVE";

  const lastActivity = project.last_activity_at
    ? formatRelative(project.last_activity_at)
    : "—";

  return (
    <Link
      to={`/projects/${project.name}`}
      className={cn(
        "gundam-mission-card",
        isArchived && "gundam-mission-card-archived",
        className,
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="text-base font-[Orbitron] text-[var(--accent)] tracking-wider truncate uppercase">
            {project.name}
          </div>
          <div className="text-[10px] text-[var(--text-muted)] font-mono mt-1">
            {project.agent_type}
            {project.session_count > 0 && (
              <>
                {" · "}
                {project.session_count} sess
                {project.session_count === 1 ? "" : "s"}
              </>
            )}
          </div>
        </div>
        <div className="flex flex-col items-end gap-1">
          <div className="flex items-center gap-1">
            <span
              style={{
                display: "inline-block",
                width: "6px",
                height: "6px",
                borderRadius: "50%",
                background: statusColor,
                boxShadow: `0 0 6px ${statusColor}`,
              }}
            />
            <span
              className="text-[9px] font-mono uppercase tracking-widest"
              style={{ color: statusColor }}
            >
              {statusLabel}
            </span>
          </div>
        </div>
      </div>

      <div className="mt-3 flex items-center justify-between text-[10px] font-mono">
        <span className="text-[var(--text-muted)]">
          <span className="opacity-60">last: </span>
          {lastActivity}
        </span>
        <span className="text-[var(--accent)] font-[Orbitron] tracking-wider">
          {project.message_count}
          <span className="text-[var(--text-muted)] ml-0.5">msg</span>
        </span>
      </div>

      <div className="gundam-engage-hint">ENGAGE ▸</div>
    </Link>
  );
}

function formatRelative(iso: string): string {
  if (!iso) return "—";
  try {
    const then = new Date(iso).getTime();
    if (isNaN(then)) return iso.slice(0, 16);
    const now = Date.now();
    const diffMs = now - then;
    const sec = Math.floor(diffMs / 1000);
    if (sec < 60) return `${sec}s ago`;
    const min = Math.floor(sec / 60);
    if (min < 60) return `${min}m ago`;
    const hr = Math.floor(min / 60);
    if (hr < 24) return `${hr}h ago`;
    const day = Math.floor(hr / 24);
    if (day < 30) return `${day}d ago`;
    return new Date(iso).toLocaleDateString("en", { day: "numeric", month: "short" });
  } catch {
    return iso;
  }
}

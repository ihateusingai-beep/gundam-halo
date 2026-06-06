import { Link } from "react-router";

import { useLocation } from "react-router";
import { cn } from "@/lib/utils";
import type { ProjectSummary } from "@/types/api";

interface ProjectCardProps {
  project: ProjectSummary;
  className?: string;
}

/** Mobile-suit-style status panel for a single project.
 *
 *  Visual: corner brackets like the cockpit frame (smaller), status indicator
 *  on the right, agent type + last activity in the meta row, energy/activity
 *  bar at the bottom showing message density.
 *
 *  Active projects get a subtle pulse border; archived get a muted treatment.
 *  Hover: corner brackets brighten, card lifts slightly.
 */
export function ProjectCard({ project, className = "" }: ProjectCardProps) {
  const location = useLocation();
  const isCurrent = location.pathname === `/projects/${project.name}`;

  const isArchived = project.status === "archived";
  const isPaused = project.status === "paused";
  const isActive = !isArchived && !isPaused;

  const statusColor = isArchived
    ? "var(--text-muted)"
    : isPaused
    ? "var(--warning)"
    : "var(--success)";

  const statusLabel = isArchived ? "ARCHIVED" : isPaused ? "PAUSED" : "ACTIVE";

  // Activity level: rough heuristic — 0-50 messages = low, 50-200 = mid, 200+ = high
  const activityLevel: "low" | "mid" | "high" =
    project.message_count >= 200
      ? "high"
      : project.message_count >= 50
      ? "mid"
      : "low";

  const activityPct = Math.min(100, project.message_count / 2); // 200 msgs = 100%

  const lastActivity = project.last_activity_at
    ? formatRelative(project.last_activity_at)
    : "—";

  return (
    <Link
      to={`/projects/${project.name}`}
      className={cn(
        "gundam-project-card",
        isActive && "gundam-project-card-active",
        isArchived && "gundam-project-card-archived",
        isCurrent && "gundam-project-card-current",
        className,
      )}
    >
      {/* Top row — name + status indicator */}
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="text-sm font-[Orbitron] text-[var(--accent)] tracking-wider truncate uppercase">
            {project.name}
          </div>
          <div className="text-[9px] text-[var(--text-muted)] font-mono mt-0.5">
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
          {/* Status dot */}
          <div
            className="flex items-center gap-1"
            title={`Status: ${statusLabel}`}
          >
            <span
              className={isActive ? "gundam-status-pulse" : ""}
              style={{
                display: "inline-block",
                width: "6px",
                height: "6px",
                borderRadius: "50%",
                background: statusColor,
                boxShadow: isActive ? `0 0 6px ${statusColor}` : "none",
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

      {/* Middle — last activity + message count */}
      <div className="mt-2 flex items-center justify-between text-[10px] font-mono">
        <span className="text-[var(--text-muted)]">
          <span className="opacity-60">last: </span>
          {lastActivity}
        </span>
        <span className="text-[var(--accent)] font-[Orbitron] tracking-wider">
          {project.message_count}
          <span className="text-[var(--text-muted)] ml-0.5">msg</span>
        </span>
      </div>

      {/* Bottom — energy/activity bar */}
      <div className="mt-2 gundam-energy-bar">
        <div
          className="gundam-energy-bar-fill"
          style={{
            width: `${activityPct}%`,
            opacity: isArchived ? 0.3 : 1,
            background:
              activityLevel === "high"
                ? "linear-gradient(90deg, var(--success), var(--accent))"
                : activityLevel === "mid"
                ? "var(--accent)"
                : "var(--text-muted)",
          }}
        />
      </div>
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

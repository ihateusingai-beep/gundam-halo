import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router";
import { toast } from "sonner";

import { HudCard } from "@/components/gundam/HudCard";
import { Reticle } from "@/components/gundam/Reticle";
import { api, ApiError } from "@/lib/api";
import type { SessionListItem } from "@/types/api";

/** Project memory browser — vertical timeline of past sessions.
 *
 *  Layout:
 *    ┌────────────────────────────────────────────┐
 *    │ Header: name + summary stats               │
 *    ├────────────────────────────────────────────┤
 *    │ Filters: All / native_react / simple       │
 *    ├────────────────────────────────────────────┤
 *    │ Timeline (left line, right cards)          │
 *    │  ┃                                         │
 *    │  ● Today                                   │
 *    │  ┃  ┌─────────────────────────────────┐    │
 *    │  ●  ┃ 14:23  3 msgs  native_react     │    │
 *    │  ┃  └─────────────────────────────────┘    │
 *    │  ┃                                         │
 *    │  ● Yesterday                               │
 *    │  ┃  ...                                    │
 *    └────────────────────────────────────────────┘
 *
 *  Click a card → navigate to /projects/:id/sessions/:sessionId
 *  (M10-B2 SessionDetailPage) for the full transcript. Inline
 *  expansion was removed in favour of the dedicated page — the
 *  bubble-rendering logic now lives in one place (MessageBubble
 *  from A8) and sessions get shareable deep-links.
 */
export function ProjectMemoryPage() {
  const { id } = useParams<{ id: string }>();
  const [sessions, setSessions] = useState<SessionListItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filterAgent, setFilterAgent] = useState<string>("all");

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    setError(null);
    api
      .listProjectMemory(id)
      .then(setSessions)
      .catch((e) => {
        const msg = e instanceof ApiError ? e.message : String(e);
        setError(msg);
        toast.error("Failed to load memory", { description: msg });
      })
      .finally(() => setLoading(false));
  }, [id]);

  // Compute summary stats
  const stats = useMemo(() => {
    if (sessions.length === 0) {
      return { count: 0, totalMessages: 0, agents: [] as string[], firstAt: null, lastAt: null };
    }
    const totalMessages = sessions.reduce((sum, s) => sum + s.message_count, 0);
    const agents = Array.from(new Set(sessions.map((s) => s.agent_type)));
    const sorted = [...sessions].sort((a, b) => a.created_at.localeCompare(b.created_at));
    return {
      count: sessions.length,
      totalMessages,
      agents,
      firstAt: sorted[0]?.created_at,
      lastAt: sorted[sorted.length - 1]?.updated_at || sorted[sorted.length - 1]?.created_at,
    };
  }, [sessions]);

  // Group sessions by date bucket
  const groups = useMemo(() => {
    const filtered =
      filterAgent === "all"
        ? sessions
        : sessions.filter((s) => s.agent_type === filterAgent);

    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);
    const weekAgo = new Date(today);
    weekAgo.setDate(weekAgo.getDate() - 7);

    const buckets: Record<string, SessionListItem[]> = {
      Today: [],
      Yesterday: [],
      "This Week": [],
      Earlier: [],
    };

    for (const s of filtered) {
      const d = new Date(s.created_at);
      if (d >= today) buckets.Today.push(s);
      else if (d >= yesterday) buckets.Yesterday.push(s);
      else if (d >= weekAgo) buckets["This Week"].push(s);
      else buckets.Earlier.push(s);
    }

    // Sort each bucket by created_at desc (newest first)
    for (const k of Object.keys(buckets)) {
      buckets[k].sort((a, b) => b.created_at.localeCompare(a.created_at));
    }

    return Object.entries(buckets).filter(([_, v]) => v.length > 0);
  }, [sessions, filterAgent]);

  if (loading) {
    return (
      <HudCard>
        <div className="flex items-center gap-3">
          <div className="gundam-radar w-8 h-8" />
          <p className="text-[var(--text-muted)] font-mono">Loading memory...</p>
        </div>
      </HudCard>
    );
  }

  if (error) {
    return (
      <HudCard>
        <p className="text-[var(--danger)]">⚠ {error}</p>
      </HudCard>
    );
  }

  if (sessions.length === 0) {
    return (
      <div className="space-y-3">
        <HudCard>
          <h2 className="text-2xl font-[Orbitron] text-[var(--accent)] tracking-widest uppercase">
            Memory: {id}
          </h2>
        </HudCard>
        <HudCard>
          <Reticle>
            <h3 className="text-lg font-[Orbitron] text-[var(--accent)] tracking-widest uppercase mb-2">
              NO MISSIONS LOGGED
            </h3>
            <p className="text-sm text-[var(--text-secondary)]">
              Start a session from the{" "}
              <a href={`/projects/${id}`} className="text-[var(--accent)] underline">
                project page
              </a>{" "}
              to begin recording.
            </p>
          </Reticle>
        </HudCard>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* Header — name + summary stats */}
      <HudCard>
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div>
            <h2 className="text-2xl font-[Orbitron] text-[var(--accent)] tracking-widest uppercase">
              Memory: {id}
            </h2>
            <p className="text-xs text-[var(--text-muted)] font-mono mt-1">
              {stats.count} session{stats.count === 1 ? "" : "s"} ·{" "}
              {stats.totalMessages} message{stats.totalMessages === 1 ? "" : "s"}
              {stats.firstAt && stats.lastAt && (
                <>
                  {" · "}
                  <span title={`${stats.firstAt} → ${stats.lastAt}`}>
                    {formatDateRange(stats.firstAt, stats.lastAt)}
                  </span>
                </>
              )}
            </p>
          </div>

          {/* Agent type filter */}
          {stats.agents.length > 1 && (
            <div className="flex items-center gap-1 text-[10px] font-mono">
              <span className="text-[var(--text-muted)] uppercase tracking-wider">agent:</span>
              {["all", ...stats.agents].map((a) => (
                <button
                  key={a}
                  onClick={() => setFilterAgent(a)}
                  className={`px-2 py-0.5 rounded border transition-colors ${
                    filterAgent === a
                      ? "border-[var(--accent)] text-[var(--accent)] bg-[var(--bg-elevated)]"
                      : "border-[var(--border-color)] text-[var(--text-muted)] hover:border-[var(--accent)]"
                  }`}
                >
                  {a}
                </button>
              ))}
            </div>
          )}
        </div>
      </HudCard>

      {/* Timeline */}
      <HudCard>
        <div className="gundam-timeline">
          {groups.map(([groupName, items]) => (
            <div key={groupName}>
              <div className="gundam-timeline-group-header">{groupName}</div>
              {items.map((s) => (
                <SessionNode key={s.id} session={s} projectId={id ?? ""} />
              ))}
            </div>
          ))}
        </div>
      </HudCard>
    </div>
  );
}

function SessionNode({
  session,
  projectId,
}: {
  session: SessionListItem;
  projectId: string;
}) {
  return (
    <div className="gundam-timeline-node">
      <Link
        to={`/projects/${projectId}/sessions/${session.id}`}
        className={`gundam-memory-card block hover:gundam-memory-card-expanded transition-colors`}
      >
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-3">
            <span className="text-[10px] text-[var(--accent)] font-mono uppercase tracking-wider font-[Orbitron]">
              {formatTime(session.created_at)}
            </span>
            <span className="text-[10px] text-[var(--text-muted)] font-mono">
              {session.id.slice(0, 8)}
            </span>
            <span className="text-[10px] px-1.5 py-0.5 border border-[var(--border-color)] text-[var(--text-secondary)] font-mono rounded">
              {session.agent_type}
            </span>
          </div>
          <div className="flex items-center gap-3 text-[10px] font-mono text-[var(--text-muted)]">
            <span>
              {session.message_count} msg{session.message_count === 1 ? "" : "s"}
            </span>
            <span className="text-[var(--accent)]">→</span>
          </div>
        </div>
        {session.updated_at && session.updated_at !== session.created_at && (
          <div className="text-[9px] text-[var(--text-muted)] font-mono mt-1">
            last update: {formatTime(session.updated_at)}
          </div>
        )}
      </Link>
    </div>
  );
}

function formatTime(iso: string): string {
  if (!iso) return "(unknown)";
  try {
    const d = new Date(iso);
    if (isNaN(d.getTime())) return iso.slice(0, 19).replace("T", " ");
    const hh = String(d.getHours()).padStart(2, "0");
    const mm = String(d.getMinutes()).padStart(2, "0");
    const ss = String(d.getSeconds()).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    const mon = d.toLocaleString("en", { month: "short" });
    return `${day} ${mon} ${hh}:${mm}:${ss}`;
  } catch {
    return iso;
  }
}

function formatDateRange(start: string, end: string): string {
  try {
    const s = new Date(start);
    const e = new Date(end);
    if (s.toDateString() === e.toDateString()) {
      return s.toLocaleDateString("en", { day: "numeric", month: "short", year: "numeric" });
    }
    return `${s.toLocaleDateString("en", { day: "numeric", month: "short" })} → ${e.toLocaleDateString("en", { day: "numeric", month: "short" })}`;
  } catch {
    return "";
  }
}

import { useEffect, useState } from "react";
import { useParams } from "react-router";
import { toast } from "sonner";

import { HudCard } from "@/components/gundam/HudCard";
import { api, ApiError } from "@/lib/api";
import type { SessionListItem } from "@/types/api";

/** Project memory browser — shows real persisted sessions from disk. */
export function ProjectMemoryPage() {
  const { id } = useParams<{ id: string }>();
  const [sessions, setSessions] = useState<SessionListItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

  return (
    <div className="space-y-3">
      <HudCard>
        <h2 className="text-2xl font-[Orbitron] text-[var(--accent)] tracking-widest uppercase mb-2">
          Memory: {id}
        </h2>
        <p className="text-xs text-[var(--text-muted)] font-mono">
          {sessions.length === 0
            ? "No sessions yet"
            : `${sessions.length} session${sessions.length === 1 ? "" : "s"} on disk`}
        </p>
      </HudCard>

      {sessions.length === 0 ? (
        <HudCard>
          <p className="text-[var(--text-secondary)] text-sm">
            No conversations yet. Start a session from the{" "}
            <a href={`/projects/${id}`} className="text-[var(--accent)] underline">
              project page
            </a>
            .
          </p>
        </HudCard>
      ) : (
        sessions.map((s) => (
          <HudCard key={s.id} className="hover:gundam-pulse transition-shadow">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-sm font-mono text-[var(--accent)]">{s.id}</div>
                <div className="text-[10px] text-[var(--text-muted)] mt-1">
                  agent: {s.agent_type} · {s.message_count} message
                  {s.message_count === 1 ? "" : "s"}
                </div>
                <div className="text-[10px] text-[var(--text-muted)] font-mono mt-0.5">
                  created: {s.created_at || "(unknown)"}
                </div>
                {s.updated_at && s.updated_at !== s.created_at && (
                  <div className="text-[10px] text-[var(--text-muted)] font-mono">
                    updated: {s.updated_at}
                  </div>
                )}
              </div>
              <a
                href={`/projects/${id}?session=${s.id}`}
                className="px-2 py-1 text-xs border border-[var(--accent)] text-[var(--accent)] rounded hover:bg-[var(--accent)] hover:text-[var(--bg-primary)] transition-colors"
              >
                Resume
              </a>
            </div>
          </HudCard>
        ))
      )}
    </div>
  );
}

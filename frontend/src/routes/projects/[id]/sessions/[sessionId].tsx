import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router";
import { toast } from "sonner";

import { HudCard } from "@/components/gundam/HudCard";
import { Reticle } from "@/components/gundam/Reticle";
import { MessageBubble, type ChatMessage } from "@/components/gundam/MessageBubble";
import { StatusDot } from "@/components/gundam/StatusDot";
import { api, ApiError } from "@/lib/api";

/** Per-session detail page (B2).
 *
 *  Route: /projects/:id/sessions/:sessionId
 *
 *  Layout (top → bottom):
 *    1. Header — back link, session id, agent type, start time, status
 *    2. Metadata bar — message count, tool-call count, role breakdown
 *    3. Chat — full MessageBubble list (reuses A8 component)
 *    4. (Optional) error banner if loading failed
 *
 *  Replaces the old inline expansion in memory.tsx. By giving sessions
 *  their own URL, we get shareable deep-links, browser back/forward,
 *  and a much larger reading area — a real "mission log" feel.
 */
export function SessionDetailPage() {
  const { id, sessionId } = useParams<{ id: string; sessionId: string }>();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [projectName, setProjectName] = useState<string>("");
  const [rawMessageCount, setRawMessageCount] = useState<number>(0);
  const [createdAt, setCreatedAt] = useState<string>("");
  const [updatedAt, setUpdatedAt] = useState<string>("");
  const [agentType, setAgentType] = useState<string>("");

  useEffect(() => {
    if (!id || !sessionId) return;
    setLoading(true);
    setError(null);
    setMessages([]);

    Promise.all([api.getSessionMessages(id, sessionId), api.getProject(id)])
      .then(([sessionRes, projectRes]) => {
        setProjectName(sessionRes.project_name || projectRes.name);
        setRawMessageCount(sessionRes.message_count);
        const mapped = mapMessages(sessionRes.messages);
        setMessages(mapped);
        // Pull session-level metadata from project memory list (best effort)
        return api
          .listProjectMemory(id)
          .then((list) => {
            const meta = list.find((s) => s.id === sessionId);
            if (meta) {
              setAgentType(meta.agent_type);
              setCreatedAt(meta.created_at);
              setUpdatedAt(meta.updated_at);
            } else {
              // Fallback: derive from project last_activity
              setCreatedAt(projectRes.last_activity_at);
              setUpdatedAt(projectRes.last_activity_at);
            }
          })
          .catch(() => {
            /* non-fatal — header metadata is best-effort */
            setCreatedAt(projectRes.last_activity_at);
          });
      })
      .catch((e) => {
        const msg = e instanceof ApiError ? e.message : String(e);
        setError(msg);
        toast.error("Failed to load session", { description: msg });
      })
      .finally(() => setLoading(false));
  }, [id, sessionId]);

  // Aggregate stats from the normalized messages
  const stats = useMemo(() => {
    const toolCalls = messages.filter((m) => m.role === "tool").length;
    const user = messages.filter((m) => m.role === "user").length;
    const agent = messages.filter((m) => m.role === "agent").length;
    const system = messages.filter((m) => m.role === "system").length;
    // Distinct tool names used
    const toolNames = Array.from(
      new Set(
        messages
          .filter((m) => m.role === "agent" && m.tool_calls)
          .flatMap((m) => (m.tool_calls ?? []).map((t) => t.name)),
      ),
    );
    return { toolCalls, user, agent, system, toolNames };
  }, [messages]);

  if (loading) {
    return (
      <div className="space-y-3">
        <Header projectId={id ?? ""} sessionId={sessionId ?? ""} />
        <HudCard>
          <div className="flex items-center gap-3">
            <div className="gundam-radar w-8 h-8" />
            <p className="text-[var(--text-muted)] font-mono">
              Decrypting session transmission…
            </p>
          </div>
        </HudCard>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-3">
        <Header projectId={id ?? ""} sessionId={sessionId ?? ""} />
        <HudCard>
          <p className="text-[var(--danger)] font-mono text-sm">⚠ {error}</p>
        </HudCard>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full gap-3">
      <Header
        projectId={id ?? ""}
        sessionId={sessionId ?? ""}
        projectName={projectName}
        agentType={agentType}
        createdAt={createdAt}
        updatedAt={updatedAt}
      />

      {/* Metadata bar */}
      <HudCard>
        <div className="flex items-center justify-between flex-wrap gap-3 text-[11px] font-mono">
          <div className="flex items-center gap-4">
            <Stat label="MESSAGES" value={String(messages.length || rawMessageCount)} />
            <Stat label="USER" value={String(stats.user)} accent />
            <Stat label="AGENT" value={String(stats.agent)} accent />
            <Stat
              label="TOOL CALLS"
              value={String(stats.toolCalls)}
              accent={stats.toolCalls > 0}
            />
            {stats.system > 0 && <Stat label="SYSTEM" value={String(stats.system)} />}
          </div>
          <StatusDot
            status={messages.length === 0 ? "warn" : "ok"}
            label={messages.length === 0 ? "EMPTY" : "ARCHIVED"}
          />
        </div>
        {stats.toolNames.length > 0 && (
          <div className="mt-2 text-[10px] font-mono text-[var(--text-muted)]">
            <span className="opacity-60">tools: </span>
            {stats.toolNames.map((name, i) => (
              <span key={name}>
                <span className="text-[var(--accent)]">{name}</span>
                {i < stats.toolNames.length - 1 ? ", " : ""}
              </span>
            ))}
          </div>
        )}
      </HudCard>

      {/* Transcript */}
      <HudCard className="flex-1 overflow-y-auto">
        {messages.length === 0 ? (
          <Reticle>
            <h3 className="text-lg font-[Orbitron] text-[var(--accent)] tracking-widest uppercase mb-2">
              EMPTY TRANSMISSION
            </h3>
            <p className="text-sm text-[var(--text-secondary)]">
              This session has no recorded messages.
            </p>
          </Reticle>
        ) : (
          <div className="space-y-3">
            {messages.map((msg, i) => (
              <MessageBubble key={i} msg={msg} />
            ))}
          </div>
        )}
      </HudCard>
    </div>
  );
}

/** Convert backend wire format to our internal ChatMessage shape. */
function mapMessages(
  raw: Array<{
    role: "system" | "user" | "assistant" | "tool";
    content: string;
    tool_calls?: Array<{ id: string; name: string; arguments: Record<string, any> }>;
    name?: string;
  }>,
): ChatMessage[] {
  return raw.map((m) => {
    // Backend "assistant" maps to our "agent" role.
    // Backend "tool" can mean two things: a tool result message (name + content)
    // OR an assistant message that *made* a tool call. We collapse the latter
    // into an "agent" bubble with tool_calls attached, matching A8's contract.
    if (m.role === "assistant") {
      return {
        role: "agent" as const,
        text: m.content || "",
        ...(m.tool_calls && m.tool_calls.length > 0
          ? {
              tool_calls: m.tool_calls.map((tc) => ({
                id: tc.id,
                name: tc.name,
                args: tc.arguments ?? {},
              })),
            }
          : {}),
      };
    }
    if (m.role === "tool") {
      return {
        role: "tool" as const,
        text: m.content || "(no result)",
        ...(m.name ? { tool_name: m.name } : {}),
      };
    }
    return {
      role: m.role as "user" | "system",
      text: m.content || "",
    };
  });
}

function Stat({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent?: boolean;
}) {
  return (
    <div className="flex flex-col">
      <span className="text-[9px] text-[var(--text-muted)] uppercase tracking-widest">
        {label}
      </span>
      <span
        className={
          accent
            ? "text-sm font-[Orbitron] text-[var(--accent)]"
            : "text-sm font-[Orbitron] text-[var(--text-primary)]"
        }
      >
        {value}
      </span>
    </div>
  );
}

function Header({
  projectId,
  sessionId,
  projectName,
  agentType,
  createdAt,
  updatedAt,
}: {
  projectId: string;
  sessionId: string;
  projectName?: string;
  agentType?: string;
  createdAt?: string;
  updatedAt?: string;
}) {
  const started = createdAt ? formatDateTime(createdAt) : "—";
  const lastUpdate = updatedAt && updatedAt !== createdAt ? formatDateTime(updatedAt) : null;

  return (
    <HudCard>
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 text-[10px] font-mono text-[var(--text-muted)] uppercase tracking-widest mb-1">
            <Link
              to={`/projects/${projectId}/memory`}
              className="hover:text-[var(--accent)] transition-colors"
            >
              ← {projectName || projectId} / memory
            </Link>
          </div>
          <h2 className="text-xl font-[Orbitron] text-[var(--accent)] tracking-widest uppercase gundam-text-neon">
            Session {sessionId.slice(0, 12)}
          </h2>
          <p className="text-[10px] text-[var(--text-muted)] font-mono mt-1">
            {agentType && (
              <span className="px-1.5 py-0.5 border border-[var(--border-color)] rounded mr-2">
                {agentType}
              </span>
            )}
            <span>started {started}</span>
            {lastUpdate && <span> · updated {lastUpdate}</span>}
          </p>
        </div>
      </div>
    </HudCard>
  );
}

function formatDateTime(iso: string): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    if (isNaN(d.getTime())) return iso.slice(0, 19).replace("T", " ");
    const day = String(d.getDate()).padStart(2, "0");
    const mon = d.toLocaleString("en", { month: "short" });
    const hh = String(d.getHours()).padStart(2, "0");
    const mm = String(d.getMinutes()).padStart(2, "0");
    return `${day} ${mon} ${hh}:${mm}`;
  } catch {
    return iso;
  }
}

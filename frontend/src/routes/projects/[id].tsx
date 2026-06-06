import { useEffect, useState } from "react";
import { useParams } from "react-router";
import { toast } from "sonner";

import { HudCard } from "@/components/gundam/HudCard";
import { CommandInput } from "@/components/gundam/CommandInput";
import { StatusDot } from "@/components/gundam/StatusDot";
import { Reticle } from "@/components/gundam/Reticle";
import { ToolCallTraceList } from "@/components/gundam/ToolCallTraceList";
import { api, ApiError } from "@/lib/api";
import type { ProjectSummary } from "@/types/api";

interface ChatMessage {
  role: "user" | "agent" | "tool" | "system";
  text: string;
  tool_calls?: Array<{ id: string; name: string; args: Record<string, any> }>;
  tool_name?: string;
}

/** Project detail — the primary use of the dashboard.
 *  Center: chat / agent activity (largest).
 *  Live-wired: shows real messages from disk, tool call badges, "thinking" state.
 */
export function ProjectDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [project, setProject] = useState<ProjectSummary | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load project + history
  useEffect(() => {
    if (!id) return;
    api
      .getProject(id)
      .then(setProject)
      .catch((e) => {
        const msg = e instanceof ApiError ? e.message : String(e);
        setError(msg);
        toast.error("Failed to load project", { description: msg });
      });
  }, [id]);

  const ensureSession = async (): Promise<string | null> => {
    if (sessionId || !id) return sessionId;
    const session = await api.startSession({
      project_name: id,
      agent_type: project?.agent_type || "native_react",
    });
    setSessionId(session.id);
    return session.id;
  };

  const handleSend = async (text: string) => {
    if (!id) return;
    setMessages((m) => [...m, { role: "user", text }]);
    setBusy(true);
    setError(null);
    try {
      const sid = await ensureSession();
      if (!sid) {
        toast.error("Could not start session");
        return;
      }
      const res = await api.sendMessage(sid, { content: text });

      // Show user message + tool calls (if any in metadata) + agent response
      setMessages((m) => {
        const next: ChatMessage[] = [...m];
        if (res.tool_calls_made > 0) {
          next.push({
            role: "tool",
            text: `Used ${res.tool_calls_made} tool call${res.tool_calls_made === 1 ? "" : "s"}`,
            tool_name: "tools",
          });
        }
        next.push({ role: "agent", text: res.agent_response || "(no response)" });
        return next;
      });

      if (!res.success) {
        toast.warning("Agent returned an error", { description: res.error });
      } else {
        toast.success("Reply received", {
          description: `${res.agent_response.length} chars · ${res.tool_calls_made} tool calls`,
        });
      }
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : String(e);
      setError(msg);
      setMessages((m) => [...m, { role: "agent", text: `Error: ${msg}` }]);
      toast.error("Failed to send message", { description: msg });
    } finally {
      setBusy(false);
    }
  };

  if (error && !project) {
    return (
      <HudCard>
        <p className="text-[var(--danger)]">⚠ {error}</p>
      </HudCard>
    );
  }

  if (!project) {
    return (
      <HudCard>
        <div className="flex items-center gap-3">
          <div className="gundam-radar w-8 h-8" />
          <p className="text-[var(--text-muted)] font-mono">Loading project...</p>
        </div>
      </HudCard>
    );
  }

  return (
    <div className="flex flex-col h-full gap-3">
      {/* Project header */}
      <HudCard>
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-2xl font-[Orbitron] text-[var(--accent)] tracking-widest uppercase gundam-text-neon">
              {project.name}
            </h2>
            <p className="text-xs text-[var(--text-muted)] font-mono mt-1">
              agent: {project.agent_type} · status: {project.status}
              {sessionId && <span className="ml-2">· session: {sessionId.slice(0, 6)}…</span>}
            </p>
          </div>
          <StatusDot
            status={busy ? "warn" : sessionId ? "ok" : "warn"}
            label={busy ? "THINKING" : sessionId ? "READY" : "IDLE"}
          />
        </div>
      </HudCard>

      {/* Chat / agent output (center, primary focus) */}
      <HudCard className="flex-1 overflow-y-auto">
        {/* Live tool call traces (fly in from the right when agent invokes tools) */}
        <ToolCallTraceList sessionId={sessionId ?? undefined} />
        {messages.length === 0 ? (
          <Reticle>
            <h3 className="text-lg font-[Orbitron] text-[var(--accent)] tracking-widest uppercase mb-2">
              {busy ? "AGENT THINKING" : "READY"}
            </h3>
            <p className="text-sm text-[var(--text-secondary)]">
              {busy ? (
                <span className="inline-block gundam-radar w-4 h-4 align-middle mr-2" />
              ) : null}
              {busy ? "…" : "Send a message to begin"}
            </p>
          </Reticle>
        ) : (
          <div className="space-y-3">
            {messages.map((msg, i) => (
              <MessageBubble key={i} msg={msg} />
            ))}
            {busy && (
              <div className="flex items-center gap-2 px-3 py-2 text-[var(--text-muted)] text-xs">
                <div className="gundam-radar w-4 h-4" />
                <span>Agent thinking…</span>
              </div>
            )}
          </div>
        )}
      </HudCard>

      {/* Command input (sticky bottom) */}
      <CommandInput
        onSubmit={handleSend}
        placeholder="Tell the agent what to do..."
        disabled={busy}
      />
    </div>
  );
}

function MessageBubble({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === "user";
  const isTool = msg.role === "tool";
  return (
    <div
      className={`p-3 rounded border ${
        isUser
          ? "border-[var(--accent)] bg-[var(--bg-elevated)]"
          : isTool
          ? "border-[var(--border-color)] border-dashed bg-[var(--bg-input)]/50"
          : "border-[var(--border-color)] bg-[var(--bg-card)]"
      }`}
    >
      <div className="flex items-center gap-2 mb-1">
        <span className="text-[10px] text-[var(--text-muted)] uppercase tracking-widest font-[Rajdhani]">
          {msg.role === "user" ? "YOU" : msg.role === "agent" ? "AGENT" : msg.role === "tool" ? "TOOL" : "SYSTEM"}
        </span>
        {isTool && msg.tool_name && (
          <span className="text-[10px] text-[var(--accent)] font-mono">🔧 {msg.tool_name}</span>
        )}
      </div>
      <pre className="text-sm text-[var(--text-primary)] whitespace-pre-wrap font-mono m-0">
        {msg.text}
      </pre>
    </div>
  );
}

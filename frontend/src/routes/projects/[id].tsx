import { useEffect, useState } from "react";
import { useParams } from "react-router";
import { HudCard } from "@/components/gundam/HudCard";
import { CommandInput } from "@/components/gundam/CommandInput";
import { StatusDot } from "@/components/gundam/StatusDot";
import { Reticle } from "@/components/gundam/Reticle";
import { api } from "@/lib/api";
import type { ProjectSummary } from "@/types/api";

/** Project detail — the primary use of the dashboard.
 *  Center: chat / agent activity (largest). */
export function ProjectDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [project, setProject] = useState<ProjectSummary | null>(null);
  const [messages, setMessages] = useState<{ role: "user" | "agent"; text: string }[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    api.getProject(id).then(setProject).catch((e) => setError(e.message));
  }, [id]);

  const ensureSession = async () => {
    if (sessionId || !id) return sessionId;
    const session = await api.startSession({ project_name: id, agent_type: project?.agent_type || "native_react" });
    setSessionId(session.id);
    return session.id;
  };

  const handleSend = async (text: string) => {
    if (!id) return;
    setMessages((m) => [...m, { role: "user", text }]);
    setBusy(true);
    try {
      const sid = await ensureSession();
      if (!sid) return;
      const res = await api.sendMessage(sid, { content: text });
      setMessages((m) => [
        ...m,
        { role: "agent", text: res.agent_response || "[no response]" },
      ]);
    } catch (e) {
      setMessages((m) => [...m, { role: "agent", text: `Error: ${(e as Error).message}` }]);
    } finally {
      setBusy(false);
    }
  };

  if (error) {
    return (
      <HudCard>
        <p className="text-[var(--danger)]">⚠ {error}</p>
      </HudCard>
    );
  }

  if (!project) {
    return (
      <HudCard>
        <p className="text-[var(--text-muted)] font-mono">Loading project...</p>
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
            </p>
          </div>
          <StatusDot
            status={sessionId ? "ok" : "warn"}
            label={sessionId ? "ACTIVE" : "IDLE"}
          />
        </div>
      </HudCard>

      {/* Chat / agent output (center, primary focus) */}
      <HudCard className="flex-1 overflow-y-auto">
        {messages.length === 0 ? (
          <Reticle>
            <h3 className="text-lg font-[Orbitron] text-[var(--accent)] tracking-widest uppercase mb-2">
              READY
            </h3>
            <p className="text-sm text-[var(--text-secondary)]">
              Send a message to begin
            </p>
          </Reticle>
        ) : (
          <div className="space-y-3">
            {messages.map((msg, i) => (
              <div
                key={i}
                className={`p-3 rounded border ${
                  msg.role === "user"
                    ? "border-[var(--accent)] bg-[var(--bg-elevated)]"
                    : "border-[var(--border-color)] bg-[var(--bg-card)]"
                }`}
              >
                <div className="text-[10px] text-[var(--text-muted)] uppercase tracking-widest font-[Rajdhani] mb-1">
                  {msg.role === "user" ? "USER" : "AGENT"}
                </div>
                <pre className="text-sm text-[var(--text-primary)] whitespace-pre-wrap font-mono">
                  {msg.text}
                </pre>
              </div>
            ))}
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

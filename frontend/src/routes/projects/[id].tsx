import { useEffect, useState } from "react";
import { useParams } from "react-router";
import { toast } from "sonner";

import { HudCard } from "@/components/gundam/HudCard";
import { CommandInput } from "@/components/gundam/CommandInput";
import { MessageBubble, type ChatMessage } from "@/components/gundam/MessageBubble";
import { StatusDot } from "@/components/gundam/StatusDot";
import { Reticle } from "@/components/gundam/Reticle";
import { ToolCallTraceList } from "@/components/gundam/ToolCallTraceList";
import { api, ApiError } from "@/lib/api";
import { mapMessages } from "@/lib/message-mapper";
import type { ProjectSummary } from "@/types/api";

/** Project detail — the primary use of the dashboard.
 *  Center: chat / agent activity (largest).
 *  Live-wired: shows real messages from disk, tool call badges, "thinking" state.
 *
 *  A5 (this revision):
 *   - Optimistic send: user message is pushed into local state with
 *     `pending: true` BEFORE the network call. On success, the agent
 *     response bubbles replace the pending flag; on failure, the user
 *     bubble is marked `error: true` and a toast surfaces the cause.
 *   - Reload safety: when a `sessionId` is already known (e.g. from a
 *     deep link, page refresh, or navigation back from a sub-page),
 *     we call `api.getSessionHistory(sessionId)` on mount and hydrate
 *     the local message list. Without this, a refresh mid-conversation
 *     would erase the chat history.
 *   - The `sessionId` is read from `?session=…` on the URL — passing
 *     it explicitly avoids "lost context" when the user comes back.
 */
export function ProjectDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [project, setProject] = useState<ProjectSummary | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load project on mount
  useEffect(() => {
    if (!id) return;
    setError(null);
    api
      .getProject(id)
      .then(setProject)
      .catch((e) => {
        const msg = e instanceof ApiError ? e.message : String(e);
        setError(msg);
        toast.error("Failed to load project", { description: msg });
      });
  }, [id]);

  // A5 — on mount, read `?session=…` from the URL (if present) and
  // hydrate the local message list. Runs only once per `id` change.
  useEffect(() => {
    if (!id) return;
    const params = new URLSearchParams(window.location.search);
    const fromUrl = params.get("session");
    if (fromUrl) {
      setSessionId(fromUrl);
      api
        .getSessionHistory(fromUrl)
        .then((res) => {
          if (res.messages.length > 0) {
            setMessages(mapMessages(res.messages));
            toast.success("Session resumed", {
              description: `${res.message_count} messages reloaded`,
            });
          }
        })
        .catch((e) => {
          const msg = e instanceof ApiError ? e.message : String(e);
          // Don't toast — 404 is normal for a stale URL. Just log.
          console.warn("Session resume failed:", msg);
        });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const ensureSession = async (): Promise<string | null> => {
    if (sessionId || !id) return sessionId;
    const session = await api.startSession({
      project_name: id,
      agent_type: project?.agent_type || "native_react",
    });
    setSessionId(session.id);
    // Reflect into the URL so a refresh / deep-link keeps the session
    const url = new URL(window.location.href);
    url.searchParams.set("session", session.id);
    window.history.replaceState(null, "", url.toString());
    return session.id;
  };

  const handleSend = async (text: string) => {
    if (!id) return;

    // A5 — optimistic insert: push the user message immediately with
    // pending=true. The MessageBubble will render with a pulsing accent
    // border and a "● pending" badge. This makes the click-to-display
    // latency feel ~0.
    const optimisticUser: ChatMessage = {
      role: "user",
      text,
      pending: true,
    };
    setMessages((m) => [...m, optimisticUser]);
    setBusy(true);
    setError(null);

    try {
      const sid = await ensureSession();
      if (!sid) {
        toast.error("Could not start session");
        markMessageError(text);
        return;
      }
      const res = await api.sendMessage(sid, { content: text });

      // Replace the optimistic user bubble with the confirmed one,
      // and append tool-call summary + agent response (A8 contract).
      setMessages((m) => {
        const next: ChatMessage[] = m.map((msg) =>
          msg === optimisticUser || (msg.pending && msg.text === text)
            ? { role: "user", text }
            : msg,
        );
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
      markMessageError(text);
      toast.error("Failed to send message", { description: msg });
    } finally {
      setBusy(false);
    }
  };

  /** Mark a pending user message as errored (✕ failed).
   *  Finds the LAST pending message in the list and flips it.
   *  The user-typed text uniquely identifies the optimistic bubble
   *  we just pushed (since we only allow one in-flight send at a
   *  time — `busy` guards the input).
   */
  const markMessageError = (text: string) => {
    setMessages((m) => {
      const next = [...m];
      for (let i = next.length - 1; i >= 0; i--) {
        if (next[i].pending && next[i].text === text) {
          next[i] = { ...next[i], pending: undefined, error: true };
          break;
        }
      }
      return next;
    });
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

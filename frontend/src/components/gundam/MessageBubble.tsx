/** ChatMessage — frontend UI shape for a single message in a conversation.
 *
 * Distinct from `SessionMessagesResponse.messages` (the backend
 * wire format) — this is the normalized shape the dashboard uses
 * internally. Mapping happens in `api.*` (e.g. ws stream parser).
 *
 * Why a separate type:
 * - `text` instead of `content` (UI doesn't care about OpenAI-style
 *   "content blocks" — just want a string to render)
 * - `role: "agent"` (our brand) instead of `"assistant"`
 * - `args: Record<string, any>` (display-only) instead of
 *   `arguments` (server-canonical)
 *
 * A5 additions (frontend-only — never sent to backend):
 * - `pending?: true` — message pushed optimistically, awaiting
 *   the server response. Renders with a pulsing dot + "…" suffix.
 * - `error?: true` — server rejected the message (4xx/5xx/network).
 *   Renders with a red ✕ and the text turns muted.
 */
export interface ChatMessage {
  role: "user" | "agent" | "tool" | "system";
  text: string;
  tool_calls?: Array<{ id: string; name: string; args: Record<string, any> }>;
  tool_name?: string;
  pending?: true;
  error?: true;
}

/** Single message bubble — user / agent / tool / system. */
export function MessageBubble({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === "user";
  const isTool = msg.role === "tool";

  // Border / opacity tweaks for pending + error states
  const stateClasses = msg.error
    ? "border-[var(--danger)] opacity-70"
    : msg.pending
    ? "border-[var(--accent)] opacity-60 gundam-pulse"
    : isUser
    ? "border-[var(--accent)] bg-[var(--bg-elevated)]"
    : isTool
    ? "border-[var(--border-color)] border-dashed bg-[var(--bg-input)]/50"
    : "border-[var(--border-color)] bg-[var(--bg-card)]";

  return (
    <div className={`p-3 rounded border ${stateClasses}`}>
      <div className="flex items-center gap-2 mb-1">
        <span className="text-[10px] text-[var(--text-muted)] uppercase tracking-widest font-[Rajdhani]">
          {msg.role === "user"
            ? "YOU"
            : msg.role === "agent"
            ? "AGENT"
            : msg.role === "tool"
            ? "TOOL"
            : "SYSTEM"}
        </span>
        {isTool && msg.tool_name && (
          <span className="text-[10px] text-[var(--accent)] font-mono">
            🔧 {msg.tool_name}
          </span>
        )}
        {msg.pending && (
          <span
            className="text-[10px] text-[var(--accent)] font-mono"
            title="Awaiting server response"
          >
            ● pending
          </span>
        )}
        {msg.error && (
          <span
            className="text-[10px] text-[var(--danger)] font-mono"
            title="Send failed"
          >
            ✕ failed
          </span>
        )}
      </div>
      <pre className="text-sm text-[var(--text-primary)] whitespace-pre-wrap font-mono m-0">
        {msg.text}
      </pre>
    </div>
  );
}

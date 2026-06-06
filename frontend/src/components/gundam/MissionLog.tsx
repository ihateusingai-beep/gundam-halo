import { useEffect, useRef, useState } from "react";

import { subscribe, type WsEvent, type WsEventType } from "@/lib/ws";

interface MissionLogEntry extends WsEvent {
  id: string; // unique key for React
}

interface MissionLogProps {
  className?: string;
  /** Max entries to keep. Default 50. */
  maxEntries?: number;
  /** Event types to hide (e.g. noisy periodic ones). */
  hiddenTypes?: WsEventType[];
}

/** Terminal-style scrolling log of live WS events.
 *
 *  Format per line: `[HH:MM:SS] ▸ event_type · key=value ...`
 *  Color: cyan by default, danger red for errors/alerts, success green for ok.
 *
 *  Sits in the cockpit's left column under "Projects" — replaces the
 *  ticker with a vertical feed so the pilot can scan recent activity
 *  at a glance.
 */
export function MissionLog({
  className = "",
  maxEntries = 50,
  hiddenTypes = ["system_gauges", "system_hello"],
}: MissionLogProps) {
  const [entries, setEntries] = useState<MissionLogEntry[]>([]);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const unsub = subscribe((e) => {
      if (hiddenTypes.includes(e.type)) return;
      const entry: MissionLogEntry = { ...e, id: `${e.ts}-${Math.random().toString(36).slice(2, 8)}` };
      setEntries((prev) => {
        const next = [entry, ...prev];
        return next.slice(0, maxEntries);
      });
    });
    return unsub;
  }, [maxEntries, hiddenTypes]);

  // Auto-scroll to top when new entries arrive
  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = 0;
    }
  }, [entries.length]);

  return (
    <div
      ref={containerRef}
      className={`font-mono text-[10px] space-y-px overflow-y-auto max-h-64 pr-1 ${className}`}
    >
      {entries.length === 0 && (
        <div className="text-[var(--text-muted)] italic">// awaiting events…</div>
      )}
      {entries.map((e) => (
        <MissionLogLine key={e.id} entry={e} />
      ))}
    </div>
  );
}

function MissionLogLine({ entry }: { entry: MissionLogEntry }) {
  const color = colorForEvent(entry);
  const time = new Date(entry.ts * 1000).toLocaleTimeString("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
  const summary = formatData(entry.type, entry.data);

  return (
    <div className="flex gap-1 leading-tight" style={{ color }}>
      <span className="opacity-60 shrink-0">{time}</span>
      <span className="shrink-0">▸</span>
      <span className="shrink-0 uppercase tracking-wider font-bold">{entry.type}</span>
      {summary && <span className="opacity-80 truncate">{summary}</span>}
    </div>
  );
}

function colorForEvent(e: WsEvent): string {
  // Severity-tinted coloring
  if (e.type === "security_alert" || e.type === "security_block") {
    const sev = (e.data as any)?.severity;
    return sev === "critical" || sev === "high" ? "var(--danger)" : "var(--warning)";
  }
  if (e.type === "mac_op_blocked" || e.type === "system_error") return "var(--danger)";
  if (e.type === "tool_call_end" && (e.data as any)?.ok === false) return "var(--danger)";
  if (e.type === "agent_turn_end" && (e.data as any)?.success === false) return "var(--danger)";
  if (e.type === "tool_call_end" || e.type === "agent_turn_end") return "var(--success)";
  if (e.type === "agent_turn_start" || e.type === "tool_call_start") return "var(--accent)";
  return "var(--text-secondary)";
}

function formatData(type: WsEventType, data: any): string {
  if (!data) return "";
  switch (type) {
    case "agent_turn_start":
    case "agent_turn_end":
      return data.session_id ? `session=${String(data.session_id).slice(0, 8)}` : "";
    case "tool_call_start":
      return `${data.tool ?? ""} ${data.call_id ? `id=${String(data.call_id).slice(0, 8)}` : ""}`;
    case "tool_call_end":
      return `${data.tool ?? ""} ${data.ok ? "ok" : "FAIL"} ${data.duration_ms ?? 0}ms`;
    case "session_start":
    case "session_end":
      return data.session_id ? `session=${String(data.session_id).slice(0, 8)}` : "";
    case "session_message_received":
      return data.session_id ? `session=${String(data.session_id).slice(0, 8)}` : "";
    case "mac_op_audit":
      return data.action || "";
    case "mac_op_blocked":
      return `${data.action ?? ""} ${data.reason ?? ""}`.trim();
    case "security_alert":
    case "security_block":
      return `${data.severity ?? ""} ${data.rule ?? ""}`.trim();
    case "channel_message_received":
    case "channel_message_sent":
      return data.channel || "";
    case "project_created":
    case "project_archived":
      return data.name || "";
    case "system_error":
      return data.message || data.error || "";
    default:
      return "";
  }
}

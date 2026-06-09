import { useEffect, useState } from "react";

import {
  getEmotionDisplay,
  getPhaseIcon,
} from "@/lib/emotion-display";
import { subscribe, type WsEvent } from "@/lib/ws";

interface ActivityTickerProps {
  className?: string;
  /** Max number of recent events to keep. */
  maxEvents?: number;
}

/** Activity ticker — shows the most recent WS events in a compact strip.
 *  Useful for debugging and giving the cockpit a "live data" feel.
 *
 *  Format: [icon] [event_type] · [key info] @ [time]
 */
export function ActivityTicker({ className = "", maxEvents = 5 }: ActivityTickerProps) {
  const [events, setEvents] = useState<WsEvent[]>([]);

  useEffect(() => {
    const unsub = subscribe((e) => {
      // Filter out the high-frequency system_gauges — too noisy
      if (e.type === "system_gauges" || e.type === "system_hello") return;
      setEvents((prev) => {
        const next = [e, ...prev];
        return next.slice(0, maxEvents);
      });
    });
    return unsub;
  }, [maxEvents]);

  if (events.length === 0) {
    return (
      <span className={`text-[var(--text-muted)] font-mono ${className}`}>
        // awaiting events…
      </span>
    );
  }

  return (
    <div className={`flex items-center gap-3 overflow-x-auto ${className}`}>
      {events.map((e, i) => (
        <EventChip key={`${e.ts}-${i}`} event={e} />
      ))}
    </div>
  );
}

function EventChip({ event }: { event: WsEvent }) {
  const { icon, color, summary } = formatEvent(event);
  return (
    <span
      className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded border font-mono whitespace-nowrap"
      style={{ borderColor: color, color }}
      title={`${event.type} @ ${new Date(event.ts * 1000).toLocaleTimeString()}`}
    >
      <span>{icon}</span>
      <span className="text-[10px] uppercase tracking-wider">{event.type}</span>
      {summary && <span className="text-[10px] opacity-70">{summary}</span>}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Emotion → icon + color is now in `@/lib/emotion-display` so it can be
// shared with other components (tool trace tooltips, future HUD overlays)
// and unit-tested in isolation.
// ---------------------------------------------------------------------------

function formatEvent(event: WsEvent): {
  icon: string;
  color: string;
  summary: string;
} {
  const data = event.data || {};

  switch (event.type) {
    case "agent_turn_start":
      return {
        icon: "🤖",
        color: "var(--accent)",
        summary: data.session_id ? data.session_id.slice(0, 6) : "",
      };
    case "agent_turn_end":
      return { icon: "✓", color: "var(--success)", summary: "" };
    case "tool_call_start":
      return {
        icon: "🔧",
        color: "var(--accent)",
        summary: data.tool ? `${data.tool}` : "",
      };
    case "tool_call_end":
      return {
        icon: "⚙",
        color: "var(--text-muted)",
        summary: data.tool ? `${data.tool} ${data.ok ? "ok" : "fail"}` : "",
      };
    case "live2d_tool_trigger": {
      // The avatar reacted to a tool call. Display the emotion + tool +
      // phase so the user can read "agent is doing X with feeling Y".
      const emotion = data.emotion as string | undefined;
      const phase = data.phase as string | undefined;
      const tool = (data.tool as string) || "?";
      const display = getEmotionDisplay(emotion);
      const phaseGlyph = getPhaseIcon(phase);
      return {
        icon: display.icon,
        color: display.color,
        summary: `${phaseGlyph} ${tool} · ${display.label}`,
      };
    }
    case "backend_log": {
      // M7-Phase-0: render backend log lines as slim chips. Trim the
      // logger name to the trailing 16 chars to keep the chip short.
      const level = (data.level as string) || "INFO";
      const msg = (data.msg as string) || "";
      const logger = (data.logger as string) || "app";
      const short = logger.length > 16 ? logger.slice(-16) : logger;
      const color =
        level === "ERROR" || level === "CRITICAL"
          ? "var(--danger)"
          : level === "WARNING"
          ? "var(--warning)"
          : "var(--text-muted)";
      return {
        icon: "·",
        color,
        summary: `[${level}] ${short}: ${msg.length > 60 ? msg.slice(0, 57) + "..." : msg}`,
      };
    }
    case "session_start":
      return {
        icon: "▶",
        color: "var(--success)",
        summary: data.project || data.session_id?.slice(0, 6) || "",
      };
    case "session_end":
      return { icon: "■", color: "var(--text-muted)", summary: "" };
    case "session_message_received":
      return { icon: "💬", color: "var(--accent)", summary: "" };
    case "mac_op_audit":
      return {
        icon: "🛡",
        color: "var(--text-secondary)",
        summary: data.action || "",
      };
    case "mac_op_blocked":
      return {
        icon: "🚫",
        color: "var(--danger)",
        summary: data.reason || data.action || "",
      };
    case "security_alert":
    case "security_block":
      return {
        icon: "⚠",
        color: "var(--danger)",
        summary: data.rule || "",
      };
    case "system_error":
      return {
        icon: "✗",
        color: "var(--danger)",
        summary: data.message || "",
      };
    case "channel_message_received":
      return {
        icon: "📡",
        color: "var(--accent)",
        summary: data.channel || "",
      };
    case "channel_message_sent":
      return {
        icon: "📤",
        color: "var(--success)",
        summary: data.channel || "",
      };
    case "project_created":
      return { icon: "+", color: "var(--success)", summary: data.name || "" };
    default:
      return { icon: "·", color: "var(--text-muted)", summary: "" };
  }
}

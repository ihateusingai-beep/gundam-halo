import { useEffect, useState } from "react";

import { subscribeTo, type WsEvent, type WsToolCallData } from "@/lib/ws";

interface ToolCallTraceProps {
  callId: string;
  tool: string;
  args?: Record<string, any>;
}

/** A single tool call trace — animates in from the right and collapses on end.
 *
 *  Visual stages:
 *    1. Entering: opacity 0 → 1, translateX(60vw) → 0 (250ms)
 *    2. Running:  spinning ring + "EXECUTING" label
 *    3. Done:     ring stops, label switches to "COMPLETE" / "ERROR", duration shown
 *    4. Aging:    stays for 1.5s then collapses to a one-line summary (height → 0)
 */
export function ToolCallTrace({ callId, tool, args }: ToolCallTraceProps) {
  const [status, setStatus] = useState<"running" | "ok" | "error">("running");
  const [durationMs, setDurationMs] = useState<number | null>(null);
  const [resultPreview, setResultPreview] = useState<string | null>(null);
  const [collapsed, setCollapsed] = useState(false);

  // Subscribe to TOOL_CALL_END for this specific call_id
  useEffect(() => {
    const unsub = subscribeTo("tool_call_end", (e: WsEvent) => {
      const data = e.data as WsToolCallData;
      if (data.call_id !== callId) return;
      setStatus(data.ok ? "ok" : "error");
      setDurationMs(data.duration_ms ?? null);
      setResultPreview(data.result_preview ?? null);
      // Schedule collapse 1.5s after completion
      setTimeout(() => setCollapsed(true), 1500);
    });
    return unsub;
  }, [callId]);

  const accent =
    status === "running"
      ? "var(--accent)"
      : status === "ok"
      ? "var(--success)"
      : "var(--danger)";

  const argsStr = args
    ? Object.entries(args)
        .slice(0, 3)
        .map(([k, v]) => `${k}=${truncate(String(v), 20)}`)
        .join(" ")
    : "";

  return (
    <div
      className={`gundam-holo-panel tool-trace ${collapsed ? "tool-trace-collapsed" : ""}`}
      style={{
        borderColor: accent,
        boxShadow: `0 0 12px ${accent}`,
        transition: "all 0.3s ease",
      }}
    >
      <div className="flex items-center gap-2">
        {/* Spinner / status ring */}
        <div
          className={`w-3 h-3 rounded-full border-2 ${
            status === "running" ? "tool-trace-spinner" : ""
          }`}
          style={{
            borderColor: accent,
            borderTopColor: status === "running" ? "transparent" : accent,
            background: status === "ok" ? accent : status === "error" ? accent : "transparent",
            boxShadow: `0 0 6px ${accent}`,
          }}
        />
        <span
          className="text-[10px] font-[Orbitron] uppercase tracking-widest"
          style={{ color: accent }}
        >
          {status === "running" ? "EXECUTING" : status === "ok" ? "COMPLETE" : "ERROR"}
        </span>
        <span className="text-[var(--text-muted)] text-[10px]">·</span>
        <span className="text-[10px] font-mono" style={{ color: accent }}>
          {tool}
        </span>
        {durationMs !== null && (
          <span className="text-[10px] font-mono text-[var(--text-muted)] ml-auto">
            {durationMs}ms
          </span>
        )}
      </div>
      {argsStr && !collapsed && (
        <div className="text-[10px] font-mono text-[var(--text-secondary)] mt-1 truncate">
          {argsStr}
        </div>
      )}
      {resultPreview && !collapsed && status !== "running" && (
        <div className="text-[10px] font-mono text-[var(--text-muted)] mt-1 truncate">
          → {resultPreview}
        </div>
      )}
    </div>
  );
}

function truncate(s: string, n: number): string {
  if (s.length <= n) return s;
  return s.slice(0, n - 1) + "…";
}

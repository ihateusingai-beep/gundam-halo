import { useEffect, useState } from "react";

import { subscribeTo, type WsEvent, type WsToolCallData } from "@/lib/ws";
import { ToolCallTrace } from "./ToolCallTrace";

interface InFlightCall {
  call_id: string;
  tool: string;
  args?: Record<string, any>;
  startedAt: number;
}

interface ToolCallTraceListProps {
  /** Optional filter: only show calls for this session_id. */
  sessionId?: string;
  className?: string;
}

/** Live list of in-flight tool call traces.
 *
 *  Subscribes to tool_call_start / tool_call_end on the WS, displays
 *  each tool call as a fly-in holographic panel via <ToolCallTrace />.
 *
 *  Useful for debugging agent activity and giving the cockpit a "live
 *  data" feel — you can see exactly which tools the agent is invoking
 *  in real time.
 */
export function ToolCallTraceList({ sessionId, className = "" }: ToolCallTraceListProps) {
  const [calls, setCalls] = useState<InFlightCall[]>([]);

  useEffect(() => {
    const unsubStart = subscribeTo("tool_call_start", (e: WsEvent) => {
      const data = e.data as WsToolCallData;
      if (sessionId && data.session_id !== sessionId) return;
      setCalls((prev) => {
        // De-dup: if same call_id arrives twice, update instead of append
        const existing = prev.find((c) => c.call_id === data.call_id);
        if (existing) return prev;
        return [
          ...prev,
          {
            call_id: data.call_id,
            tool: data.tool,
            args: data.args,
            startedAt: e.ts,
          },
        ];
      });
    });

    // Listen for end to remove from list after the trace's own collapse
    const unsubEnd = subscribeTo("tool_call_end", (e: WsEvent) => {
      const data = e.data as WsToolCallData;
      // The ToolCallTrace itself schedules its own collapse; we just clean
      // the entry from our list 3s after the end event (after collapse)
      setTimeout(() => {
        setCalls((prev) => prev.filter((c) => c.call_id !== data.call_id));
      }, 3000);
    });

    return () => {
      unsubStart();
      unsubEnd();
    };
  }, [sessionId]);

  if (calls.length === 0) {
    return null;
  }

  return (
    <div className={`space-y-2 tool-trace-list ${className}`}>
      {calls.map((c) => (
        <ToolCallTrace
          key={c.call_id}
          callId={c.call_id}
          tool={c.tool}
          args={c.args}
        />
      ))}
    </div>
  );
}

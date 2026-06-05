import { useWsStatus } from "@/lib/ws";

interface ConnectionStatusProps {
  className?: string;
}

/** Connection indicator — small green/yellow/red dot + label.
 *  Used in the cockpit footer to show live WebSocket status.
 */
export function ConnectionStatus({ className = "" }: ConnectionStatusProps) {
  const { connected, reconnectAttempts } = useWsStatus();

  const color = connected
    ? "var(--success)"
    : reconnectAttempts > 0
    ? "var(--warning)"
    : "var(--danger)";

  const label = connected
    ? "WS LINKED"
    : reconnectAttempts > 0
    ? `WS RECONNECT (${reconnectAttempts})`
    : "WS OFFLINE";

  return (
    <span
      className={`inline-flex items-center gap-1.5 font-mono ${className}`}
      title={
        connected
          ? "WebSocket connected to backend"
          : "WebSocket disconnected — retrying with backoff"
      }
    >
      <span
        className="inline-block w-1.5 h-1.5 rounded-full"
        style={{
          background: color,
          boxShadow: connected ? `0 0 6px ${color}` : "none",
          animation: connected
            ? "gundam-pulse-dot 1.5s ease-in-out infinite"
            : "none",
        }}
      />
      <span style={{ color }}>{label}</span>
    </span>
  );
}

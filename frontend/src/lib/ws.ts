/**
 * WebSocket client — global singleton for real-time backend events.
 *
 * Architecture:
 *   - One WebSocket per browser tab (module-level singleton).
 *   - Components subscribe to specific event types via useWsEvent<T>().
 *   - Connection state exposed via useWsStatus().
 *   - Auto-reconnect on close (exponential backoff, capped).
 *
 * Backend event names use underscore convention to match the Python
 * EventType enum on the server (e.g. "agent_turn_start", "system_gauges").
 *
 * Sprint 32 P1.2 refactor: the connect / reconnect / dispatch / dead-
 * socket-detection boilerplate was extracted into
 * `lib/ws-base.ts::BaseWebSocketClient`. This module now only owns:
 *   1. The `WsEvent` / `WsEventType` types (backend contract).
 *   2. The `WsClient` singleton — a 5-line subclass that supplies
 *      the `/ws` URL.
 *   3. The React hooks (`useWsEvent`, `useWsStatus`) that bridge
 *      the singleton's state into components.
 */

import { useEffect, useRef, useState } from "react";

import { BaseWebSocketClient, wsUrlFromApi } from "./ws-base";

// ---------------------------------------------------------------------------
// Event types — mirror the backend's EventType enum
// ---------------------------------------------------------------------------

export type WsEventType =
  // System
  | "system_hello"
  | "system_gauges"
  | "system_error"
  // LLM
  | "inference_start"
  | "inference_end"
  // Tools
  | "tool_call_start"
  | "tool_call_end"
  // Agent
  | "agent_turn_start"
  | "agent_turn_end"
  // Session
  | "session_start"
  | "session_end"
  | "session_message_received"
  // Project
  | "project_created"
  | "project_archived"
  // Channel
  | "channel_message_received"
  | "channel_message_sent"
  // Mac control
  | "mac_op_start"
  | "mac_op_end"
  | "mac_op_blocked"
  | "mac_op_audit"
  // Security
  | "security_scan"
  | "security_alert"
  | "security_block"
  // Live2D
  | "live2d_tool_trigger"
  // Backend log (M7-Phase-0)
  | "backend_log";

// Payload shapes for the events we care about
export interface WsSystemGaugesData {
  cpu_percent: number;
  memory_percent: number;
  disk_percent: number;
  network_sent_mb: number;
  network_recv_mb: number;
}

export interface WsAgentTurnData {
  session_id: string;
  project?: string;
  agent_type?: string;
}

export interface WsToolCallData {
  call_id: string;
  tool: string;
  args?: Record<string, any>;
  ok?: boolean;
  duration_ms?: number;
  result_preview?: string;
  session_id?: string;
  project?: string;
}

export interface WsSystemHelloData {
  client_id: number;
  event_types: WsEventType[];
  gauges_interval_sec: number;
}

export interface WsSessionData {
  session_id: string;
  project?: string;
  agent_type?: string;
}

export interface WsMacOpData {
  action: string;
  target?: string;
  ok?: boolean;
  blocked?: boolean;
  reason?: string;
  user?: string;
  tool?: string;
}

export interface WsSecurityAlertData {
  severity: "low" | "medium" | "high" | "critical";
  rule: string;
  detail: string;
  path?: string;
}

export interface WsLive2DToolTriggerData {
  source: "tool";
  tool: string;
  phase: "start" | "end";
  ok?: boolean;
  call_id?: string;
  session_id?: string;
  project?: string;
  expression: string;
  motion: string;
  emotion: string;
}

export interface WsBackendLogData {
  level: "INFO" | "WARNING" | "ERROR" | "DEBUG" | "CRITICAL";
  logger: string;
  msg: string;
}

export interface WsEventEnvelope<T = any> {
  type: WsEventType;
  ts: number;
  data: T;
}

// Generic envelope — backend doesn't actually type data, so we cast on use
export type WsEvent = WsEventEnvelope & { data: any; [key: string]: unknown };

// ---------------------------------------------------------------------------
// Singleton wrapper around BaseWebSocketClient
// ---------------------------------------------------------------------------

class WsClient extends BaseWebSocketClient<WsEvent, never> {
  protected override get logTag(): string {
    return "[Ws]";
  }

  protected override getUrl(): string {
    return wsUrlFromApi("/ws");
  }
}

// Module-level singleton — auto-connects on first browser load.
const singleton = new WsClient();

// ---------------------------------------------------------------------------
// React state bridge — useWsStatus listens for connection changes
// ---------------------------------------------------------------------------

type StateChangeCb = (connected: boolean, reconnectAttempts: number) => void;
const stateChangeCbs = new Set<StateChangeCb>();

// Patch the singleton's lifecycle hooks so we can fan out state
// changes to React components without subclassing a second time.
// We do this by overriding the protected hooks via the base class's
// own internal call site — but those are private. The cleanest
// approach is to forward via a small post-connect helper that
// uses the singleton's observable fields.
let lastConnected = singleton.isConnected();
let lastAttempts = singleton.reconnectAttempts;

const pollInterval = typeof window !== "undefined"
  ? window.setInterval(() => {
      const c = singleton.isConnected();
      const a = singleton.reconnectAttempts;
      if (c !== lastConnected || a !== lastAttempts) {
        lastConnected = c;
        lastAttempts = a;
        for (const cb of stateChangeCbs) {
          try {
            cb(c, a);
          } catch (e) {
            console.warn("[Ws] state change cb threw:", e);
          }
        }
      }
    }, 250)
  : null;

// ---------------------------------------------------------------------------
// Public subscription API (preserved from pre-P1.2 surface)
// ---------------------------------------------------------------------------

export function subscribe(handler: (event: WsEvent) => void): () => void {
  return singleton.subscribe(handler);
}

export function subscribeTo(
  type: WsEventType | "*",
  handler: (event: WsEvent) => void,
): () => void {
  return singleton.subscribeTo(type, handler);
}

export function isConnected(): boolean {
  return singleton.isConnected();
}

// ---------------------------------------------------------------------------
// React hooks
// ---------------------------------------------------------------------------

/** Subscribe to all events (or a specific type) inside a component. */
export function useWsEvent(
  type: WsEventType | "*",
  handler: ((event: WsEvent) => void) | undefined,
): void {
  const handlerRef = useRef(handler);
  handlerRef.current = handler;

  useEffect(() => {
    if (!handlerRef.current) return;
    const unsubscribe = singleton.subscribeTo(type, (e) =>
      handlerRef.current?.(e),
    );
    return unsubscribe;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [type]);
}

/** Track WS connection state in a component. */
export function useWsStatus(): { connected: boolean; reconnectAttempts: number } {
  const [connected, setConn] = useState(singleton.isConnected());
  const [attempts, setAttempts] = useState(singleton.reconnectAttempts);

  useEffect(() => {
    const cb: StateChangeCb = (c, a) => {
      setConn(c);
      setAttempts(a);
    };
    stateChangeCbs.add(cb);
    // Sync to current state in case we mounted after a state change
    setConn(singleton.isConnected());
    setAttempts(singleton.reconnectAttempts);
    return () => {
      stateChangeCbs.delete(cb);
    };
  }, []);

  return { connected, reconnectAttempts: attempts };
}

// Silence "unused" warnings for variables that are referenced for
// side-effects (the polling interval keeps the module alive).
void pollInterval;
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
 */

import { useEffect, useState, useRef } from "react";

import { API_BASE } from "./api";

const WS_URL = API_BASE.replace(/^http/, "ws") + "/ws";

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
export type WsEvent = WsEventEnvelope & { data: any };

// ---------------------------------------------------------------------------
// Singleton WebSocket + pub/sub
// ---------------------------------------------------------------------------

type Handler = (event: WsEvent) => void;

interface WsClientState {
  socket: WebSocket | null;
  connected: boolean;
  reconnectAttempts: number;
  listeners: Map<WsEventType | "*", Set<Handler>>;
  onStateChange: Set<(connected: boolean) => void>;
}

const state: WsClientState = {
  socket: null,
  connected: false,
  reconnectAttempts: 0,
  listeners: new Map(),
  onStateChange: new Set(),
};

const MAX_RECONNECT_DELAY = 30000; // 30s cap
const BASE_RECONNECT_DELAY = 500;

function notifyStateChange(connected: boolean) {
  for (const cb of state.onStateChange) {
    try {
      cb(connected);
    } catch (e) {
      console.warn("WS state change handler threw:", e);
    }
  }
}

function setConnected(connected: boolean) {
  if (state.connected !== connected) {
    state.connected = connected;
    notifyStateChange(connected);
  }
}

function dispatch(event: WsEvent) {
  // Specific listeners
  const specific = state.listeners.get(event.type);
  if (specific) {
    for (const h of specific) {
      try {
        h(event);
      } catch (e) {
        console.warn(`WS handler for ${event.type} threw:`, e);
      }
    }
  }
  // Wildcard listeners
  const wildcard = state.listeners.get("*");
  if (wildcard) {
    for (const h of wildcard) {
      try {
        h(event);
      } catch (e) {
        console.warn("WS wildcard handler threw:", e);
      }
    }
  }
}

function connect() {
  if (state.socket && state.socket.readyState <= WebSocket.OPEN) {
    return; // already connecting/connected
  }

  const ws = new WebSocket(WS_URL);
  state.socket = ws;

  ws.onopen = () => {
    setConnected(true);
    state.reconnectAttempts = 0;
  };

  ws.onclose = () => {
    setConnected(false);
    state.socket = null;
    // Reconnect with exponential backoff
    const delay = Math.min(
      BASE_RECONNECT_DELAY * Math.pow(2, state.reconnectAttempts),
      MAX_RECONNECT_DELAY,
    );
    state.reconnectAttempts += 1;
    setTimeout(connect, delay);
  };

  ws.onerror = () => {
    // onclose will follow; just log
    console.debug("WS error, will reconnect");
  };

  ws.onmessage = (msg) => {
    try {
      const event = JSON.parse(msg.data) as WsEvent;
      dispatch(event);
    } catch (e) {
      console.warn("Failed to parse WS message:", e, msg.data);
    }
  };
}

// Auto-connect on first import (browser only)
if (typeof window !== "undefined") {
  // Slight delay to let the page settle; not critical
  if (document.readyState === "complete") {
    connect();
  } else {
    window.addEventListener("load", connect, { once: true });
  }
}

// ---------------------------------------------------------------------------
// Public subscription API
// ---------------------------------------------------------------------------

export function subscribe(handler: Handler): () => void {
  return subscribeTo("*", handler);
}

export function subscribeTo(
  type: WsEventType | "*",
  handler: Handler,
): () => void {
  let set = state.listeners.get(type);
  if (!set) {
    set = new Set();
    state.listeners.set(type, set);
  }
  set.add(handler);
  return () => {
    set?.delete(handler);
  };
}

export function isConnected(): boolean {
  return state.connected;
}

// ---------------------------------------------------------------------------
// React hooks
// ---------------------------------------------------------------------------

/** Subscribe to all events (or a specific type) inside a component. */
export function useWsEvent(
  type: WsEventType | "*",
  handler: Handler | undefined,
): void {
  const handlerRef = useRef(handler);
  handlerRef.current = handler;

  useEffect(() => {
    if (!handlerRef.current) return;
    const unsubscribe = subscribeTo(type, (e) => handlerRef.current?.(e));
    return unsubscribe;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [type]);
}

/** Track WS connection state in a component. */
export function useWsStatus(): { connected: boolean; reconnectAttempts: number } {
  const [connected, setConn] = useState(state.connected);
  const [attempts, setAttempts] = useState(state.reconnectAttempts);

  useEffect(() => {
    const cb = (c: boolean) => {
      setConn(c);
      setAttempts(state.reconnectAttempts);
    };
    state.onStateChange.add(cb);
    // Sync to current state in case we mounted after a state change
    setConn(state.connected);
    setAttempts(state.reconnectAttempts);
    return () => {
      state.onStateChange.delete(cb);
    };
  }, []);

  return { connected, reconnectAttempts: attempts };
}

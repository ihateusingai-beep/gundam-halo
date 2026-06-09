/**
 * Halo Live2D Bridge — unified WebSocket dispatcher for the avatar.
 *
 * Two WS sources fan into one trigger pipeline:
 *
 * 1. **Voice WS** (`/ws/voice`) — the LLM's spoken emotion arrives as a
 *    `live2d.trigger` custom frame. The voice bridge handles lip-sync
 *    coordination (tts.start / tts.end) on the same channel.
 *
 * 2. **Main WS** (`/ws`) — every tool call (file_read, shell_exec, …)
 *    is translated server-side by `ToolMotionMapper` into a
 *    `live2d_tool_trigger` event. We listen for those and dispatch
 *    them through the same `dispatchLive2DTrigger` so the avatar reacts
 *    in real time even when the user isn't speaking.
 *
 * This is a module-level singleton: it auto-connects on first import.
 * Components use the `useHaloLive2D` hook to subscribe to state changes.
 */

import { API_BASE } from "@/lib/api";
import { subscribeTo } from "@/lib/ws";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface Live2DTriggerEvent {
  type: "live2d.trigger";
  data: {
    session_id: string;
    expression: string;
    motion: string;
    emotion: string;
  };
}

export interface TTSStartEvent {
  type: "tts.start";
  data: {
    session_id: string;
    emotion: string;
  };
}

export interface TTSEndEvent {
  type: "tts.end";
  data: {
    session_id: string;
    chunks: number;
  };
}

export interface AgentMessageEvent {
  type: "agent.message";
  data: {
    session_id: string;
    text: string;
    emotion: string;
    is_final: boolean;
  };
}

export interface VoiceHelloEvent {
  type: "voice.hello";
  data: {
    client_id: number;
    sample_rate: number;
    frame_duration_ms: number;
    vad_backend: string;
    asr_backend: string;
    asr_model: string;
    tts_enabled: boolean;
    live2d_enabled: boolean;
  };
}

export type VoiceWSEvent =
  | Live2DTriggerEvent
  | TTSStartEvent
  | TTSEndEvent
  | AgentMessageEvent
  | VoiceHelloEvent
  | { type: string; [key: string]: unknown };

export interface Live2DState {
  connected: boolean;
  live2dEnabled: boolean;
  ttsEnabled: boolean;
  lastTrigger: Live2DTriggerEvent["data"] | null;
  lastText: string | null;
  lastEmotion: string | null;
}

// ---------------------------------------------------------------------------
// Internal bridge state
// ---------------------------------------------------------------------------

interface BridgeState {
  socket: WebSocket | null;
  connected: boolean;
  live2dEnabled: boolean;
  ttsEnabled: boolean;
  lastTrigger: Live2DTriggerEvent["data"] | null;
  lastText: string | null;
  lastEmotion: string | null;
  listeners: Map<string, Set<(event: VoiceWSEvent) => void>>;
  onStateChange: Set<(state: Live2DState) => void>;
}

const state: BridgeState = {
  socket: null,
  connected: false,
  live2dEnabled: false,
  ttsEnabled: false,
  lastTrigger: null,
  lastText: null,
  lastEmotion: null,
  listeners: new Map(),
  onStateChange: new Set(),
};

function notifyState() {
  const s: Live2DState = {
    connected: state.connected,
    live2dEnabled: state.live2dEnabled,
    ttsEnabled: state.ttsEnabled,
    lastTrigger: state.lastTrigger,
    lastText: state.lastText,
    lastEmotion: state.lastEmotion,
  };
  for (const cb of state.onStateChange) {
    try { cb(s); } catch (e) { console.warn("[HaloLive2D] state cb threw:", e); }
  }
}

function dispatch(event: VoiceWSEvent) {
  const type = event.type;
  const specific = state.listeners.get(type);
  if (specific) {
    for (const h of specific) {
      try { h(event); } catch (e) { console.warn(`[HaloLive2D] handler for ${type} threw:`, e); }
    }
  }
  // Wildcard listeners
  const wildcard = state.listeners.get("*");
  if (wildcard) {
    for (const h of wildcard) {
      try { h(event); } catch (e) { console.warn(`[HaloLive2D] wildcard handler threw:`, e); }
    }
  }
}

function connect() {
  if (state.socket && state.socket.readyState <= WebSocket.OPEN) return;

  const WS_URL = API_BASE.replace(/^http/, "ws") + "/ws/voice";
  const ws = new WebSocket(WS_URL);
  state.socket = ws;

  ws.onopen = () => {
    state.connected = true;
    console.log("[HaloLive2D] Connected to voice WS");
    notifyState();
  };

  ws.onclose = () => {
    state.connected = false;
    state.socket = null;
    console.debug("[HaloLive2D] WS closed, will not reconnect (voice is input-driven)");
    notifyState();
  };

  ws.onerror = () => {
    console.warn("[HaloLive2D] WS error");
  };

  ws.onmessage = (msg) => {
    try {
      const raw = JSON.parse(msg.data);
      const event = raw as VoiceWSEvent;
      handleEvent(event);
      dispatch(event);
    } catch (e) {
      console.warn("[HaloLive2D] Failed to parse WS message:", e, msg.data);
    }
  };
}

/**
 * Subscribe to `live2d_tool_trigger` events on the main `/ws` channel
 * (driven by `ToolMotionMapper` on the backend) and route them through
 * the same `dispatchLive2DTrigger` pipeline as voice-emotion triggers.
 *
 * Side effect: updates `state.lastEmotion` so components that read
 * `getLive2DState().lastEmotion` (e.g. CSSAvatar) get the right class
 * without needing to know the event came from the main WS.
 */
function subscribeToMainWsTriggers() {
  subscribeTo("live2d_tool_trigger", (event) => {
    const d = event.data as {
      expression: string;
      motion: string;
      emotion: string;
      tool: string;
      phase: string;
    };
    if (!d || !d.expression) {
      console.warn("[HaloLive2D] live2d_tool_trigger missing fields", d);
      return;
    }
    console.log(
      `[HaloLive2D] Tool trigger: tool=${d.tool}, phase=${d.phase}, emotion=${d.emotion}`,
    );
    state.lastEmotion = d.emotion;
    dispatchLive2DTrigger({
      session_id: "",
      expression: d.expression,
      motion: d.motion,
      emotion: d.emotion,
    });
    notifyState();
  });
}

function handleEvent(event: VoiceWSEvent) {
  switch (event.type) {
    case "voice.hello": {
      const d = event.data as VoiceHelloEvent["data"];
      state.live2dEnabled = d.live2d_enabled ?? false;
      state.ttsEnabled = d.tts_enabled ?? false;
      console.log(
        `[HaloLive2D] Server config: live2d=${state.live2dEnabled}, tts=${state.ttsEnabled}`
      );
      notifyState();
      break;
    }
    case "live2d.trigger": {
      const d = event.data as Live2DTriggerEvent["data"];
      state.lastTrigger = d;
      state.lastEmotion = d.emotion;
      notifyState();
      dispatchLive2DTrigger(d);
      break;
    }
    case "agent.message": {
      const d = event.data as AgentMessageEvent["data"];
      state.lastText = d.text;
      if (!state.lastEmotion) state.lastEmotion = d.emotion;
      notifyState();
      break;
    }
    case "tts.end": {
      // Reset emotion to default when TTS ends
      resetExpression();
      break;
    }
    default:
      break;
  }
}

// ---------------------------------------------------------------------------
// Live2D dispatch (calls into WebSDK globals)
// ---------------------------------------------------------------------------

function dispatchLive2DTrigger(data: Live2DTriggerEvent["data"]) {
  const { expression, motion, emotion } = data;
  console.log(`[HaloLive2D] Trigger: emotion=${emotion}, expression=${expression}, motion=${motion}`);

  const adapter = (window as any).getLAppAdapter?.();
  if (!adapter) {
    console.warn("[HaloLive2D] LAppAdapter not available yet. Trigger queued.");
    return;
  }

  const model = adapter.getModel?.();
  if (!model) {
    console.warn("[HaloLive2D] Live2D model not loaded yet.");
    return;
  }

  // Set expression
  try {
    adapter.setExpression?.(expression);
    console.log(`[HaloLive2D] Expression set: ${expression}`);
  } catch (e) {
    console.error(`[HaloLive2D] Failed to set expression ${expression}:`, e);
  }

  // Play motion (parse group:index from motion string)
  // motion format: "Idle" or "Idle:0" (group:index)
  const [motionGroup, motionIndexStr] = motion.split(":");
  const motionIndex = motionIndexStr ? parseInt(motionIndexStr, 10) : 0;
  const priority = 3; // PriorityForce — interrupt idle animations

  try {
    if (motionGroup) {
      model.startMotion?.(motionGroup, motionIndex, priority);
      console.log(`[HaloLive2D] Motion started: ${motionGroup}[${motionIndex}]`);
    }
  } catch (e) {
    console.error(`[HaloLive2D] Failed to play motion ${motionGroup}:`, e);
  }

  // Start talk motion (always when speaking)
  try {
    model.startRandomMotion?.("Talk", 2); // PriorityNormal
  } catch {
    // Talk group may not exist — that's fine
  }
}

function resetExpression() {
  const adapter = (window as any).getLAppAdapter?.();
  if (!adapter) return;
  const modelInfo = undefined; // Will use model default
  try {
    const expressionCount = adapter.getExpressionCount?.();
    if (expressionCount && expressionCount > 0) {
      const defaultExpr = adapter.getExpressionName?.(0);
      if (defaultExpr) {
        adapter.setExpression?.(defaultExpr);
        console.log(`[HaloLive2D] Expression reset to: ${defaultExpr}`);
      }
    }
  } catch (e) {
    console.warn("[HaloLive2D] Failed to reset expression:", e);
  }
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export function subscribeToVoice(
  type: string | "*",
  handler: (event: VoiceWSEvent) => void,
): () => void {
  let set = state.listeners.get(type);
  if (!set) {
    set = new Set();
    state.listeners.set(type, set);
  }
  set.add(handler);
  return () => { set?.delete(handler); };
}

export function getLive2DState(): Live2DState {
  return {
    connected: state.connected,
    live2dEnabled: state.live2dEnabled,
    ttsEnabled: state.ttsEnabled,
    lastTrigger: state.lastTrigger,
    lastText: state.lastText,
    lastEmotion: state.lastEmotion,
  };
}

export function triggerLive2D(expression: string, motion: string) {
  const adapter = (window as any).getLAppAdapter?.();
  if (!adapter) {
    console.warn("[HaloLive2D] LAppAdapter not available");
    return;
  }
  const model = adapter.getModel?.();
  if (!model) {
    console.warn("[HaloLive2D] Model not loaded");
    return;
  }
  try { adapter.setExpression?.(expression); } catch {}
  const [group, idxStr] = motion.split(":");
  if (group) {
    try { model.startMotion?.(group, parseInt(idxStr || "0", 10), 3); } catch {}
  }
}

// Auto-connect on first import (browser only)
if (typeof window !== "undefined") {
  if (document.readyState === "complete") {
    connect();
    subscribeToMainWsTriggers();
  } else {
    window.addEventListener("load", connect, { once: true });
    window.addEventListener("load", subscribeToMainWsTriggers, { once: true });
  }
}

// Expose for console debugging
if (typeof window !== "undefined") {
  (window as any).__haloLive2D = {
    subscribeToVoice,
    getLive2DState,
    triggerLive2D,
    help: () => {
      console.log(`
Halo Live2D Bridge — Console Debug API
  __haloLive2D.getLive2DState()  → current state snapshot
  __haloLive2D.triggerLive2D(expression, motion)  → trigger directly
  __haloLive2D.subscribeToVoice("*", handler)  → subscribe to all events

Sources:
  - /ws/voice: live2d.trigger (emotion from LLM)
  - /ws:       live2d_tool_trigger (mapped from tool calls)
      `);
    },
  };
}
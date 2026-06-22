/**
 * BaseWebSocketClient — generic reconnecting WebSocket with pub/sub.
 *
 * Sprint 32 P1.2 refactor: extracts the duplicated connect/reconnect/
 * dispatch/heartbeat/dead-socket-detection boilerplate that lived
 * in both `lib/ws.ts` (general event stream) and
 * `services/halo-voice-ws.ts` (voice stream with binary frames).
 *
 * Subclasses provide:
 *   - `getUrl()` — the WebSocket URL to connect to
 *   - `handleEvent(event)` — optional per-event reducer (e.g. voice
 *      state machine). The base class still dispatches to listeners
 *      regardless; the reducer is for high-level state transitions.
 *   - `handleBinary(chunk)` — optional binary handler override
 *      (default: forward to registered binary listeners).
 *   - `get heartbeatEnabled()` — return true to enable ping/pong
 *      liveness probing (default: false).
 *   - `get heartbeatMs()` / `get heartbeatTimeoutMs()` — timings.
 *   - `heartbeatPayload()` — what to send on each ping (default
 *      `{ type: "ping", ts: Date.now() }`).
 *   - `isHeartbeatPong(event)` — return true to clear the pong
 *      deadline (default: any incoming event counts).
 *   - `get autoConnectOnLoad()` — auto-connect on `window.load`
 *      (default: true).
 *
 * Public surface (typed via generics):
 *   - `subscribe(handler)` — wildcard listener
 *   - `subscribeTo(type, handler)` — typed listener
 *   - `onBinary(handler)` — binary listener
 *   - `isConnected()`, `reconnectAttempts`
 *   - `forceReconnect(reason?)` — manual reconnect hook
 *   - `send(payload)` — send JSON or binary; auto-reconnects on
 *      dead socket (warning logged) instead of silently dropping
 *
 * The base class intentionally does NOT touch React hooks. Hooks
 * live in the concrete wrappers (`lib/ws.ts::useWsEvent` etc.) so
 * React stays out of this module's dependency surface.
 */

import { API_BASE } from "./api";

// ---------------------------------------------------------------------------
// Tunables (override via subclass getters)
// ---------------------------------------------------------------------------

const MAX_RECONNECT_DELAY_MS = 30_000;
const BASE_RECONNECT_DELAY_MS = 500;
const HEARTBEAT_MS = 25_000;
const HEARTBEAT_TIMEOUT_MS = 10_000;
const RECONNECT_BACKOFF_BASE_MS = 1_000;
const RECONNECT_BACKOFF_MAX_MS = 30_000;
const STALE_RECONNECT_DROP_MS = 5_000;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type AnyEvent = { type: string; [key: string]: unknown };

export type EventHandler<TEvent> = (event: TEvent) => void;
export type BinaryHandler<TBinary> = (chunk: TBinary) => void;
export type SendPayload = object | string | ArrayBuffer;

export interface BaseWsOptions {
  /**
   * Tag used in console output to distinguish multiple clients
   * (e.g. "[Voice]" vs "[Ws]"). Falls back to the class name.
   */
  logTag?: string;
}

// ---------------------------------------------------------------------------
// Base class
// ---------------------------------------------------------------------------

export abstract class BaseWebSocketClient<
  TEvent extends AnyEvent,
  TBinary = ArrayBuffer,
> {
  // --- abstract / override hooks ----------------------------------------

  /** WebSocket URL — re-evaluated on every connect so subclasses can
   *  swap bases without subclassing `connect()`. */
  protected abstract getUrl(): string;

  /** Optional per-event reducer for high-level state machines.
   *  Fires BEFORE pub/sub dispatch. */
  protected handleEvent(_event: TEvent): void {
    /* default: no-op */
  }

  /** Optional binary-frame reducer — fires BEFORE the binary
   *  pub/sub fanout. Default: no-op (binary listeners still receive
   *  the chunk via `onBinary()`). */
  protected handleBinary(_chunk: TBinary): void {
    /* default: no-op */
  }

  /** Whether to send a ping every `heartbeatMs` and force a
   *  reconnect if no frame arrives within `heartbeatTimeoutMs`.
   *  Default: false. Subclasses with a `/ws/voice` style protocol
   *  that defines a pong frame should override to true. */
  protected get heartbeatEnabled(): boolean {
    return false;
  }

  protected get heartbeatMs(): number {
    return HEARTBEAT_MS;
  }

  protected get heartbeatTimeoutMs(): number {
    return HEARTBEAT_TIMEOUT_MS;
  }

  /** Payload to send on each heartbeat tick. */
  protected heartbeatPayload(): object {
    return { type: "ping", ts: Date.now() };
  }

  /** Whether an incoming event counts as a heartbeat reply (i.e.
   *  clears the pong-deadline). Default: any frame counts. */
  protected isHeartbeatPong(_event: TEvent): boolean {
    return true;
  }

  /** Auto-connect on module load (when running in the browser).
   *  Default: true. */
  protected get autoConnectOnLoad(): boolean {
    return true;
  }

  /** Auto-reconnect on `visibilitychange → visible` if the socket
   *  is not OPEN. Default: true. */
  protected get reconnectOnTabVisible(): boolean {
    return true;
  }

  /** Log tag for console output. */
  protected get logTag(): string {
    return this._logTag ?? "[Ws]";
  }

  // --- state ------------------------------------------------------------

  protected socket: WebSocket | null = null;
  protected connected = false;
  // NB: `_reconnectAttempts` is declared below alongside its public
  // getter (see `get reconnectAttempts()`). It must NOT be shadowed
  // here — subclasses and the base class both read/write the same
  // counter.
  protected connectAttempted = false;

  protected readonly listeners = new Map<string | "*", Set<EventHandler<TEvent>>>();
  protected readonly binaryListeners = new Set<BinaryHandler<TBinary>>();

  private _logTag: string | undefined;

  private heartbeatTimer: ReturnType<typeof setInterval> | null = null;
  private pongDeadline: ReturnType<typeof setTimeout> | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(options: BaseWsOptions = {}) {
    this._logTag = options.logTag;

    if (typeof window === "undefined") return;

    if (!this.autoConnectOnLoad) return;

    if (this.reconnectOnTabVisible) {
      // Tab visibility probe — when the user returns to the tab after
      // a long background, the WebSocket may be half-open (browser
      // suspended the underlying socket without firing onclose).
      document.addEventListener("visibilitychange", () => {
        if (document.visibilityState !== "visible") return;
        const ws = this.socket;
        if (!ws || ws.readyState !== WebSocket.OPEN) {
          console.log(`${this.logTag} tab visible, socket not open — forcing reconnect`);
          this.forceReconnect("tab_visible");
        } else if (this.heartbeatEnabled) {
          // Socket looks alive but may be half-open. Trigger a ping
          // immediately; if we don't see a frame back, forceReconnect
          // will fire from the heartbeat deadline path.
          try {
            ws.send(JSON.stringify(this.heartbeatPayload()));
          } catch (e) {
            console.warn(`${this.logTag} visibility-ping send threw:`, e);
            this.forceReconnect("visibility_ping_failed");
          }
        }
      });
    }

    if (document.readyState === "complete") {
      this.connect();
    } else {
      window.addEventListener("load", () => this.connect(), { once: true });
    }
  }

  // --- public API --------------------------------------------------------

  /** Subscribe to a specific event type, or "*" for all. */
  subscribeTo(type: string | "*", handler: EventHandler<TEvent>): () => void {
    let set = this.listeners.get(type);
    if (!set) {
      set = new Set();
      this.listeners.set(type, set);
    }
    set.add(handler);
    return () => {
      set?.delete(handler);
    };
  }

  /** Subscribe to all events (wildcard). */
  subscribe(handler: EventHandler<TEvent>): () => void {
    return this.subscribeTo("*", handler);
  }

  /** Subscribe to binary frames. */
  onBinary(handler: BinaryHandler<TBinary>): () => void {
    this.binaryListeners.add(handler);
    return () => {
      this.binaryListeners.delete(handler);
    };
  }

  isConnected(): boolean {
    return this.connected;
  }

  /** Number of reconnect attempts since the last successful open.
   *  Exposed so subclasses (and the React state bridge in `lib/ws.ts`)
   *  can read the counter without subclassing. */
  get reconnectAttempts(): number {
    return this._reconnectAttempts;
  }

  /** Internal counter — renamed to avoid collision with the public
   *  getter above. */
  protected _reconnectAttempts = 0;

  /** Force-close the current socket and schedule a reconnect. */
  forceReconnect(reason: string): void {
    console.log(`${this.logTag} forceReconnect: ${reason}`);
    const ws = this.socket;
    this.socket = null;
    this.stopHeartbeat();
    if (ws && ws.readyState <= WebSocket.OPEN) {
      try {
        ws.close(1000, reason);
      } catch (e) {
        console.warn(`${this.logTag} close() during forceReconnect threw:`, e);
      }
    }
    this.scheduleReconnect();
  }

  /** Send a JSON or binary payload. If the socket isn't OPEN,
   *  triggers a reconnect and drops the message with a warning —
   *  callers should design UI around the expectation that voice
   *  pushes during reconnection can fail loudly. */
  send(payload: SendPayload): boolean {
    const ws = this.socket;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      console.warn(
        `${this.logTag} cannot send, socket not open — scheduling reconnect`,
        payload,
      );
      if (!this.reconnectTimer) {
        this.forceReconnect("dead_socket_send");
      }
      return false;
    }
    // Binary must go through raw — JSON.stringify(new ArrayBuffer(...))
    // collapses to "{}".
    if (payload instanceof ArrayBuffer) {
      try {
        ws.send(payload);
      } catch (e) {
        console.warn(`${this.logTag} ws.send(binary) threw, forcing reconnect:`, e);
        this.forceReconnect("binary_send_threw");
        return false;
      }
      return true;
    }
    try {
      ws.send(typeof payload === "string" ? payload : JSON.stringify(payload));
    } catch (e) {
      console.warn(`${this.logTag} ws.send(text) threw, forcing reconnect:`, e);
      this.forceReconnect("text_send_threw");
      return false;
    }
    return true;
  }

  // --- connection --------------------------------------------------------

  /** Open the WebSocket if not already open / connecting. */
  connect(): void {
    if (this.socket && this.socket.readyState <= WebSocket.OPEN) return;
    if (this.connectAttempted) return;
    this.connectAttempted = true;

    const url = this.getUrl();
    console.log(`${this.logTag} connecting to`, url);
    const ws = new WebSocket(url);
    // If the subclass wants binary frames, opt in here. Subclasses
    // that only handle JSON can leave the default ("blob") which
    // doesn't break anything.
    if (this.binaryListeners.size > 0 || this.usesBinary) {
      ws.binaryType = "arraybuffer";
    }
    this.socket = ws;

    ws.onopen = () => {
      console.log(`${this.logTag} connected`);
      this.connected = true;
      this._reconnectAttempts = 0;
      this.onConnected();
      if (this.heartbeatEnabled) this.startHeartbeat();
    };

    ws.onclose = () => {
      console.log(`${this.logTag} disconnected`);
      this.connected = false;
      this.stopHeartbeat();
      this.socket = null;
      this.connectAttempted = false;
      this.onDisconnected();
      // Auto-reconnect unless the page is being torn down. We can't
      // detect that perfectly, but the next send()/heartbeat tick
      // will reconnect if the user is still around.
      if (typeof document !== "undefined" && document.visibilityState !== "hidden") {
        this.scheduleReconnect();
      }
    };

    ws.onerror = () => {
      this.onError();
      // onclose will follow and trigger the reconnect — don't double up.
    };

    ws.onmessage = (msg) => {
      if (this.heartbeatEnabled) this.noteSocketActivity();
      // Binary frames
      if (msg.data instanceof ArrayBuffer) {
        this.handleBinary(msg.data as unknown as TBinary);
        this.dispatchBinary(msg.data as unknown as TBinary);
        return;
      }
      try {
        const event = JSON.parse(msg.data) as TEvent;
        this.handleEvent(event);
        if (this.heartbeatEnabled && this.isHeartbeatPong(event)) {
          // Already cleared deadline in noteSocketActivity, but we
          // still need to log recovery if previously thought dead.
        }
        this.dispatch(event);
      } catch (e) {
        console.warn(`${this.logTag} failed to parse WS message:`, e, msg.data);
      }
    };
  }

  /** Whether this client expects binary frames (ArrayBuffer). The
   *  default false; subclasses set this to true in their constructor
   *  or override. Used by `connect()` to set `binaryType`. */
  protected get usesBinary(): boolean {
    return false;
  }

  /** Lifecycle hooks — subclasses can override without touching
   *  `connect()`. */
  protected onConnected(): void {}
  protected onDisconnected(): void {}
  protected onError(): void {}

  // --- dispatch ----------------------------------------------------------

  private dispatch(event: TEvent): void {
    const specific = this.listeners.get(event.type);
    if (specific) {
      for (const h of specific) {
        try {
          h(event);
        } catch (e) {
          console.warn(`${this.logTag} handler for ${event.type} threw:`, e);
        }
      }
    }
    const wildcard = this.listeners.get("*");
    if (wildcard) {
      for (const h of wildcard) {
        try {
          h(event);
        } catch (e) {
          console.warn(`${this.logTag} wildcard handler threw:`, e);
        }
      }
    }
  }

  private dispatchBinary(chunk: TBinary): void {
    for (const h of this.binaryListeners) {
      try {
        h(chunk);
      } catch (e) {
        console.warn(`${this.logTag} binary handler threw:`, e);
      }
    }
  }

  // --- heartbeat ---------------------------------------------------------

  private noteSocketActivity(): void {
    if (this.pongDeadline) {
      clearTimeout(this.pongDeadline);
      this.pongDeadline = null;
    }
  }

  private startHeartbeat(): void {
    this.stopHeartbeat();
    this.heartbeatTimer = setInterval(() => {
      const ws = this.socket;
      if (!ws || ws.readyState !== WebSocket.OPEN) return;
      try {
        ws.send(JSON.stringify(this.heartbeatPayload()));
      } catch (e) {
        console.warn(`${this.logTag} heartbeat send threw, treating as dead:`, e);
        this.forceReconnect("heartbeat_send_failed");
        return;
      }
      this.pongDeadline = setTimeout(() => {
        const cur = this.socket;
        if (!cur || cur.readyState !== WebSocket.OPEN) return;
        console.warn(`${this.logTag} no pong within heartbeat timeout, reconnecting`);
        this.forceReconnect("heartbeat_timeout");
      }, this.heartbeatTimeoutMs);
    }, this.heartbeatMs);
  }

  private stopHeartbeat(): void {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
    if (this.pongDeadline) {
      clearTimeout(this.pongDeadline);
      this.pongDeadline = null;
    }
  }

  // --- reconnect ---------------------------------------------------------

  private scheduleReconnect(): void {
    if (this.reconnectTimer) return; // already scheduled
    const delay = Math.min(
      RECONNECT_BACKOFF_BASE_MS * Math.pow(2, this._reconnectAttempts),
      RECONNECT_BACKOFF_MAX_MS,
    );
    this._reconnectAttempts += 1;
    console.log(
      `${this.logTag} reconnect scheduled in ${delay}ms (attempt ${this._reconnectAttempts})`,
    );
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.connectAttempted = false; // allow connect() to actually run
      this.connect();
    }, delay);
    // If we're still in "reconnecting" 5s after the schedule, drop
    // the badge to "idle" so the user knows the panel is waiting
    // for them. The reconnect itself still runs in the background.
    setTimeout(() => {
      // Subclass-specific: voice wrapper flips its state to idle
      // via onDisconnected() handler. No-op for the JSON-only client.
    }, STALE_RECONNECT_DROP_MS);
  }
}

// ---------------------------------------------------------------------------
// Shared URL helper
// ---------------------------------------------------------------------------

/** Convert an HTTP API base to its WS counterpart. */
export function wsUrlFromApi(path = "/ws"): string {
  return API_BASE.replace(/^http/, "ws") + path;
}
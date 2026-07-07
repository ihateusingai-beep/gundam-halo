/**
 * jsdom WebSocket stub — single source of truth, imported by
 * `src/test/setup.ts`.
 *
 * ## Why this exists
 *
 * jsdom v29.1.1 ships its own `WebSocket` constructor
 * (verified via `typeof dom.window.WebSocket === "function"`),
 * but it **rejects relative URLs** with `SyntaxError: The URL
 * '/ws/voice' is invalid.`. Real browsers resolve
 * `new WebSocket("/ws/voice")` against `window.location`
 * (treating it as `ws://<current-host>/ws/voice`); jsdom
 * doesn't.
 *
 * Sprint 56.6 hit this in `frontend/src/services/voice/api.ts`:
 * Line 25 does `const singleton = new VoiceWsClient();` at
 * module load. VoiceWsClient auto-connects, which calls
 * `new WebSocket("/ws/voice")`. The test crashed with the
 * SyntaxError even though we're not testing voice at all —
 * the smoke test just imports every `.tsx` under `src/routes/`
 * (via an `import.meta.glob` resolved against this file's
 * directory), which transitively
 * pulls in `routes/settings/tabs/VoiceTab.tsx` → `services/
 * halo-voice-ws.ts` → `services/voice/api.ts` → BOOM.
 *
 * This stub replicates the browser's URL-resolution behavior:
 * any URL not already absolute is `new URL(url, window.location.
 * href)`-d first, so `new WebSocket("/ws/voice")` becomes
 * `ws://localhost/ws/voice` in the test environment and
 * silently no-ops.
 *
 * ## Why not a per-test mock?
 *
 * Three reasons:
 *  1. The 35 existing component tests would each need `vi.mock
 *     ("@/services/voice/api")` to avoid the auto-connect —
 *     a multi-file, easy-to-forget setup. A global stub fixes
 *     it once.
 *  2. `services/voice/api.ts` exports turn-control functions
 *     used by the **test** of those functions (e.g.
 *     `VoiceWsIndicator.test.tsx`). The stub's no-op
 *     `send` and `close` are correct for those unit tests —
 *     they don't assert on WS frames.
 *  3. For tests that DO need real WS behavior (we have one:
 *     `lib/ws-base.test.ts`), `vi.useFakeTimers()` + a per-test
 *     `WebSocket` override via `vi.stubGlobal` is the
 *     canonical vitest pattern. Don't fight this stub.
 */
export class WebSocketStub {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSING = 2;
  static readonly CLOSED = 3;

  readonly CONNECTING = 0;
  readonly OPEN = 1;
  readonly CLOSING = 2;
  readonly CLOSED = 3;

  /** Fully-resolved URL — what the real WebSocket constructor
   *  would have parsed. Useful for tests that want to assert
   *  on the resolved URL (e.g. VoiceWsIndicator can verify
   *  the URL was `ws://localhost/ws/voice` in jsdom). */
  readonly url: string;
  readyState: number = WebSocketStub.CLOSED;
  binaryType: "blob" | "arraybuffer" = "blob";

  onopen: ((ev: Event) => void) | null = null;
  onclose: ((ev: CloseEvent) => void) | null = null;
  onerror: ((ev: Event) => void) | null = null;
  onmessage: ((ev: MessageEvent) => void) | null = null;

  constructor(url: string, _protocols?: string | string[]) {
    // Resolve relative URLs against `window.location`, the same
    // way a real browser does. In non-jsdom test runners
    // (rare — this stub is jsdom-specific by design), fall
    // back to a stable origin so the URL is parseable.
    const base =
      typeof window !== "undefined" ? window.location.href : "http://localhost/";
    this.url = String(new URL(url, base));
  }

  send(_data: string | ArrayBufferLike | Blob | ArrayBufferView): void {
    // No-op: we don't actually open a socket. Tests that need
    // to assert on sent frames should override this stub with
    // `vi.stubGlobal("WebSocket", MySpyClass)`.
  }

  close(_code?: number, _reason?: string): void {
    // Mark closed so `.connect()` retry logic doesn't
    // infinite-loop. We never fire onclose — there's no real
    // socket to lose.
    this.readyState = WebSocketStub.CLOSED;
  }

  addEventListener(): void {}
  removeEventListener(): void {}
  dispatchEvent(_event: Event): boolean {
    return true;
  }
}

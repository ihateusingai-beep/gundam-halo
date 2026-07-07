/**
 * Vitest setup — runs before every test file.
 *
 * Provides minimal browser APIs that jsdom does not implement by
 * default but are required by 3rd-party libs / our own modules
 * we test:
 *
 *  1. ResizeObserver — cmdk 1.1.1 calls `new ResizeObserver(...)`
 *     when its <Command> component mounts. Without the polyfill
 *     the test crashes with "ResizeObserver is not defined".
 *     We provide a no-op stub; tests do not assert on layout.
 *  2. matchMedia — some shadcn primitives query this. jsdom
 *     returns `null` which is sufficient.
 *  3. scrollIntoView — cmdk calls this when navigating the list.
 *     No-op stub is fine.
 *  4. **WebSocket** — jsdom's default `WebSocket` rejects
 *     relative URLs (`/ws/voice`) with a SyntaxError. Real
 *     browsers resolve them against `window.location`. Our
 *     `WebSocketStub` (in `ws-stub.ts`) replicates the browser
 *     behavior so `services/voice/api.ts`'s module-level
 *     singleton doesn't crash test imports. See `ws-stub.ts`
 *     for the full rationale + how to override per-test.
 *
 * Keep this file tiny. Anything heavy belongs in a per-test mock.
 */

import "@testing-library/jest-dom/vitest";

import { WebSocketStub } from "./ws-stub";

if (typeof globalThis.ResizeObserver === "undefined") {
  class ResizeObserverStub {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  (globalThis as unknown as { ResizeObserver: typeof ResizeObserverStub }).ResizeObserver =
    ResizeObserverStub;
}

if (typeof Element !== "undefined" && !Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = function () {};
}

// jsdom v29.1.1 ships its own WebSocket that rejects relative
// URLs (verified empirically — Sprint 56.6 audit). Install our
// stub unconditionally: vitest is jsdom-only by config
// (`vitest.config.ts` `environment: "jsdom"`). Tests that need
// to assert on WS frames (we have one: `lib/ws-base.test.ts`)
// use `vi.stubGlobal("WebSocket", MySpy)` to override.
(globalThis as unknown as { WebSocket: typeof WebSocketStub }).WebSocket =
  WebSocketStub;
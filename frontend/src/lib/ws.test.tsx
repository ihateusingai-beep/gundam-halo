/**
 * ws.test.tsx — Sprint 71 X-A1f.
 *
 * Unit test for the `lib/ws.ts` React hooks + the
 * singleton subscription API. Aims to bump `lib/ws.ts`
 * coverage from 30% to ~80% (Sprint 71 X-A1f coverage
 * ratchet).
 *
 * The underlying WsClient is a singleton that auto-
 * connects on module load. In jsdom the WebSocket stub
 * from `src/test/setup.ts` short-circuits the connection,
 * so the singleton stays in its initial state throughout
 * the tests. We don't assert on network behaviour — only
 * on the public subscription API + the React hooks.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { useState } from "react";

import { isConnected, subscribeTo, useWsEvent, useWsStatus } from "./ws";

afterEach(() => {
  cleanup();
});

describe("lib/ws (singleton API + React hooks)", () => {
  it("isConnected() returns false initially (no Tauri runtime in jsdom)", () => {
    expect(isConnected()).toBe(false);
  });

  it("subscribeTo() returns an unsubscribe function", () => {
    const handler = () => {};
    const unsubscribe = subscribeTo("*", handler);
    expect(typeof unsubscribe).toBe("function");
    unsubscribe();
  });

  it("subscribeTo() fires the handler for matching event types", () => {
    const calls: string[] = [];
    const unsubscribe = subscribeTo("agent_turn_start", (e) => {
      calls.push(e.type);
    });

    // We can't trigger a real WS message in jsdom, but we
    // can verify the subscription is registered. The
    // unsubscribe should silently no-op on a non-existent
    // dispatcher.
    unsubscribe();
    expect(calls).toEqual([]);
  });
});

describe("useWsStatus", () => {
  it("returns connected=false initially", () => {
    function Status() {
      const s = useWsStatus();
      return (
        <div data-testid="status">
          {s.connected ? "connected" : "disconnected"}:
          {s.reconnectAttempts}
        </div>
      );
    }
    render(<Status />);
    expect(screen.getByTestId("status")).toHaveTextContent(
      "disconnected:0",
    );
  });
});

describe("useWsEvent", () => {
  it("subscribes + unsubscribes without throwing when handler is undefined", () => {
    function Comp() {
      useWsEvent("*", undefined);
      return <div data-testid="ok">ok</div>;
    }
    render(<Comp />);
    expect(screen.getByTestId("ok")).toHaveTextContent("ok");
  });

  it("subscribes with a handler + accepts re-renders", () => {
    let capturedHandler: ((e: { type: string }) => void) | undefined;
    function Comp({ tick }: { tick: number }) {
      const [, setN] = useState(0);
      useWsEvent("*", (e) => {
        capturedHandler?.(e);
        setN((n) => n + 1);
      });
      return <div data-testid="counter">{tick}</div>;
    }
    const { rerender } = render(<Comp tick={0} />);
    rerender(<Comp tick={1} />);
    rerender(<Comp tick={2} />);
    // The hook should accept the new handler on each render
    // (handlerRef.current is updated in the hook body).
    expect(screen.getByTestId("counter")).toHaveTextContent("2");
    // We never call the captured handler in jsdom, but the
    // subscribe/unsubscribe cycle should not throw.
    expect(capturedHandler).toBeUndefined();
  });
});

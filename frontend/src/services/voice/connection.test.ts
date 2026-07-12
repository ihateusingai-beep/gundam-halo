/**
 * services/voice/connection.test.ts — Sprint 66 X-A1b.
 *
 * Tests the public surface of `VoiceWsClient`: snapshot,
 * session tracking, state reset helpers, and status pub/sub.
 * Uses the global WebSocketStub from `src/test/setup.ts` so
 * the client's auto-connect is a no-op (we never call .send()
 * in these tests).
 */
import { describe, expect, it, vi } from "vitest";

import { VoiceWsClient } from "./connection";

describe("VoiceWsClient", () => {
  it("snapshot() returns the initial idle state", () => {
    const client = new VoiceWsClient();
    const snap = client.snapshot();
    expect(snap.state).toBe("idle");
    expect(snap.lastAsr).toBeNull();
    expect(snap.lastReply).toBeNull();
    expect(snap.error).toBeNull();
  });

  it("setCurrentSession() / getCurrentSession() round-trip", () => {
    const client = new VoiceWsClient();
    expect(client.getCurrentSession()).toBeNull();
    client.setCurrentSession("voice-test-123");
    expect(client.getCurrentSession()).toBe("voice-test-123");
    client.setCurrentSession(null);
    expect(client.getCurrentSession()).toBeNull();
  });

  it("resetToListening() flips state to 'listening' and clears error", () => {
    const client = new VoiceWsClient();
    client.resetToListening();
    const snap = client.snapshot();
    expect(snap.state).toBe("listening");
    expect(snap.error).toBeNull();
  });

  it("resetToThinking() flips state to 'thinking' and clears error", () => {
    const client = new VoiceWsClient();
    client.resetToThinking();
    const snap = client.snapshot();
    expect(snap.state).toBe("thinking");
    expect(snap.error).toBeNull();
  });

  it("subscribeStatus() fires the callback on state change", () => {
    const client = new VoiceWsClient();
    const cb = vi.fn();
    const unsub = client.subscribeStatus(cb);
    expect(cb).not.toHaveBeenCalled();
    client.resetToListening();
    expect(cb).toHaveBeenCalled();
    const lastCall = cb.mock.calls[cb.mock.calls.length - 1]?.[0];
    expect(lastCall?.state).toBe("listening");
    unsub();
  });

  it("subscribeStatus() returns an unsubscribe that stops further calls", () => {
    const client = new VoiceWsClient();
    const cb = vi.fn();
    const unsub = client.subscribeStatus(cb);
    client.resetToListening();
    const callsAfterFirst = cb.mock.calls.length;
    unsub();
    client.resetToThinking();
    expect(cb.mock.calls.length).toBe(callsAfterFirst);
  });
});

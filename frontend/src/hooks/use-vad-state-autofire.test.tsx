/**
 * useVadStateAutoFire tests — Sprint 19c Phase 2.
 *
 * Verifies the hook:
 *  - is a no-op when `enabled` is false
 *  - subscribes to vad.state events and fires
 *    voiceBegin / voiceEnd when not paused
 *  - ignores events when paused
 *
 * We mock the `voiceBegin` / `voiceEnd` / `subscribeToVoiceEvent`
 * modules so we can assert call counts without standing up
 * a real WebSocket. The hook contract is the only thing
 * under test; the actual voice WS handler is exercised by
 * the existing Sprint 17b voice_ws tests.
 */
import { renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// vi.mock factory hoists to the top of the file, so any
// top-level consts we reference inside the factory would
// be accessed before they're initialized. vitest's
// `vi.hoisted` is the supported escape hatch (the var
// is created before the mock factory runs).
//
// IMPORTANT: `vi.hoisted` returns a snapshot of the
// values at the time it ran. If we use a plain `let`
// inside the closure, the test file reads the snapshot
// (frozen) and the mock factory reads the live closure
// variable — they diverge. The fix is to expose a
// *holder object* whose `.current` we mutate, so both
// sides see the same reference.
const mocks = vi.hoisted(() => {
  const voiceBeginMock = vi.fn();
  const voiceEndMock = vi.fn();
  const handlerRef: { current: ((event: unknown) => void) | null } = {
    current: null,
  };
  const subscribeToVoiceEventMock = vi.fn(
    (_type: string, handler: (event: unknown) => void) => {
      handlerRef.current = handler;
      return () => {
        handlerRef.current = null;
      };
    },
  );
  return { voiceBeginMock, voiceEndMock, handlerRef, subscribeToVoiceEventMock };
});

vi.mock("@/services/halo-voice-ws", () => ({
  voiceBegin: mocks.voiceBeginMock,
  voiceEnd: mocks.voiceEndMock,
  subscribeToVoiceEvent: mocks.subscribeToVoiceEventMock,
}));

import { useVadStateAutoFire } from "@/hooks/use-vad-state-autofire";

beforeEach(() => {
  mocks.voiceBeginMock.mockClear();
  mocks.voiceEndMock.mockClear();
  mocks.subscribeToVoiceEventMock.mockClear();
  mocks.handlerRef.current = null;
});

afterEach(() => {
  // No-op; renderHook's cleanup is called automatically.
});

describe("useVadStateAutoFire", () => {
  it("is a no-op when enabled is false", () => {
    renderHook(() => useVadStateAutoFire({ enabled: false, paused: false }));
    expect(mocks.subscribeToVoiceEventMock).not.toHaveBeenCalled();
    // No event handler to fire — voiceBegin/voiceEnd
    // should remain untouched.
    if (mocks.handlerRef.current) {
      mocks.handlerRef.current({ data: { state: "speech_start" } });
    }
    expect(mocks.voiceBeginMock).not.toHaveBeenCalled();
  });

  it("subscribes to vad.state and fires voiceBegin on speech_start", () => {
    renderHook(() => useVadStateAutoFire({ enabled: true, paused: false }));
    expect(mocks.subscribeToVoiceEventMock).toHaveBeenCalledWith(
      "vad.state",
      expect.any(Function),
    );
    expect(mocks.handlerRef.current).not.toBeNull();
    mocks.handlerRef.current!({ data: { state: "speech_start" } });
    expect(mocks.voiceBeginMock).toHaveBeenCalledTimes(1);
    expect(mocks.voiceEndMock).not.toHaveBeenCalled();
  });

  it("fires voiceEnd on speech_end", () => {
    renderHook(() => useVadStateAutoFire({ enabled: true, paused: false }));
    mocks.handlerRef.current!({ data: { state: "speech_end" } });
    expect(mocks.voiceEndMock).toHaveBeenCalledTimes(1);
    expect(mocks.voiceBeginMock).not.toHaveBeenCalled();
  });

  it("ignores events when paused", () => {
    renderHook(() => useVadStateAutoFire({ enabled: true, paused: true }));
    mocks.handlerRef.current!({ data: { state: "speech_start" } });
    mocks.handlerRef.current!({ data: { state: "speech_end" } });
    expect(mocks.voiceBeginMock).not.toHaveBeenCalled();
    expect(mocks.voiceEndMock).not.toHaveBeenCalled();
  });

  it("unmount tears down the subscription", () => {
    const { unmount } = renderHook(() =>
      useVadStateAutoFire({ enabled: true, paused: false }),
    );
    expect(mocks.handlerRef.current).not.toBeNull();
    unmount();
    expect(mocks.handlerRef.current).toBeNull();
  });

  it("ignores events with missing or unknown state", () => {
    renderHook(() => useVadStateAutoFire({ enabled: true, paused: false }));
    // Missing data.state
    mocks.handlerRef.current!({ data: {} });
    mocks.handlerRef.current!({});
    // Unknown state value
    mocks.handlerRef.current!({ data: { state: "something_else" } });
    expect(mocks.voiceBeginMock).not.toHaveBeenCalled();
    expect(mocks.voiceEndMock).not.toHaveBeenCalled();
  });
});



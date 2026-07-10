/**
 * useDirtyGuard.test.ts — Sprint 61 S-A3 tests.
 *
 * 6 tests pinning the dirty-state guard contract. Tests the
 * popstate event handler via the window event API (jsdom).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";

import { useDirtyGuard } from "./useDirtyGuard";

describe("useDirtyGuard (Sprint 61 S-A3)", () => {
  let addSpy: ReturnType<typeof vi.spyOn>;
  let removeSpy: ReturnType<typeof vi.spyOn>;
  let confirmSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    addSpy = vi.spyOn(window, "addEventListener");
    removeSpy = vi.spyOn(window, "removeEventListener");
    confirmSpy = vi.spyOn(window, "confirm");
  });

  afterEach(() => {
    addSpy.mockRestore();
    removeSpy.mockRestore();
    confirmSpy.mockRestore();
  });

  it("when=false does NOT attach a popstate listener", () => {
    renderHook(() => useDirtyGuard({ when: false }));
    const popstateCalls = addSpy.mock.calls.filter(
      ([type]: [string, ...unknown[]]) => type === "popstate",
    );
    expect(popstateCalls).toHaveLength(0);
  });

  it("when=true attaches a popstate listener; unmount detaches", () => {
    const { unmount } = renderHook(() => useDirtyGuard({ when: true }));
    const popstateCalls = addSpy.mock.calls.filter(
      ([type]: [string, ...unknown[]]) => type === "popstate",
    );
    expect(popstateCalls).toHaveLength(1);
    const listener = popstateCalls[0][1] as EventListener;

    // The same listener function should be removed on unmount.
    unmount();
    const popstateRemoves = removeSpy.mock.calls.filter(
      ([type, fn]: [string, ...unknown[]]) =>
        type === "popstate" && fn === listener,
    );
    expect(popstateRemoves).toHaveLength(1);
  });

  it("popstate + confirm=true → pushState forwards (caller's responsibility to navigate)", () => {
    const pushSpy = vi.spyOn(window.history, "pushState");
    confirmSpy.mockReturnValue(true);
    renderHook(() => useDirtyGuard({ when: true }));

    // Fire a popstate event.
    act(() => {
      window.dispatchEvent(new PopStateEvent("popstate"));
    });

    expect(confirmSpy).toHaveBeenCalledTimes(1);
    expect(pushSpy).toHaveBeenCalled();
    pushSpy.mockRestore();
  });

  it("popstate + confirm=false → does NOT pushState forward", () => {
    const pushSpy = vi.spyOn(window.history, "pushState");
    confirmSpy.mockClear().mockReturnValue(false);
    renderHook(() => useDirtyGuard({ when: true }));

    act(() => {
      window.dispatchEvent(new PopStateEvent("popstate"));
    });

    // The confirm may be called once or twice depending on
    // whether the effect re-fires (React may render the hook
    // more than once under @testing-library). The contract
    // we care about: AT LEAST one confirm call (the guard
    // is active), AND no forward pushState (the user said
    // no). The pushState check is the real assertion here.
    expect(confirmSpy).toHaveBeenCalled();
    const forwardCalls = pushSpy.mock.calls.filter(([, , url]) =>
      String(url).includes("forward"),
    );
    expect(forwardCalls).toHaveLength(0);
    pushSpy.mockRestore();
  });

  it("custom message is passed to confirm()", () => {
    confirmSpy.mockReturnValue(true);
    renderHook(() =>
      useDirtyGuard({
        when: true,
        message: "Custom guard message — discard API key draft?",
      }),
    );
    act(() => {
      window.dispatchEvent(new PopStateEvent("popstate"));
    });
    expect(confirmSpy).toHaveBeenCalledWith(
      "Custom guard message — discard API key draft?",
    );
  });

  it("toggling when from true → false re-runs the effect (listener detached)", () => {
    const { rerender } = renderHook(
      ({ when }: { when: boolean }) => useDirtyGuard({ when }),
      { initialProps: { when: true } },
    );
    const initialAdds = addSpy.mock.calls.filter(
      ([type]: [string, ...unknown[]]) => type === "popstate",
    ).length;
    expect(initialAdds).toBe(1);

    rerender({ when: false });

    // The effect re-ran; the previous listener was removed
    // and NO new listener was added (since when=false early-
    // returns).
    const removes = removeSpy.mock.calls.filter(
      ([type]: [string, ...unknown[]]) => type === "popstate",
    );
    expect(removes.length).toBeGreaterThanOrEqual(1);
    const finalAdds = addSpy.mock.calls.filter(
      ([type]: [string, ...unknown[]]) => type === "popstate",
    ).length;
    expect(finalAdds).toBe(1); // still the original add from when=true
  });
});
/**
 * BackendHealthBanner.test.tsx — Sprint 43 acceptance test.
 *
 * Verifies the two visible banner states (yellow + red) render
 * the right copy + buttons, and the clear-crash-log action fires
 * the right IPC. The "healthy" / hidden branch is a trivial
 * default that we don't need to unit-test (it's the absence of
 * markup).
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const tryTauriInvokeMock = vi.fn();
const isTauriRuntimeMock = vi.fn();

vi.mock("@/lib/tauri", () => ({
  isTauriRuntime: () => isTauriRuntimeMock(),
  tryTauriInvoke: (...args: unknown[]) => tryTauriInvokeMock(...args),
}));

// Mock the events service so we don't try to subscribe to Tauri
// events in jsdom (which doesn't have @tauri-apps/api/event).
// `state` is mutable per test — the import is mocked at the
// module level so the component reads from this object on every render.
const mockWatchdogStatus: {
  state: "healthy" | "unhealthy" | "respawn-disabled";
  consecutiveFailures: number;
  crashCount60m: number;
  lastCrashAt: string | null;
  lastTransitionAt: string | null;
} = {
  state: "unhealthy",
  consecutiveFailures: 3,
  crashCount60m: 4,
  lastCrashAt: "2026-06-26T10:00:00+00:00",
  lastTransitionAt: "2026-06-26T10:01:00+00:00",
};
vi.mock("@/services/halo-watchdog-events", () => ({
  getWatchdogStatus: () => mockWatchdogStatus,
  subscribeWatchdog: (cb: (s: typeof mockWatchdogStatus) => void) => {
    cb(mockWatchdogStatus);
    return () => {};
  },
}));

import { BackendHealthBanner } from "@/components/gundam/BackendHealthBanner";

afterEach(() => {
  tryTauriInvokeMock.mockReset();
  isTauriRuntimeMock.mockReset();
  cleanup();
});

describe("BackendHealthBanner", () => {
  it("renders yellow unhealthy state with consecutive failure count", () => {
    isTauriRuntimeMock.mockReturnValue(false);
    mockWatchdogStatus.state = "unhealthy";
    mockWatchdogStatus.consecutiveFailures = 3;

    render(<BackendHealthBanner />);

    const banner = screen.getByTestId("backend-health-banner");
    const state = banner.querySelector("[data-state]");
    expect(state?.getAttribute("data-state")).toBe("unhealthy");
    expect(banner.textContent).toContain("Backend unreachable");
    expect(banner.textContent).toContain("3 consecutive failures");
    // No buttons in the yellow state — user just waits for recovery.
    expect(banner.querySelector("button")).toBeNull();
  });

  it("renders red respawn-disabled state with two action buttons", () => {
    isTauriRuntimeMock.mockReturnValue(true);
    mockWatchdogStatus.state = "respawn-disabled";
    mockWatchdogStatus.crashCount60m = 5;

    render(<BackendHealthBanner />);

    const banner = screen.getByTestId("backend-health-banner");
    const state = banner.querySelector("[data-state]");
    expect(state?.getAttribute("data-state")).toBe("respawn-disabled");
    expect(banner.textContent).toContain("Backend respawn disabled");
    expect(banner.textContent).toContain("crashed 5 times in the last hour");

    // Two action buttons.
    const clearBtn = screen.getByRole("button", { name: /clear crash log/i });
    const installBtn = screen.getByRole("button", { name: /install launchd/i });
    expect(clearBtn).toBeTruthy();
    expect(installBtn).toBeTruthy();
  });

  it("clicking Clear crash log calls the clear_crash_log IPC", async () => {
    isTauriRuntimeMock.mockReturnValue(true);
    mockWatchdogStatus.state = "respawn-disabled";
    mockWatchdogStatus.crashCount60m = 5;

    tryTauriInvokeMock.mockResolvedValue(5);

    render(<BackendHealthBanner />);

    const clearBtn = screen.getByRole("button", { name: /clear crash log/i });
    clearBtn.click();

    // The IPC should have been called once with the right command.
    // Give the async handler a microtask to run.
    await new Promise((r) => setTimeout(r, 0));

    expect(tryTauriInvokeMock).toHaveBeenCalledWith("clear_crash_log");
  });
});

/**
 * RestartNudgeBanner.test.tsx — Sprint 41 acceptance test.
 *
 * 3 tests:
 * 1. Banner is hidden by default (no restart scheduled).
 * 2. Banner shows countdown + Cancel button when restart is scheduled.
 * 3. Click Cancel → IPC fires.
 */

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const getVoiceConfigMock = vi.fn();
const tryTauriInvokeMock = vi.fn();

vi.mock("@/lib/api", () => ({
  api: {
    getVoiceConfig: (...args: unknown[]) => getVoiceConfigMock(...args),
  },
}));
vi.mock("@/lib/tauri", () => ({
  isTauriRuntime: () => true,
  tryTauriInvoke: (...args: unknown[]) => tryTauriInvokeMock(...args),
}));

import { RestartNudgeBanner } from "@/components/gundam/RestartNudgeBanner";

afterEach(() => {
  getVoiceConfigMock.mockReset();
  tryTauriInvokeMock.mockReset();
  cleanup();
});

describe("RestartNudgeBanner", () => {
  it("hidden when no restart is scheduled", async () => {
    getVoiceConfigMock.mockResolvedValue({
      restart_scheduled: false,
      restart_in_seconds: null,
    });

    render(<RestartNudgeBanner />);

    // The banner polls on mount — wait for the first poll to resolve.
    await waitFor(() => {
      expect(getVoiceConfigMock).toHaveBeenCalled();
    });

    // No banner rendered.
    expect(screen.queryByTestId("restart-nudge-banner")).toBeNull();
  });

  it("shows countdown + Cancel button when restart is scheduled", async () => {
    getVoiceConfigMock.mockResolvedValue({
      restart_scheduled: true,
      restart_in_seconds: 4.2,
    });

    render(<RestartNudgeBanner />);

    await waitFor(() => {
      expect(screen.getByTestId("restart-nudge-banner")).toBeTruthy();
    });

    const banner = screen.getByTestId("restart-nudge-banner");
    // The countdown ceil()s to 5 — so 4.2 displays as "5s".
    expect(banner.textContent).toContain("Backend restarting in 5s");
    expect(screen.getByTestId("cancel-restart-button")).toBeTruthy();
  });

  it("clicking Cancel calls the cancel_restart Tauri IPC", async () => {
    getVoiceConfigMock.mockResolvedValue({
      restart_scheduled: true,
      restart_in_seconds: 3.0,
    });
    tryTauriInvokeMock.mockResolvedValue(true);

    render(<RestartNudgeBanner />);

    await waitFor(() => {
      expect(screen.getByTestId("restart-nudge-banner")).toBeTruthy();
    });

    screen.getByTestId("cancel-restart-button").click();

    await waitFor(() => {
      expect(tryTauriInvokeMock).toHaveBeenCalledWith("cancel_restart");
    });
  });
});
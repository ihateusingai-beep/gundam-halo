/**
 * routes/setup/index.test.tsx — Sprint 66 X-A1b.
 *
 * Verifies the 2 rendering branches of /setup: the
 * "Backend unhealthy" block (when watchdog is in
 * respawn-disabled) and the WizardShell pass-through
 * (when healthy).
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SetupPage } from "./index";

afterEach(() => cleanup());

vi.mock("@/components/wizard/WizardShell", () => ({
  WizardShell: () => <div data-testid="setup-wizard-shell" />,
}));

vi.mock("@/services/halo-watchdog-events", () => ({
  getWatchdogStatus: () => ({ state: "ok", crashCount60m: 0 }),
  subscribeWatchdog: () => () => {},
}));

describe("SetupPage", () => {
  it("renders the WizardShell when backend is healthy", () => {
    render(<SetupPage />);
    expect(screen.getByTestId("setup-wizard-shell")).toBeTruthy();
  });

  it("renders the backend-unhealthy block when watchdog is respawn-disabled", async () => {
    const watchdog = await import("@/services/halo-watchdog-events");
    vi.spyOn(watchdog, "getWatchdogStatus").mockReturnValue({
      state: "respawn-disabled",
      crashCount60m: 4,
      consecutiveFailures: 3,
      lastCrashAt: null,
      lastTransitionAt: null,
    });
    render(<SetupPage />);
    expect(screen.getByTestId("setup-health-blocked")).toBeTruthy();
    expect(screen.getByText(/Backend unhealthy/i)).toBeTruthy();
  });
});

/**
 * SetupWizard.test.tsx — Sprint 39 Track B acceptance test.
 *
 * Verifies the in-progress branch renders the right "Step N of 8"
 * label + "Resume setup" link. Other branches (complete / skipped /
 * not_started / unavailable) are covered by the live smoke test
 * (the card is mounted on `/`); we only test the most visually
 * load-bearing branch here to keep the unit-test surface small.
 *
 * Mocking strategy:
 *   - `api.getSetupState` is mocked to return the in-progress state
 *     synchronously (no need to await fetch).
 *   - We do NOT mock `useEffect` / polling — the 5s interval
 *     doesn't fire inside the test (jsdom's `setInterval` would
 *     require fake timers, which adds complexity for no payoff).
 */

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

const getSetupStateMock = vi.fn();
vi.mock("@/lib/api", () => ({
  api: {
    getSetupState: (...args: unknown[]) => getSetupStateMock(...args),
  },
}));

import { SetupWizard } from "@/components/dashboard/SetupWizard";

afterEach(() => {
  getSetupStateMock.mockReset();
  cleanup();
});

describe("SetupWizard", () => {
  it("renders the in_progress state with step label and resume link", async () => {
    getSetupStateMock.mockResolvedValue({
      status: "in_progress",
      current_step: 3,
      completed_steps: [1, 2],
      started_at: "2026-06-26T00:00:00+00:00",
      finished_at: null,
      skipped: false,
      reason: null,
    });

    render(
      <MemoryRouter>
        <SetupWizard />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("setup-wizard-card")).toBeTruthy();
    });

    const card = screen.getByTestId("setup-wizard-card");
    expect(card.getAttribute("data-state")).toBe("in_progress");
    expect(card.textContent).toContain("Step 3 of 8");
    expect(card.textContent).toContain("2/8 done");

    // The "Resume setup" link points at /setup.
    const link = screen.getByRole("link", { name: /resume setup/i });
    expect(link.getAttribute("href")).toBe("/setup");
  });
});

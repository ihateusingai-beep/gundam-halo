/**
 * SetupWizard.test.tsx — Sprint 39 Track B + Sprint 74 X-A acceptance.
 *
 * Sprint 39: verifies the in-progress branch renders the right
 * "Step N of M" label + "Resume setup" link.
 *
 * Sprint 74 X-A: the cockpit card's "N" + "M" come from the
 * server response (`mode` + `total_steps`). The hardcoded
 * `TOTAL_STEPS = 8` was a pre-Sprint-74 bug (it counted
 * `StepFinish` as a navigable step). Tests now exercise both
 * essential (3 dots) and advanced (7 dots) branches.
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
  it("renders essential in_progress state with 3-dot step label", async () => {
    // Sprint 74 X-A — essential mode = 3 steps. current_step=2 of
    // 3 means the user is mid-LLM step.
    getSetupStateMock.mockResolvedValue({
      status: "in_progress",
      current_step: 2,
      completed_steps: [1],
      started_at: "2026-07-17T00:00:00+00:00",
      finished_at: null,
      skipped: false,
      reason: null,
      mode: "essential",
      total_steps: 3,
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
    expect(card.textContent).toContain("Step 2 of 3");
    expect(card.textContent).toContain("1/3 done");
    // Mode label surfaces in the header.
    expect(card.textContent).toContain("essential");

    // Resume setup link.
    const link = screen.getByRole("link", { name: /resume setup/i });
    expect(link.getAttribute("href")).toBe("/setup");
  });

  it("renders advanced in_progress state with 7-dot step label", async () => {
    // Sprint 74 X-A — advanced mode = 7 steps. Pilot has done
    // 1+2 (Welcome + LLM) and is currently on step 4 (Voice TTS).
    getSetupStateMock.mockResolvedValue({
      status: "in_progress",
      current_step: 4,
      completed_steps: [1, 2, 3],
      started_at: "2026-07-17T00:00:00+00:00",
      finished_at: null,
      skipped: false,
      reason: null,
      mode: "advanced",
      total_steps: 7,
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
    expect(card.textContent).toContain("Step 4 of 7");
    expect(card.textContent).toContain("3/7 done");
    expect(card.textContent).toContain("advanced");
  });

  it("falls back to 3 dots when total_steps is missing (pre-0.3.15 backend)", async () => {
    // Defensive: a pre-Sprint-74 backend doesn't return
    // `total_steps`. The card should default to 3 (essential)
    // rather than crash or render 0 dots.
    getSetupStateMock.mockResolvedValue({
      status: "in_progress",
      current_step: 1,
      completed_steps: [],
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
    expect(card.textContent).toContain("Step 1 of 3");
    expect(card.textContent).toContain("0/3 done");
  });
});

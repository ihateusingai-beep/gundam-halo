/**
 * useSetupWizard.test.tsx — Sprint 44 acceptance test #7.
 *
 * Verifies the state machine advances currentStep on a successful
 * submit. Uses a mocked setupApi so we don't hit the network.
 */

import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const setModeMock = vi.fn();
const submitLLMMock = vi.fn();

vi.mock("@/lib/setup-api", () => ({
  setupApi: {
    getState: vi.fn().mockResolvedValue({
      status: "needs_setup",
      current_step: 2,
      completed_steps: [],
      started_at: "2026-06-26T00:00:00+00:00",
      finished_at: null,
      skipped: false,
      reason: null,
      // Sprint 74 X-A — wizard mode fields.
      mode: "essential" as const,
      total_steps: 3 as const,
    }),
    submitLLM: (...args: unknown[]) => submitLLMMock(...args),
    setMode: (...args: unknown[]) => setModeMock(...args),
  },
}));

import { useSetupWizard } from "@/hooks/useSetupWizard";

afterEach(() => {
  submitLLMMock.mockReset();
  setModeMock.mockReset();
});

describe("useSetupWizard", () => {
  it("advances currentStep from 2 to 3 after successful submitLLM", async () => {
    submitLLMMock.mockResolvedValue({
      ok: true,
      status: "needs_setup",
      current_step: 3,
      completed_steps: [1, 2],
      started_at: "2026-06-26T00:00:00+00:00",
      finished_at: null,
      skipped: false,
      reason: "",
      mode: "essential" as const,
      total_steps: 3 as const,
    });

    const { result } = renderHook(() => useSetupWizard());

    // Wait for the initial getState() to resolve.
    await act(async () => {
      await new Promise((r) => setTimeout(r, 0));
    });

    expect(result.current.currentStep).toBe(2);

    await act(async () => {
      await result.current.submitLLM({
        provider: "minimax",
        api_key: "fake-key",
        base_url: "https://api.minimax.io/v1",
        default_model: "MiniMax-M2",
      });
    });

    expect(result.current.currentStep).toBe(3);
    expect(result.current.completedSteps).toEqual([1, 2]);
    expect(result.current.status).toBe("active");
    expect(result.current.errors).toEqual([]);
  });

  // Sprint 74 X-A — wizard mode persistence
  it("initial mode hydrates from getState() (defaults to 'essential')", async () => {
    const { result } = renderHook(() => useSetupWizard());

    // Wait for the initial getState() to resolve.
    await act(async () => {
      await new Promise((r) => setTimeout(r, 0));
    });

    // The default mock returns mode="essential", total_steps=3.
    expect(result.current.mode).toBe("essential");
    expect(result.current.totalSteps).toBe(3);
  });

  it("setMode('advanced') calls setupApi.setMode + updates local state", async () => {
    setModeMock.mockResolvedValue({
      ok: true,
      status: "needs_setup",
      current_step: 1,
      completed_steps: [],
      started_at: "2026-07-17T00:00:00+00:00",
      finished_at: null,
      skipped: false,
      reason: "",
      mode: "advanced",
      total_steps: 7,
    });

    const { result } = renderHook(() => useSetupWizard());

    // Wait for initial getState().
    await act(async () => {
      await new Promise((r) => setTimeout(r, 0));
    });

    expect(result.current.mode).toBe("essential");

    // Flip to advanced.
    await act(async () => {
      await result.current.setMode("advanced");
    });

    expect(setModeMock).toHaveBeenCalledWith("advanced");
    expect(result.current.mode).toBe("advanced");
    expect(result.current.totalSteps).toBe(7);
  });
});

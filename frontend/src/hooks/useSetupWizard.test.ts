/**
 * useSetupWizard.test.tsx — Sprint 44 acceptance test #7.
 *
 * Verifies the state machine advances currentStep on a successful
 * submit. Uses a mocked setupApi so we don't hit the network.
 */

import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

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
    }),
    submitLLM: (...args: unknown[]) => submitLLMMock(...args),
  },
}));

import { useSetupWizard } from "@/hooks/useSetupWizard";

afterEach(() => {
  submitLLMMock.mockReset();
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
});

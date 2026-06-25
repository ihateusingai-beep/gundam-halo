/**
 * StepSmoke.test.tsx — Sprint 44 acceptance test #6.
 *
 * Verifies that StepSmoke auto-fires the runSmoke handler on mount
 * (the wizard doesn't make the user click anything at step 7).
 */

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const mockRunSmoke = vi.fn();
const mockFinish = vi.fn();

vi.mock("@/hooks/useSetupWizard", () => ({
  useSetupWizard: () => ({
    status: "active",
    currentStep: 7,
    completedSteps: [1, 2, 3, 4, 5, 6],
    errors: [],
    redirect: null,
    runSmoke: mockRunSmoke,
    finish: mockFinish,
    submitLLM: vi.fn(),
    submitASR: vi.fn(),
    submitTTS: vi.fn(),
    submitTheme: vi.fn(),
    submitTailscale: vi.fn(),
    skip: vi.fn(),
    reset: vi.fn(),
    validateLLM: vi.fn(),
    previewTTS: vi.fn(),
    llmForm: {} as any,
    asrForm: {} as any,
    ttsForm: {} as any,
    themeForm: {} as any,
    tailscaleForm: {} as any,
  }),
}));

import { StepSmoke } from "@/components/wizard/StepSmoke";

afterEach(() => {
  mockRunSmoke.mockReset();
  mockFinish.mockReset();
  mockRunSmoke.mockResolvedValue(undefined);
  cleanup();
});

describe("StepSmoke", () => {
  it("auto-runs the smoke test on mount", async () => {
    // The wizard hook is fully mocked above; pass the same shape
    // that useSetupWizard returns so the component reads errors,
    // redirect, finish, runSmoke, status without crashing.
    const fakeWizard = {
      status: "active" as const,
      currentStep: 7 as const,
      completedSteps: [1, 2, 3, 4, 5, 6] as [1, 2, 3, 4, 5, 6],
      errors: [],
      redirect: null,
      runSmoke: mockRunSmoke,
      finish: mockFinish,
      submitLLM: vi.fn(),
      submitASR: vi.fn(),
      submitTTS: vi.fn(),
      submitTheme: vi.fn(),
      submitTailscale: vi.fn(),
      skip: vi.fn(),
      reset: vi.fn(),
      validateLLM: vi.fn(),
      previewTTS: vi.fn(),
      llmForm: {} as any,
      asrForm: {} as any,
      ttsForm: {} as any,
      themeForm: {} as any,
      tailscaleForm: {} as any,
    };
    render(<StepSmoke wizard={fakeWizard} />);

    await waitFor(() => {
      expect(mockRunSmoke).toHaveBeenCalled();
    });
  });
});

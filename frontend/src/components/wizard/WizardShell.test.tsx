/**
 * WizardShell.test.tsx — Sprint 74 X-A progressive-disclosure tests.
 *
 * Verifies the 2-tier mode (essential | advanced) wires through the
 * shell:
 *   - Essential mode: 3 step indicators, "Show advanced" toggle,
 *     header says "3 essential steps".
 *   - Advanced mode: 7 step indicators, "Hide advanced" toggle,
 *     header says "7 steps (advanced)".
 *   - Toggling the button calls wizard.setMode with the next value.
 *   - When mode = essential and current_step is an advanced step
 *     (3-6), the "Advanced required" hint renders.
 *
 * Strategy: mock every step component to a placeholder so the test
 * doesn't pull in voice / theme / tailscale deps, and mock the
 * useSetupWizard hook with a configurable shape. The shell is purely
 * presentational — all real state logic lives in the hook (which is
 * tested in `hooks/useSetupWizard.test.ts`).
 */

import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

// Mock the step components to placeholders. We don't need to test
// the steps themselves here — they have their own test files. We
// only need WizardShell to render *something* for the active step so
// the indicator + toggle UI can be asserted on.
vi.mock("@/components/wizard/StepWelcome", () => ({
  StepWelcome: () => <div data-testid="step-welcome-mock" />,
}));
vi.mock("@/components/wizard/StepLLM", () => ({
  StepLLM: () => <div data-testid="step-llm-mock" />,
}));
vi.mock("@/components/wizard/StepVoiceASR", () => ({
  StepVoiceASR: () => <div data-testid="step-asr-mock" />,
}));
vi.mock("@/components/wizard/StepVoiceTTS", () => ({
  StepVoiceTTS: () => <div data-testid="step-tts-mock" />,
}));
vi.mock("@/components/wizard/StepTheme", () => ({
  StepTheme: () => <div data-testid="step-theme-mock" />,
}));
vi.mock("@/components/wizard/StepTailscale", () => ({
  StepTailscale: () => <div data-testid="step-tailscale-mock" />,
}));
vi.mock("@/components/wizard/StepSmoke", () => ({
  StepSmoke: () => <div data-testid="step-smoke-mock" />,
}));
vi.mock("@/components/wizard/StepFinish", () => ({
  StepFinish: () => <div data-testid="step-finish-mock" />,
}));

// A configurable mock of useSetupWizard. Each test sets `mockState`
// before render to control mode / currentStep / completedSteps.
const mockSetMode = vi.fn();
let mockState: {
  status: "loading" | "active" | "submitting" | "error" | "finished";
  mode: "essential" | "advanced";
  currentStep: 1 | 2 | 3 | 4 | 5 | 6 | 7;
  completedSteps: Array<1 | 2 | 3 | 4 | 5 | 6 | 7>;
};

vi.mock("@/hooks/useSetupWizard", async () => {
  const actual = await vi.importActual<typeof import("@/hooks/useSetupWizard")>(
    "@/hooks/useSetupWizard",
  );
  return {
    ...actual,
    useSetupWizard: () => ({
      status: mockState.status,
      mode: mockState.mode,
      totalSteps: mockState.mode === "advanced" ? 7 : 3,
      currentStep: mockState.currentStep,
      completedSteps: mockState.completedSteps,
      errors: [],
      redirect: null,
      setMode: mockSetMode,
      submitLLM: vi.fn(),
      submitASR: vi.fn(),
      submitTTS: vi.fn(),
      submitTheme: vi.fn(),
      submitTailscale: vi.fn(),
      runSmoke: vi.fn(),
      finish: vi.fn(),
      skip: vi.fn(),
      reset: vi.fn(),
      validateLLM: vi.fn(),
      previewTTS: vi.fn(),
      llmForm: {} as never,
      asrForm: {} as never,
      ttsForm: {} as never,
      themeForm: {} as never,
      tailscaleForm: {} as never,
    }),
  };
});

import { WizardShell } from "@/components/wizard/WizardShell";

afterEach(() => {
  cleanup();
  mockSetMode.mockReset();
  mockState = {
    status: "active",
    mode: "essential",
    currentStep: 1,
    completedSteps: [],
  };
});

describe("WizardShell (Sprint 74 X-A — progressive disclosure)", () => {
  it("essential mode: renders 3 step indicators + 'Show advanced' toggle", () => {
    mockState = {
      status: "active",
      mode: "essential",
      currentStep: 1,
      completedSteps: [],
    };
    render(
      <MemoryRouter>
        <WizardShell />
      </MemoryRouter>,
    );

    // Header reflects essential count.
    expect(screen.getByText(/3 essential steps/i)).toBeTruthy();

    // 3 step indicators (actual step numbers 1, 2, 7). The
    // advanced-only steps (3-6) are NOT shown as indicators in
    // essential mode — the visual gap between "2. LLM" and
    // "7. Smoke" is intentional.
    expect(screen.getByTestId("step-indicator-1")).toBeTruthy();
    expect(screen.getByTestId("step-indicator-2")).toBeTruthy();
    expect(screen.getByTestId("step-indicator-7")).toBeTruthy();
    expect(screen.queryByTestId("step-indicator-3")).toBeNull();
    expect(screen.queryByTestId("step-indicator-4")).toBeNull();
    expect(screen.queryByTestId("step-indicator-5")).toBeNull();
    expect(screen.queryByTestId("step-indicator-6")).toBeNull();

    // Toggle button is in the "reveal advanced" state.
    const toggle = screen.getByTestId("wizard-mode-toggle");
    expect(toggle.textContent).toMatch(/show advanced/i);
    expect(toggle.getAttribute("data-current-mode")).toBe("essential");
  });

  it("advanced mode: renders 7 step indicators + 'Hide advanced' toggle", () => {
    mockState = {
      status: "active",
      mode: "advanced",
      currentStep: 4,
      completedSteps: [1, 2, 3],
    };
    render(
      <MemoryRouter>
        <WizardShell />
      </MemoryRouter>,
    );

    // Header reflects advanced count.
    expect(screen.getByText(/7 steps \(advanced\)/i)).toBeTruthy();

    // All 7 step indicators present.
    for (const s of [1, 2, 3, 4, 5, 6, 7]) {
      expect(screen.getByTestId(`step-indicator-${s}`)).toBeTruthy();
    }

    // Toggle button is in the "hide advanced" state.
    const toggle = screen.getByTestId("wizard-mode-toggle");
    expect(toggle.textContent).toMatch(/hide advanced/i);
    expect(toggle.getAttribute("data-current-mode")).toBe("advanced");
  });

  it("clicking the toggle calls wizard.setMode with the next value", async () => {
    mockState = {
      status: "active",
      mode: "essential",
      currentStep: 1,
      completedSteps: [],
    };
    render(
      <MemoryRouter>
        <WizardShell />
      </MemoryRouter>,
    );

    const toggle = screen.getByTestId("wizard-mode-toggle");
    expect(toggle.textContent).toMatch(/show advanced/i);
    toggle.click();
    expect(mockSetMode).toHaveBeenCalledTimes(1);
    expect(mockSetMode).toHaveBeenCalledWith("advanced");
  });

  it("essential mode + advanced currentStep shows the 'Advanced required' hint", () => {
    // Edge case: user was in advanced mode at step 5, then toggled
    // to essential. The shell should NOT crash; instead it shows
    // a soft prompt to switch back to advanced.
    mockState = {
      status: "active",
      mode: "essential",
      currentStep: 5, // advanced-only step
      completedSteps: [1, 2, 3, 4],
    };
    render(
      <MemoryRouter>
        <WizardShell />
      </MemoryRouter>,
    );

    expect(screen.getByTestId("advanced-required-hint")).toBeTruthy();
    expect(
      screen.getByText(/Step 5 is an advanced step/i),
    ).toBeTruthy();
  });
});

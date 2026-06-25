/**
 * StepLLM.test.tsx — Sprint 44 acceptance test #1.
 *
 * Verifies that picking a provider auto-fills base_url + default_model.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { StepLLM } from "@/components/wizard/StepLLM";

afterEach(() => cleanup());

describe("StepLLM", () => {
  it("auto-fills base_url and default_model when provider changes", async () => {
    const validateMock = vi.fn().mockResolvedValue({ ok: true, model: null, error: null });
    const submitMock = vi.fn().mockResolvedValue(undefined);

    render(
      <StepLLM
        form={{
          provider: "minimax",
          api_key: "",
          base_url: "https://api.minimax.io/v1",
          default_model: "MiniMax-M2",
        }}
        onSubmit={submitMock}
        onValidate={validateMock}
        errors={[]}
        busy={false}
      />,
    );

    // Initial: MiniMax fields shown.
    const modelInput = screen.getByTestId("llm-default-model") as HTMLInputElement;
    expect(modelInput.value).toBe("MiniMax-M2");

    // Switch to openai — base_url + model should update.
    const providerSelect = screen.getByTestId("llm-provider") as HTMLSelectElement;
    providerSelect.value = "openai";
    providerSelect.dispatchEvent(new Event("change", { bubbles: true }));

    // After re-render, model field should show openai's default.
    expect((screen.getByTestId("llm-default-model") as HTMLInputElement).value).toBe(
      "gpt-4o-mini",
    );
  });

  it("disables Validate button when api_key is empty", () => {
    render(
      <StepLLM
        form={{
          provider: "minimax",
          api_key: "",
          base_url: "https://api.minimax.io/v1",
          default_model: "MiniMax-M2",
        }}
        onSubmit={vi.fn()}
        onValidate={vi.fn()}
        errors={[]}
        busy={false}
      />,
    );

    const validateBtn = screen.getByTestId("llm-validate");
    expect(validateBtn.hasAttribute("disabled")).toBe(true);
  });
});

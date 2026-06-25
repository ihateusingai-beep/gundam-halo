/**
 * StepVoiceASR.test.tsx — Sprint 44 acceptance test #2.
 *
 * Verifies backend switching changes which field is shown (model_size
 * vs model_path).
 */

import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { StepVoiceASR } from "@/components/wizard/StepVoiceASR";

afterEach(() => cleanup());

describe("StepVoiceASR", () => {
  it("shows model_size dropdown for whisper_local, model_path for sherpa", async () => {
    render(
      <StepVoiceASR
        form={{
          backend: "whisper_local",
          model_size: "base",
          model_path: "",
          device: "mps",
        }}
        onSubmit={vi.fn()}
        errors={[]}
        busy={false}
      />,
    );

    // whisper_local → model_size visible.
    expect(screen.getByTestId("asr-model-size")).toBeTruthy();

    // Switch to sherpa — wrap in act() so React flushes the state
    // update before the assertion runs.
    const sherpaBtn = screen.getByTestId("asr-backend-sherpa");
    await act(async () => {
      sherpaBtn.click();
    });

    // After re-render, model_size should be gone, model_path should appear.
    expect(screen.queryByTestId("asr-model-size")).toBeNull();
  });
});

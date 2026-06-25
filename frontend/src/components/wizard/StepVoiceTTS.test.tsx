/**
 * StepVoiceTTS.test.tsx — Sprint 44 acceptance test #3.
 *
 * Verifies clicking Preview fires the tts/preview IPC.
 */

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { StepVoiceTTS } from "@/components/wizard/StepVoiceTTS";

afterEach(() => cleanup());

describe("StepVoiceTTS", () => {
  it("clicking Preview calls onPreview with backend+voice", async () => {
    const previewMock = vi.fn().mockResolvedValue({
      ok: true,
      audio_base64: "V0FWCg==", // tiny placeholder
      error: null,
    });
    const submitMock = vi.fn();

    render(
      <StepVoiceTTS
        form={{
          backend: "edge",
          voice: "zh-HK-HiuMaanNeural",
          rate: "+0%",
          pitch: "+0Hz",
          volume: "+0%",
        }}
        onSubmit={submitMock}
        onPreview={previewMock}
        errors={[]}
        busy={false}
      />,
    );

    // Click the Preview button next to the voice.
    const previewBtn = screen.getByTestId("tts-preview-zh-HK-HiuMaanNeural");
    previewBtn.click();

    await waitFor(() => {
      expect(previewMock).toHaveBeenCalledTimes(1);
    });

    const [call] = previewMock.mock.calls;
    expect(call[0]).toEqual({
      backend: "edge",
      voice: "zh-HK-HiuMaanNeural",
      text: "你好，Unicorn。",
    });

    // The audio element should render once preview returns audio_base64.
    await waitFor(() => {
      expect(screen.getByTestId("tts-preview-audio")).toBeTruthy();
    });
  });

  it("renders error message when preview fails with voice_layer_not_loaded", async () => {
    const previewMock = vi.fn().mockResolvedValue({
      ok: false,
      audio_base64: null,
      error: "voice layer not loaded yet",
      error_code: "voice_layer_not_loaded",
    });

    render(
      <StepVoiceTTS
        form={{
          backend: "edge",
          voice: "zh-HK-HiuMaanNeural",
          rate: "+0%",
          pitch: "+0Hz",
          volume: "+0%",
        }}
        onSubmit={vi.fn()}
        onPreview={previewMock}
        errors={[]}
        busy={false}
      />,
    );

    screen.getByTestId("tts-preview-zh-HK-HiuMaanNeural").click();

    await waitFor(() => {
      expect(screen.getByTestId("tts-preview-error")).toBeTruthy();
    });
    expect(screen.getByTestId("tts-preview-error").textContent).toContain(
      "Preview unavailable",
    );
  });
});

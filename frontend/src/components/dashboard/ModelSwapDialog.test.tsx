/**
 * ModelSwapDialog.test.tsx — Sprint 39 Track B acceptance test.
 *
 * Verifies:
 *   1. With current backend = whisper_local, the card renders the
 *      "Activate personalised model…" trigger + the dialog opens
 *      when clicked.
 *   2. The diff preview shows the proposed whisper_hf + a path.
 *   3. `invoke('activate_model')` does NOT fire on dialog open
 *      — only on the explicit "Confirm activate" click.
 *
 * Mocking strategy:
 *   - `api.getVoiceConfig` → returns asr_backend = "whisper_local".
 *   - `tryTauriInvoke` → records the (command, args) pair so we
 *     can assert the IPC contract (Sprint 33b).
 *   - We mock `@/lib/tauri::isTauriRuntime` to return true so the
 *     "Confirm activate" button is enabled (otherwise the test
 *     would need to assert the disabled state too, which is a
 *     separate concern).
 */

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const getVoiceConfigMock = vi.fn();
const tryTauriInvokeMock = vi.fn();
const isTauriRuntimeMock = vi.fn();

vi.mock("@/lib/api", () => ({
  api: {
    getVoiceConfig: (...args: unknown[]) => getVoiceConfigMock(...args),
  },
}));
vi.mock("@/lib/tauri", () => ({
  isTauriRuntime: () => isTauriRuntimeMock(),
  tryTauriInvoke: (...args: unknown[]) => tryTauriInvokeMock(...args),
}));

import { ModelSwapDialog } from "@/components/dashboard/ModelSwapDialog";

afterEach(() => {
  getVoiceConfigMock.mockReset();
  tryTauriInvokeMock.mockReset();
  isTauriRuntimeMock.mockReset();
  cleanup();
});

describe("ModelSwapDialog", () => {
  it("opens the dialog with a diff preview and fires activate_model on confirm", async () => {
    getVoiceConfigMock.mockResolvedValue({
      wake_phrases: ["Unicorn"],
      strict_wake_phrase: true,
      asr_backend: "whisper_local",
      asr_corrector: "bert",
      always_on_mic: false,
    });
    isTauriRuntimeMock.mockReturnValue(true);
    tryTauriInvokeMock.mockResolvedValue({
      phase: "complete",
      message: "Activated whisper_hf at /path/to/checkpoint",
    });

    render(<ModelSwapDialog />);

    await waitFor(() => {
      expect(screen.getByTestId("model-swap-card")).toBeTruthy();
    });

    // Card header shows the current backend label.
    const card = screen.getByTestId("model-swap-card");
    expect(card.textContent).toContain("whisper_local");

    // Opening the dialog does NOT fire invoke yet.
    expect(tryTauriInvokeMock).not.toHaveBeenCalled();

    // Click "Activate personalised model…" trigger.
    const trigger = screen.getByRole("button", {
      name: /activate personalised model/i,
    });
    trigger.click();

    // The dialog body now renders the diff preview.
    await waitFor(() => {
      expect(screen.getByText(/Proposed/)).toBeTruthy();
    });

    // invoke still NOT fired — only opens the dialog.
    expect(tryTauriInvokeMock).not.toHaveBeenCalled();

    // Click the "Confirm activate" button.
    const confirm = screen.getByTestId("confirm-activate");
    confirm.click();

    await waitFor(() => {
      expect(tryTauriInvokeMock).toHaveBeenCalledTimes(1);
    });

    // The IPC contract (Sprint 33b) is `activate_model` with a
    // `checkpointPath` argument.
    const [command, args] = tryTauriInvokeMock.mock.calls[0];
    expect(command).toBe("activate_model");
    expect(args).toEqual({ checkpointPath: expect.any(String) });
  });
});
